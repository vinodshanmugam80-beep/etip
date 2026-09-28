"""Integration tests for AI Delivery (build requests + pipeline runs)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

B = "/api/v1/builds"
OUTBOX = "/api/v1/integrations/outbox"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _build(client: TestClient, h: dict[str, str], **body: object) -> dict:
    payload: dict[str, object] = {"title": "Portal web app", "target_type": "web_app"}
    payload.update(body)
    r = client.post(B, headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _run(client: TestClient, h: dict[str, str], bid: str, stage: str, status: str) -> dict:
    r = client.post(
        f"{B}/{bid}/runs",
        headers=h,
        json={"stage": stage, "status": status, "provider": "tool"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_lifecycle_advances_with_runs(client: TestClient, admin_headers: dict[str, str]) -> None:
    b = _build(client, admin_headers)
    assert b["status"] == "requested"
    _run(client, admin_headers, b["id"], "generate", "passed")
    assert client.get(f"{B}/{b['id']}", headers=admin_headers).json()["status"] == "generated"
    _run(client, admin_headers, b["id"], "unit_test", "passed")
    assert client.get(f"{B}/{b['id']}", headers=admin_headers).json()["status"] == "tested"
    _run(client, admin_headers, b["id"], "deploy", "passed")
    assert client.get(f"{B}/{b['id']}", headers=admin_headers).json()["status"] == "deployed"
    # Three runs recorded, oldest first.
    runs = client.get(f"{B}/{b['id']}/runs", headers=admin_headers).json()
    assert [r["stage"] for r in runs] == ["generate", "unit_test", "deploy"]


def test_deploy_emits_build_deployed(client: TestClient, admin_headers: dict[str, str]) -> None:
    b = _build(client, admin_headers)
    _run(client, admin_headers, b["id"], "deploy", "passed")
    events = [e["event_type"] for e in client.get(OUTBOX, headers=admin_headers).json()["items"]]
    assert "build.deployed" in events


def test_failed_run_fails_build_and_emits(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    b = _build(client, admin_headers)
    _run(client, admin_headers, b["id"], "unit_test", "failed")
    assert client.get(f"{B}/{b['id']}", headers=admin_headers).json()["status"] == "failed"
    events = [e["event_type"] for e in client.get(OUTBOX, headers=admin_headers).json()["items"]]
    assert "build.failed" in events
    # A terminal build rejects further runs.
    assert (
        client.post(
            f"{B}/{b['id']}/runs",
            headers=admin_headers,
            json={"stage": "deploy", "status": "passed"},
        ).status_code
        == 409
    )


def test_cancel_and_filters(client: TestClient, admin_headers: dict[str, str]) -> None:
    b = _build(client, admin_headers, target_type="mobile_app")
    assert (
        client.post(f"{B}/{b['id']}/cancel", headers=admin_headers).json()["status"] == "cancelled"
    )
    assert (
        client.post(f"{B}/{b['id']}/cancel", headers=admin_headers).status_code == 409
    )  # terminal
    # Filter by target type.
    assert (
        client.get(B, headers=admin_headers, params={"target_type": "mobile_app"}).json()["total"]
        >= 1
    )


def test_not_found_and_bad_project(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert client.get(f"{B}/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert (
        client.post(
            B,
            headers=admin_headers,
            json={"title": "Bad", "project_id": str(uuid.uuid4())},
        ).status_code
        == 422
    )


def test_rbac_member_read_only(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    _build(client, admin_headers)
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "b@contoso.com",
            "full_name": "B Member",
            "password": PW,
            "role_ids": [member_role],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "b@contoso.com",
            "password": PW,
        },
    )
    member = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.get(B, headers=member).status_code == 200  # read allowed
    assert (
        client.post(B, headers=member, json={"title": "Nope"}).status_code == 403
    )  # manage denied


def test_update_build(client: TestClient, admin_headers: dict[str, str]) -> None:
    b = _build(client, admin_headers)
    r = client.patch(
        f"{B}/{b['id']}",
        headers=admin_headers,
        json={"title": "Renamed portal", "status": "generating"},
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Renamed portal" and r.json()["status"] == "generating"


def test_generate_template_provider(client: TestClient, admin_headers: dict[str, str]) -> None:
    b = _build(client, admin_headers, target_type="web_app", spec="Track daily habits")
    r = client.post(f"{B}/{b['id']}/generate", headers=admin_headers).json()
    assert r["provider"] == "template" and r["status"] == "generated"
    assert "index.html" in r["files"] and "<!doctype" in r["files"]["index.html"].lower()
    # A generate run was recorded and the build advanced.
    runs = client.get(f"{B}/{b['id']}/runs", headers=admin_headers).json()
    assert any(x["stage"] == "generate" and x["provider"] == "template" for x in runs)


def test_codegen_factory_and_llm_path(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.modules.aidelivery import codegen
    from app.modules.aidelivery.models import BuildTargetType

    base = get_settings()
    # No key -> deterministic template provider.
    assert (
        codegen.get_codegen_provider(
            base.model_copy(update={"codegen_provider": "anthropic", "codegen_api_key": ""})
        ).name
        == "template"
    )

    # Key set -> LLM provider; the HTTP call is mocked (no real network / key).
    monkeypatch.setattr(
        codegen,
        "llm_complete",
        lambda url, h, body: "```html\n<!doctype html><html>LLM built</html>\n```",
    )
    s = base.model_copy(
        update={
            "codegen_provider": "anthropic",
            "codegen_api_key": "sk-test",
            "codegen_model": "m",
        }
    )
    provider = codegen.get_codegen_provider(s)
    assert provider.name == "anthropic"
    art = provider.generate("build a portal", BuildTargetType.WEB_APP)
    assert "<!doctype" in art.files["index.html"].lower() and "LLM built" in art.files["index.html"]


def test_template_api_service_scaffold() -> None:
    from app.core.config import get_settings
    from app.modules.aidelivery.codegen import get_codegen_provider
    from app.modules.aidelivery.models import BuildTargetType

    art = get_codegen_provider(get_settings()).generate("orders API", BuildTargetType.API_SERVICE)
    assert set(art.files) == {"main.py", "requirements.txt"} and "FastAPI" in art.files["main.py"]


def test_full_sdlc_with_metrics_and_deploys(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    b = _build(client, admin_headers)
    # generate -> build -> unit_test (with metrics) -> qa -> deploy -> perf_test (with metrics)
    _run(client, admin_headers, b["id"], "generate", "passed")
    _run(client, admin_headers, b["id"], "build", "passed")
    ut = client.post(
        f"{B}/{b['id']}/runs",
        headers=admin_headers,
        json={
            "stage": "unit_test",
            "status": "passed",
            "metrics": {"tests": 120, "passed": 120, "coverage": 91.4},
        },
    )
    assert ut.status_code == 201 and ut.json()["metrics"]["coverage"] == 91.4
    assert client.get(f"{B}/{b['id']}", headers=admin_headers).json()["status"] == "tested"
    _run(client, admin_headers, b["id"], "qa", "passed")
    assert client.get(f"{B}/{b['id']}", headers=admin_headers).json()["status"] == "qa_passed"

    # Deploy to multiple environments.
    for env in ("dev", "staging", "production"):
        d = client.post(
            f"{B}/{b['id']}/deployments",
            headers=admin_headers,
            json={
                "environment": env,
                "status": "deployed",
                "release_version": "1.0.0",
                "url": f"https://{env}.example.com",
            },
        )
        assert d.status_code == 201 and d.json()["environment"] == env
    deps = client.get(f"{B}/{b['id']}/deployments", headers=admin_headers).json()
    assert {x["environment"] for x in deps} == {"dev", "staging", "production"}

    # Performance test with metrics.
    perf = client.post(
        f"{B}/{b['id']}/runs",
        headers=admin_headers,
        json={
            "stage": "perf_test",
            "status": "passed",
            "metrics": {"p95_ms": 180, "rps": 500, "error_rate": 0.1},
        },
    )
    assert perf.status_code == 201
    assert client.get(f"{B}/{b['id']}", headers=admin_headers).json()["status"] == "validated"


def test_deploy_emits_event_per_environment(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    b = _build(client, admin_headers)
    client.post(
        f"{B}/{b['id']}/deployments",
        headers=admin_headers,
        json={"environment": "production", "status": "deployed"},
    )
    events = [e["event_type"] for e in client.get(OUTBOX, headers=admin_headers).json()["items"]]
    assert "build.deployed" in events


def test_quality_gate_blocks_then_allows_production(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    b = _build(client, admin_headers, gate_min_coverage=80, gate_max_p95_ms=200)
    # Low coverage → gate fails.
    client.post(
        f"{B}/{b['id']}/runs",
        headers=admin_headers,
        json={"stage": "unit_test", "status": "passed", "metrics": {"coverage": 70}},
    )
    gate = client.get(f"{B}/{b['id']}/gate", headers=admin_headers).json()
    assert gate["passed"] is False
    # Staging is not gated; production is blocked.
    assert (
        client.post(
            f"{B}/{b['id']}/deployments",
            headers=admin_headers,
            json={"environment": "staging", "status": "deployed"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"{B}/{b['id']}/deployments",
            headers=admin_headers,
            json={"environment": "production", "status": "deployed"},
        ).status_code
        == 409
    )
    # Meet the thresholds → gate passes, production allowed.
    client.post(
        f"{B}/{b['id']}/runs",
        headers=admin_headers,
        json={"stage": "unit_test", "status": "passed", "metrics": {"coverage": 92}},
    )
    client.post(
        f"{B}/{b['id']}/runs",
        headers=admin_headers,
        json={"stage": "perf_test", "status": "passed", "metrics": {"p95_ms": 150}},
    )
    assert client.get(f"{B}/{b['id']}/gate", headers=admin_headers).json()["passed"] is True
    assert (
        client.post(
            f"{B}/{b['id']}/deployments",
            headers=admin_headers,
            json={"environment": "production", "status": "deployed"},
        ).status_code
        == 201
    )


def test_no_gate_configured_allows_production(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    b = _build(client, admin_headers)  # no thresholds
    assert client.get(f"{B}/{b['id']}/gate", headers=admin_headers).json()["passed"] is True
    assert (
        client.post(
            f"{B}/{b['id']}/deployments",
            headers=admin_headers,
            json={"environment": "production", "status": "deployed"},
        ).status_code
        == 201
    )


def test_tech_stacks_catalog(client: TestClient, admin_headers: dict[str, str]) -> None:
    cats = client.get(f"{B}/tech-stacks", headers=admin_headers).json()
    assert isinstance(cats, list) and any(c["category"] == "Backend / API" for c in cats)
    ids = {st["id"] for c in cats for st in c["stacks"]}
    assert {
        "react",
        "python-fastapi",
        "go-http",
        "flutter",
        "angular",
        "nestjs",
        "swiftui",
        "data-python",
    } <= ids


def test_stack_aware_generation(client: TestClient, admin_headers: dict[str, str]) -> None:
    for stack, expected in [
        ("go-http", "main.go"),
        ("react", "src/App.jsx"),
        ("flutter", "lib/main.dart"),
    ]:
        b = _build(client, admin_headers, tech_stack=stack)
        assert client.get(f"{B}/{b['id']}", headers=admin_headers).json()["tech_stack"] == stack
        files = client.post(f"{B}/{b['id']}/generate", headers=admin_headers).json()["files"]
        assert expected in files


def test_scaffold_includes_starter_test(client: TestClient, admin_headers: dict[str, str]) -> None:
    for stack, test_file in [
        ("python-fastapi", "tests/test_smoke.py"),
        ("go-gin", "main_test.go"),
        ("remix", "app.test.js"),
    ]:
        b = _build(client, admin_headers, tech_stack=stack)
        files = client.post(f"{B}/{b['id']}/generate", headers=admin_headers).json()["files"]
        assert test_file in files


def test_detect_stack_from_repo(client: TestClient, admin_headers: dict[str, str]) -> None:
    cases = [
        (["go.mod", "main.go"], "go-http", "gotest"),
        (["package.json", "next.config.js"], "nextjs", "jest"),
        (["pom.xml"], "java-spring", "junit"),
        (["manage.py", "requirements.txt"], "python-django", "pytest"),
        (["README.md"], None, None),
    ]
    for filenames, stack, fw in cases:
        r = client.post(
            f"{B}/detect-stack", headers=admin_headers, json={"filenames": filenames}
        ).json()
        assert r["stack"] == stack and r["framework"] == fw


def test_new_stacks_generate(client: TestClient, admin_headers: dict[str, str]) -> None:
    for stack, expected in [
        ("rust-axum", "src/main.rs"),
        ("go-gin", "main.go"),
        ("java-spring-jpa", "src/main/java/com/app/Item.java"),
    ]:
        b = _build(client, admin_headers, tech_stack=stack)
        files = client.post(f"{B}/{b['id']}/generate", headers=admin_headers).json()["files"]
        assert expected in files


def test_c_cpp_shell_stacks(client: TestClient, admin_headers: dict[str, str]) -> None:
    for stack, entry, test_file in [
        ("c", "main.c", "test.c"),
        ("cpp", "main.cpp", "test.cpp"),
        ("shell", "main.sh", "test.sh"),
    ]:
        b = _build(client, admin_headers, tech_stack=stack)
        files = client.post(f"{B}/{b['id']}/generate", headers=admin_headers).json()["files"]
        assert entry in files and test_file in files
    # detection
    for filenames, stack in [
        (["main.cpp"], "cpp"),
        (["prog.c"], "c"),
        (["run.sh"], "shell"),
    ]:
        assert (
            client.post(
                f"{B}/detect-stack",
                headers=admin_headers,
                json={"filenames": filenames},
            ).json()["stack"]
            == stack
        )


def test_added_languages_generate(client: TestClient, admin_headers: dict[str, str]) -> None:
    checks = [
        ("kotlin", "src/main/kotlin/Main.kt", "src/test/kotlin/SmokeTest.kt"),
        ("scala", "src/main/scala/Main.scala", "src/test/scala/SmokeSuite.scala"),
        ("elixir", "mix.exs", "test/app_test.exs"),
        ("haskell", "app/Main.hs", "test/Spec.hs"),
        ("perl", "app.pl", "t/smoke.t"),
        ("r", "app.R", "tests/testthat/test-smoke.R"),
    ]
    for stack, entry, test_file in checks:
        b = _build(client, admin_headers, tech_stack=stack)
        files = client.post(f"{B}/{b['id']}/generate", headers=admin_headers).json()["files"]
        assert entry in files and test_file in files
    for stack, only in [
        ("sql", "schema.sql"),
        ("terraform", "main.tf"),
        ("bicep", "main.bicep"),
    ]:
        b = _build(client, admin_headers, tech_stack=stack)
        assert only in client.post(f"{B}/{b['id']}/generate", headers=admin_headers).json()["files"]
    for filenames, stack in [
        (["build.sbt"], "scala"),
        (["mix.exs"], "elixir"),
        (["main.tf"], "terraform"),
        (["main.bicep"], "bicep"),
    ]:
        assert (
            client.post(
                f"{B}/detect-stack",
                headers=admin_headers,
                json={"filenames": filenames},
            ).json()["stack"]
            == stack
        )


def test_more_languages_generate(client: TestClient, admin_headers: dict[str, str]) -> None:
    with_tests = [
        ("zig", "main.zig", "test.zig"),
        ("nim", "main.nim", "tests/test_smoke.nim"),
        ("clojure", "src/app/core.clj", "test/app/core_test.clj"),
        ("fsharp", "Program.fs", "Tests.fs"),
        ("dart-server", "bin/server.dart", "test/server_test.dart"),
    ]
    for stack, entry, tf in with_tests:
        files = client.post(
            f"{B}/{_build(client, admin_headers, tech_stack=stack)['id']}/generate",
            headers=admin_headers,
        ).json()["files"]
        assert entry in files and tf in files
    for stack, only in [
        ("graphql", "schema.graphql"),
        ("dockerfile", "Dockerfile"),
        ("ansible", "playbook.yml"),
    ]:
        files = client.post(
            f"{B}/{_build(client, admin_headers, tech_stack=stack)['id']}/generate",
            headers=admin_headers,
        ).json()["files"]
        assert only in files
    for filenames, stack in [
        (["build.zig"], "zig"),
        (["deps.edn"], "clojure"),
        (["schema.graphql"], "graphql"),
        (["Dockerfile"], "dockerfile"),
    ]:
        assert (
            client.post(
                f"{B}/detect-stack",
                headers=admin_headers,
                json={"filenames": filenames},
            ).json()["stack"]
            == stack
        )
    # Dockerfile alongside a real app does not override the app stack.
    assert (
        client.post(
            f"{B}/detect-stack",
            headers=admin_headers,
            json={"filenames": ["package.json", "Dockerfile"]},
        ).json()["stack"]
        == "node-express"
    )


def test_final_languages_generate(client: TestClient, admin_headers: dict[str, str]) -> None:
    with_tests = [
        ("elm", "src/Main.elm", "tests/Tests.elm"),
        ("ocaml", "bin/main.ml", "test/test_smoke.ml"),
        ("julia", "src/App.jl", "test/runtests.jl"),
        ("solidity", "src/Contract.sol", "test/Contract.t.sol"),
    ]
    for stack, entry, tf in with_tests:
        files = client.post(
            f"{B}/{_build(client, admin_headers, tech_stack=stack)['id']}/generate",
            headers=admin_headers,
        ).json()["files"]
        assert entry in files and tf in files
    for stack, only in [
        ("protobuf", "proto/app.proto"),
        ("openapi", "openapi.yaml"),
        ("helm", "Chart.yaml"),
    ]:
        files = client.post(
            f"{B}/{_build(client, admin_headers, tech_stack=stack)['id']}/generate",
            headers=admin_headers,
        ).json()["files"]
        assert only in files
    for filenames, stack in [
        (["elm.json"], "elm"),
        (["dune-project"], "ocaml"),
        (["Project.toml"], "julia"),
        (["Chart.yaml"], "helm"),
    ]:
        assert (
            client.post(
                f"{B}/detect-stack",
                headers=admin_headers,
                json={"filenames": filenames},
            ).json()["stack"]
            == stack
        )
    # A .proto alongside a Go service still detects Go.
    assert (
        client.post(
            f"{B}/detect-stack",
            headers=admin_headers,
            json={"filenames": ["go.mod", "api.proto"]},
        ).json()["stack"]
        == "go-http"
    )


def test_test_plan_endpoint(client: TestClient, admin_headers: dict[str, str]) -> None:
    for stack, cmd in [
        ("python-fastapi", "pytest -q"),
        ("go-gin", "go test ./..."),
        ("react", "npm test"),
    ]:
        b = _build(client, admin_headers, tech_stack=stack)
        plan = client.get(f"{B}/{b['id']}/test-plan", headers=admin_headers).json()
        assert plan["command"] == cmd and plan["framework"]


def test_require_tests_gate(client: TestClient, admin_headers: dict[str, str]) -> None:
    b = _build(client, admin_headers, tech_stack="python-fastapi", gate_require_tests=True)
    # No passing unit_test run yet → gate fails, production blocked.
    assert client.get(f"{B}/{b['id']}/gate", headers=admin_headers).json()["passed"] is False
    assert (
        client.post(
            f"{B}/{b['id']}/deployments",
            headers=admin_headers,
            json={"environment": "production", "status": "deployed"},
        ).status_code
        == 409
    )
    # Report a passing unit_test run → gate passes, production allowed.
    client.post(
        f"{B}/{b['id']}/runs",
        headers=admin_headers,
        json={"stage": "unit_test", "status": "passed", "metrics": {"tests": 5}},
    )
    assert client.get(f"{B}/{b['id']}/gate", headers=admin_headers).json()["passed"] is True
    assert (
        client.post(
            f"{B}/{b['id']}/deployments",
            headers=admin_headers,
            json={"environment": "production", "status": "deployed"},
        ).status_code
        == 201
    )


def test_llm_prompt_depth_and_multifile() -> None:
    import app.modules.aidelivery.codegen as cg
    from app.core.config import Settings
    from app.modules.aidelivery.models import BuildTargetType

    captured: dict[str, object] = {}

    def fake_complete(url: str, headers: dict, body: dict) -> str:
        captured["body"] = body
        return '{"app/main.py": "print(1)", "tests/test_app.py": "def test(): assert True"}'

    cg.llm_complete = fake_complete  # type: ignore[assignment]
    settings = Settings(codegen_provider="llm", codegen_api_key="k", jwt_secret_key="x" * 32)
    art = cg.LLMProvider(settings).generate(
        "a todo API", BuildTargetType.API_SERVICE, "python-fastapi"
    )
    assert set(art.files) == {"app/main.py", "tests/test_app.py"}
    prompt = captured["body"]["messages"][0]["content"]  # type: ignore[index]
    assert "CRUD" in prompt and "authentication" in prompt and "JSON object" in prompt
