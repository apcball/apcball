# BUZ Service Receipt

**Version:** 17.0.1.0.0

## Summary

Manage service visits, technician scheduling, product claims with stock pickings, and chargeable service orders.

## Features

- Service receipt form with technician calendar sync
- PDF reports: Service Receipt, Service Claim, Repair Notification
- **Claim Workflow**: Draft → Confirm → Product Return (return picking) → Replacement Delivery (replacement picking) → Done
- **Charge Customer Workflow**: Draft → Confirm → Create SO → Done
- Smart buttons for Return Picking, Replacement Delivery, Sale Order, and Invoice
- Stock pickings auto-created from service receipt lines
- Sale order auto-created for billable lines
- Multi-company support
- Thai/English language toggle on form

## Dependencies

- base, mail, calendar, product, hr
- account, stock, sale

## Technical

### Models

| Model | Key Fields |
|-------|-----------|
| `service.receipt` | name, claim_number, state, partner_id, line_ids, return_picking_id, replacement_picking_id, sale_order_id, invoice_id, technician_ids |
| `service.receipt.line` | product_id, quantity, resolution_type, replacement_product_id, replacement_qty, bill_customer, price_unit |

### States

- draft → confirmed → product_return → replacement_delivery → done / cancel

### Key Files

| File | Purpose |
|------|---------|
| `models/service_receipt.py` | Core model + claim workflow methods |
| `data/stock_location_claim.xml` | Claim Return / Replacement locations |
| `views/service_receipt_views.xml` | Main form with smart buttons + pickings/SO tabs |
| `views/service_claim_views.xml` | Claim-specific form with pickings/SO tabs |
| `report/service_claim_report.xml` | Claim PDF report |
| `tests/test_service_receipt_claim.py` | 7 test cases covering full workflow |

## Changelog

### 17.0.1.0.0

- Initial release with service receipt form, calendar sync, and PDF reports
- Added claim workflow with return/replacement stock pickings
- Added Create SO button for chargeable services