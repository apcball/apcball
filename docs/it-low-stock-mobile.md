# IT stock alerts and purchase requisitions

Implemented in `buz_it_stock_mobile` version `17.0.1.2.0`.

- Bell badge and dashboard preview show equipment below its configured minimum.
- The new **สินค้าเหลือน้อย / สร้างใบขอซื้อ** menu opens a desktop drawer or mobile page with search, category/status filters, six items per page, selection, and editable quantities.
- Selection survives filtering and pagination. Suggested quantity fills the shortage to minimum, rounded up to the stock unit precision.
- **สร้างใบขอซื้อ (PR)** opens the existing `employee.purchase.requisition` form with selected lines, quantities, units, current company, responsible user, and IT warehouse receiving operation. The user reviews and saves the document before submitting through the existing approval workflow.
- Server validation checks IT access, PR creation access, current company, current low-stock status, duplicate products, and positive finite quantities matching unit precision.

## Setup

Upgrade `buz_it_stock_mobile`; it now depends on `employee_purchase_requisition`.
In **IT Issue → ตั้งค่า → สินค้า → IT Issue**, configure **IT Minimum Stock** for the current company. Zero disables the product's alert. The threshold is per company and expressed in the inventory unit; availability is free stock in the configured IT location and its children, including reservations.

Users creating requisitions need the existing Purchase Requisition user permission and an employee selected in the PR form. This change does not grant additional PR permissions automatically.

## Validation

- Odoo 17 / PostgreSQL 16, separate local `MOG_TEST` database: **22 tests passed, 0 failures, 0 errors**. Includes threshold boundaries, disabled alerts, unauthorized access, PR defaults, invalid quantities, and ineligible products.
- Actual OWL component rendered in Chromium with mocked ORM: desktop plus 390px and 320px widths; pagination, search, status filter, retained selection, edited PR quantity, and horizontal overflow checks passed. No JavaScript page errors. This browser check does not exercise the real PR form or save workflow.
- SCSS compiled using Odoo's libsass. Python/XML syntax and `git diff --check` passed.

## PR tracking

New PRs opened from the IT low-stock screen retain a link to the IT company configuration when saved. An unsaved form does not change the stock alert. A saved draft, approval request, or active PO changes the alert to **กำลังสั่งซื้อ**. The alert shows accessible PR references and their individual workflow states.

The PR-to-PO workflow preserves a relational reference even when splitting orders by vendor. Pending status is checked per product against non-cancelled PO lines and their received quantities. Fully received products do not stay marked as ordering if stock falls below minimum again. Cancelled or manually closed PRs do not count as pending.

Alerts disappear when available stock in the configured IT location reaches or exceeds minimum. A partial receipt below minimum retains the alert. Data refreshes every 60 seconds while the screen is visible and on **อัปเดตสถานะ** or reopening the screen. Replenished products are removed from any pending selection.

**รายงาน PR เติมคลัง IT** lists related PRs, products, PO references, requester, date and workflow state, including completed/cancelled history. Each alert can open its product-specific PR history. Report and document access retain the existing PR permissions; IT users without PR read permission see only the ordering flag.

PRs created before this tracking extension are not automatically guessed from product names. A draft PR can be linked through **คลัง IT ที่ขอเติม**. Existing POs made before the relational link was introduced are not automatically linked.

Validation for PR tracking: **27 Odoo tests passed**, including real partial/full purchase receipts, a subsequent signed IT issue producing a new shortage, cancelled POs, multiple PRs, company mismatch, restricted visibility, and persistence of the link through the PR form. OWL browser checks passed for ordering filters, PR/report links, selection removal after replenishment, and desktop/mobile layout.

Deployed to DEV `MOG_DEV` on 2026-09-13, version `17.0.1.2.0`, using `scripts/deploy.sh` with worker restart. Verified PR/PO fields, both new views, and the low-stock/report APIs under an existing IT user's permissions. The DEV login endpoint responds with HTTP 303. No business documents or stock balances were changed by these verification calls.

DEV logs also report the unrelated module `office_supply_requisition` as unavailable; it was not changed as part of this deployment.
