# buz BO Report Excel

## Module: buz_bo_report_excel
**Version:** 17.0.1.0.0

## Summary
Export Purchase Blanket Orders (Purchase Agreements / `purchase.requisition`) to Excel (.xlsx).

## Features
- Wizard-based export with filters: Date From, Date To, Vendor, Status
- Export selected records directly from tree/form view via server action
- Excel output with styled headers, auto-filter, freeze panes
- Columns: No., Agreement Reference, Vendor, Agreement Type, Ordering Date, Delivery Date, Deadline, Status, Product, Quantity, UoM, Unit Price

## Dependencies
- `purchase` (Odoo core — provides `purchase.requisition` model)
- `openpyxl` (Python library — must be installed in container)

## Technical

### Models
| Model | Type | Description |
|-------|------|-------------|
| `bo.report.excel.wizard` | TransientModel | Wizard for filtering and exporting |

### Files
```
buz_bo_report_excel/
├── __init__.py
├── __manifest__.py
├── wizard/
│   ├── __init__.py
│   ├── bo_report_excel_wizard.py
│   └── bo_report_excel_wizard_views.xml
├── views/
│   └── purchase_requisition_views.xml
├── tests/
│   ├── __init__.py
│   └── test_bo_report_excel.py
└── README.md
```

## Usage
1. Go to **Purchase > Agreements** (Purchase Requisitions)
2. Select one or more records → click **Export Blanket Orders to Excel** (gear menu)
3. Or use **Settings > Export Blanket Orders to Excel** wizard to filter by date/vendor/status

## Changelog

### 17.0.1.0.0 (2025-07-11)
- Initial release
- Wizard with date range, vendor, state filters
- Server action for direct export from selection
- Excel export with openpyxl
