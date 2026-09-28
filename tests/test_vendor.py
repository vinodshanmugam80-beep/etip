"""Integration tests for Vendor / Procurement / Contracts.

Covers vendor CRUD with code uniqueness, contracts, purchase orders with the
computed outstanding amount and invoicing auto-status, the vendor-belongs check,
spend / utilization / procurement rollups, RBAC and not-found handling.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import _login

VEN = "/api/v1/vendors"
CON = "/api/v1/contracts"
PO = "/api/v1/purchase-orders"
PROC = "/api/v1/procurement"
PROJECTS = "/api/v1/projects"
USERS = "/api/v1/users"
ROLES = "/api/v1/roles"
PW = "Initial-Passphrase!1"


def _vendor(
    client: TestClient,
    h: dict[str, str],
    name: str = "Acme Corp",
    code: str = "ACME",
    **body: object,
) -> dict:
    payload: dict[str, object] = {"name": name, "code": code}
    payload.update(body)
    r = client.post(VEN, headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _contract(client: TestClient, h: dict[str, str], vendor_id: str, **body: object) -> dict:
    payload: dict[str, object] = {"vendor_id": vendor_id, "title": "MSA 2026"}
    payload.update(body)
    r = client.post(CON, headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _po(client: TestClient, h: dict[str, str], vendor_id: str, **body: object) -> dict:
    payload: dict[str, object] = {
        "vendor_id": vendor_id,
        "reference": "PO-1",
        "committed_amount": "1000.00",
    }
    payload.update(body)
    r = client.post(PO, headers=h, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _project(client: TestClient, h: dict[str, str], code: str) -> str:
    r = client.post(PROJECTS, headers=h, json={"name": "Project", "code": code})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_vendor_crud(client: TestClient, admin_headers: dict[str, str]) -> None:
    v = _vendor(client, admin_headers, category="technology", status="active")
    assert v["category"] == "technology"
    # Duplicate code (case-insensitive) → 409.
    assert (
        client.post(VEN, headers=admin_headers, json={"name": "Other", "code": "acme"}).status_code
        == 409
    )

    got = client.get(f"{VEN}/{v['id']}", headers=admin_headers).json()
    assert got["code"] == "ACME"
    upd = client.patch(
        f"{VEN}/{v['id']}", headers=admin_headers, json={"status": "suspended", "code": "ACME2"}
    ).json()
    assert upd["status"] == "suspended" and upd["code"] == "ACME2"

    _vendor(client, admin_headers, name="Globex", code="GLBX", category="staffing")
    tech = client.get(VEN, headers=admin_headers, params={"category": "technology"}).json()
    assert tech["total"] == 1
    q = client.get(VEN, headers=admin_headers, params={"query": "glob"}).json()
    assert q["total"] == 1


def test_contract_crud(client: TestClient, admin_headers: dict[str, str]) -> None:
    v = _vendor(client, admin_headers)
    proj = _project(client, admin_headers, "VC1")
    c = _contract(
        client,
        admin_headers,
        v["id"],
        project_id=proj,
        value="50000.00",
        contract_type="fixed_price",
    )
    assert c["value"] == "50000.00" and c["project_id"] == proj
    # Unknown vendor → 404.
    assert (
        client.post(
            CON, headers=admin_headers, json={"vendor_id": str(uuid.uuid4()), "title": "Orphan"}
        ).status_code
        == 404
    )
    # Bad project → 422.
    assert (
        client.post(
            CON,
            headers=admin_headers,
            json={"vendor_id": v["id"], "title": "BadProj", "project_id": str(uuid.uuid4())},
        ).status_code
        == 422
    )

    upd = client.patch(f"{CON}/{c['id']}", headers=admin_headers, json={"status": "active"}).json()
    assert upd["status"] == "active"
    by_vendor = client.get(CON, headers=admin_headers, params={"vendor_id": v["id"]}).json()
    assert by_vendor["total"] == 1


def test_po_computed_and_invoicing(client: TestClient, admin_headers: dict[str, str]) -> None:
    v = _vendor(client, admin_headers)
    order = _po(client, admin_headers, v["id"], committed_amount="1000.00")
    assert order["outstanding_amount"] == "1000.00" and order["status"] == "draft"
    # Partial invoice.
    partial = client.post(
        f"{PO}/{order['id']}/invoice", headers=admin_headers, json={"invoiced_amount": "300.00"}
    ).json()
    assert partial["status"] == "partially_invoiced" and partial["outstanding_amount"] == "700.00"
    # Full invoice.
    full = client.post(
        f"{PO}/{order['id']}/invoice", headers=admin_headers, json={"invoiced_amount": "1000.00"}
    ).json()
    assert full["status"] == "invoiced" and full["outstanding_amount"] == "0.00"


def test_po_contract_must_match_vendor(client: TestClient, admin_headers: dict[str, str]) -> None:
    va = _vendor(client, admin_headers, name="Vendor A", code="VA")
    vb = _vendor(client, admin_headers, name="Vendor B", code="VB")
    ca = _contract(client, admin_headers, va["id"])
    # PO for vendor B referencing vendor A's contract → 422.
    r = client.post(
        PO,
        headers=admin_headers,
        json={"vendor_id": vb["id"], "contract_id": ca["id"], "committed_amount": "100.00"},
    )
    assert r.status_code == 422


def test_po_status_transition(client: TestClient, admin_headers: dict[str, str]) -> None:
    v = _vendor(client, admin_headers)
    order = _po(client, admin_headers, v["id"])
    assert (
        client.patch(
            f"{PO}/{order['id']}", headers=admin_headers, json={"status": "issued"}
        ).json()["status"]
        == "issued"
    )
    # draft→paid style invalid jump from issued → paid is not allowed.
    assert (
        client.patch(
            f"{PO}/{order['id']}", headers=admin_headers, json={"status": "paid"}
        ).status_code
        == 422
    )


def test_summaries(client: TestClient, admin_headers: dict[str, str]) -> None:
    v = _vendor(client, admin_headers)
    proj = _project(client, admin_headers, "VS1")
    c = _contract(client, admin_headers, v["id"], value="2000.00")
    _po(
        client,
        admin_headers,
        v["id"],
        reference="P1",
        contract_id=c["id"],
        project_id=proj,
        committed_amount="1500.00",
        invoiced_amount="300.00",
    )
    _po(client, admin_headers, v["id"], reference="P2", project_id=proj, committed_amount="500.00")

    spend = client.get(f"{VEN}/{v['id']}/spend", headers=admin_headers).json()
    assert spend["po_count"] == 2 and spend["total_committed"] == "2000.00"
    assert spend["total_invoiced"] == "300.00" and spend["total_outstanding"] == "1700.00"

    csum = client.get(f"{CON}/{c['id']}/summary", headers=admin_headers).json()
    assert csum["value"] == "2000.00" and csum["total_committed"] == "1500.00"
    assert csum["utilization_percent"] == 75.0  # 1500 / 2000

    proc = client.get(f"{PROC}/projects/{proj}/summary", headers=admin_headers).json()
    assert proc["po_count"] == 2 and proc["total_committed"] == "2000.00"
    assert proc["total_outstanding"] == "1700.00"
    # Unknown project → 404.
    assert (
        client.get(f"{PROC}/projects/{uuid.uuid4()}/summary", headers=admin_headers).status_code
        == 404
    )


def test_delete_vendor_cascades(client: TestClient, admin_headers: dict[str, str]) -> None:
    v = _vendor(client, admin_headers)
    c = _contract(client, admin_headers, v["id"])
    o = _po(client, admin_headers, v["id"])
    assert client.delete(f"{VEN}/{v['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"{VEN}/{v['id']}", headers=admin_headers).status_code == 404
    assert client.get(f"{CON}/{c['id']}", headers=admin_headers).status_code == 404
    assert client.get(f"{PO}/{o['id']}", headers=admin_headers).status_code == 404


def test_not_found(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert client.get(f"{VEN}/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.get(f"{CON}/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.get(f"{PO}/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.get(f"{VEN}/{uuid.uuid4()}/spend", headers=admin_headers).status_code == 404


def test_rbac(
    client: TestClient, admin_headers: dict[str, str], registered_org: dict[str, str]
) -> None:
    _vendor(client, admin_headers)
    roles = client.get(ROLES, headers=admin_headers).json()
    member_role = next(r["id"] for r in roles if r["name"] == "Member")
    client.post(
        USERS,
        headers=admin_headers,
        json={
            "email": "vn@contoso.com",
            "full_name": "Vn Reader",
            "password": PW,
            "role_ids": [member_role],
        },
    )
    tokens = _login(
        client,
        {
            "organization_slug": registered_org["organization_slug"],
            "email": "vn@contoso.com",
            "password": PW,
        },
    )
    member = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.get(VEN, headers=member).status_code == 200
    assert (
        client.post(VEN, headers=member, json={"name": "Nope", "code": "NOPE"}).status_code == 403
    )
