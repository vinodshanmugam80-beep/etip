# Vendor / Procurement / Contracts — Examples

**ETIP 2.0 · Phase 3b.** `BASE = http://localhost:8000/api/v1`. Requires
`Authorization: Bearer <token>`. Permissions: `vendor:read` (Org Admin, PM,
Member), `vendor:manage` (Org Admin, PM).

Suppliers and their spend: a **vendor** is a supplier; a **contract** is an
agreement (optionally tied to a project); a **purchase order** is a spend
commitment against a vendor (committed vs invoiced gives outstanding). Additive:
the Finance module is untouched.

---

## Vendors

`POST /vendors` (`vendor:manage`) → **201**
```json
{ "name": "Acme Corp", "code": "ACME", "category": "technology", "status": "active" }
```
Codes are unique per tenant (case-insensitive) → duplicate is **409**.
Categories: technology, prof_services, staffing, hardware, facilities, other.
`GET /vendors?query=acme&category=technology&status=active`, `GET/PATCH/DELETE
/vendors/{id}` (delete cascades contracts & purchase orders).

## Contracts

`POST /contracts` (`vendor:manage`) → **201**
```json
{ "vendor_id": "…", "title": "MSA 2026", "project_id": "…",
  "contract_type": "fixed_price", "value": "50000.00", "currency": "USD" }
```
Unknown vendor → **404**; a project outside the tenant → **422**.
`GET /contracts?vendor_id=…&project_id=…&status=active`, `GET/PATCH/DELETE
/contracts/{id}`.

## Purchase orders

`POST /purchase-orders` (`vendor:manage`) → **201**
```json
{ "vendor_id": "…", "contract_id": "…", "project_id": "…",
  "reference": "PO-1", "committed_amount": "1000.00" }
```
The response adds the derived outstanding:
```json
{ "reference": "PO-1", "status": "draft", "committed_amount": "1000.00",
  "invoiced_amount": "0.00", "outstanding_amount": "1000.00" }
```
A `contract_id` must belong to the PO's vendor, else **422**.

`POST /purchase-orders/{id}/invoice` (`vendor:manage`) records invoiced amount and
**auto-advances status** (partially_invoiced when 0 < invoiced < committed,
invoiced when invoiced ≥ committed):
```json
{ "invoiced_amount": "300.00" }   →  status "partially_invoiced", outstanding "700.00"
```
Explicit status changes via `PATCH` follow a validated lifecycle
(draft → issued → partially_invoiced → invoiced → paid, with cancel), so e.g.
issued → paid is **422**.

## Rollups

`GET /vendors/{id}/spend` → committed / invoiced / outstanding across a vendor's POs.
`GET /contracts/{id}/summary` → contract value vs committed spend + utilization %.
`GET /procurement/projects/{project_id}/summary` → **200**
```json
{ "scope": "project", "po_count": 2, "total_committed": "2000.00",
  "total_invoiced": "300.00", "total_outstanding": "1700.00" }
```

## Why it matters

Supplier commitments become visible alongside delivery and benefits: outstanding
PO spend is forward-looking cost the finance and intelligence views can reckon
with — not a surprise at invoice time.
