#!/usr/bin/env python3
"""Report AI Delivery pipeline results from CI/CD back into ETIP.

Your CI/CD (GitHub Actions, GitLab CI, Jenkins, …) does the real work — compile,
test, deploy, load-test — then calls this script to record the outcome against a
build in ETIP. ETIP is the control plane; this turns your pipeline into its
executor. Uses only the standard library.

Environment:
    ETIP_URL       Base URL of the ETIP instance, e.g. https://etip.acme.com
    ETIP_API_KEY   An ETIP API key (X-API-Key) with `build:manage`
    ETIP_BUILD_ID  The build request id to report against

Usage:
    python etip_report.py run --stage unit_test --status passed \
        --metrics '{"tests": 120, "passed": 120, "coverage": 91.4}'
    python etip_report.py run --stage build --status failed --logs-url "$RUN_URL"
    python etip_report.py deploy --environment staging --url https://staging.acme.com
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def _call(method: str, path: str, body: dict[str, object]) -> dict:
    base = os.environ.get("ETIP_URL", "").rstrip("/")
    key = os.environ.get("ETIP_API_KEY", "")
    if not base or not key or not os.environ.get("ETIP_BUILD_ID"):
        sys.exit("Set ETIP_URL, ETIP_API_KEY and ETIP_BUILD_ID.")
    req = urllib.request.Request(
        base + "/api/v1" + path, data=json.dumps(body).encode(), method=method
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("X-API-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        sys.exit(f"ETIP {method} {path} -> {exc.code}: {exc.read().decode()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Report pipeline results to ETIP.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Report a pipeline-stage run.")
    run.add_argument(
        "--stage",
        required=True,
        choices=["generate", "build", "unit_test", "qa", "deploy", "perf_test"],
    )
    run.add_argument("--status", default="passed", choices=["running", "passed", "failed"])
    run.add_argument("--provider", default="github-actions")
    run.add_argument("--metrics", default="{}", help="JSON object of metrics.")
    run.add_argument("--logs-url", default="")
    run.add_argument("--ref", default=os.environ.get("GITHUB_SHA", ""))

    dep = sub.add_parser("deploy", help="Report a deployment to an environment.")
    dep.add_argument("--environment", required=True, choices=["dev", "staging", "production"])
    dep.add_argument("--status", default="deployed", choices=["deployed", "failed", "rolled_back"])
    dep.add_argument("--version", default=os.environ.get("GITHUB_SHA", "")[:7])
    dep.add_argument("--url", default="")
    dep.add_argument("--provider", default="github-actions")

    args = parser.parse_args()
    build_id = os.environ["ETIP_BUILD_ID"]

    if args.cmd == "run":
        try:
            metrics = json.loads(args.metrics or "{}")
        except json.JSONDecodeError:
            sys.exit("--metrics must be a JSON object.")
        _call(
            "POST",
            f"/builds/{build_id}/runs",
            {
                "stage": args.stage,
                "status": args.status,
                "provider": args.provider,
                "metrics": metrics,
                "logs_url": args.logs_url,
                "external_ref": args.ref,
            },
        )
        print(f"ETIP: reported {args.stage} = {args.status}")
    else:
        _call(
            "POST",
            f"/builds/{build_id}/deployments",
            {
                "environment": args.environment,
                "status": args.status,
                "version": args.version,
                "url": args.url,
                "provider": args.provider,
            },
        )
        print(f"ETIP: deployed to {args.environment} = {args.status}")


if __name__ == "__main__":
    main()
