# Payment Voucher Report

Professional Accounting Payment Voucher Report for Odoo 17 Community.

## Features

- Print professional Accounting Payment Voucher showing complete journal entries
- Supports Customer Payment, Vendor Payment, Internal Transfer
- Posted Payments (Draft optional)
- PDF and Excel (XLSX) export via wizard
- Smart button on `account.payment` form for direct PDF print
- Filter by: Partner, Journal, Company, Payment Type, State
- Sort by: Payment Date, Number, Partner, Journal
- Group by: None, Partner, Journal, Payment Method
- Display options (checkboxes): Account Code, Chart of Account, Partner, Label, Reference, Memo, Analytic, Currency, Amount Currency, Reconciled Invoices
- Reconciled documents section (invoices/bills)
- Multi-company support
- Multi-currency support
- Total Debit, Credit, and Difference (highlighted if unbalanced)

## Supported Documents

| Document | Supported |
|----------|-----------|
| Customer Payment | Yes |
| Vendor Payment | Yes |
| Internal Transfer | Yes |
| Posted Payments | Yes |
| Draft Payments | Optional (via wizard filter) |

## Data Source

The report uses `account.payment.move_id.line_ids` (Odoo's generated journal entry).

**Never calculate accounting values manually** — always use the journal entry.

## Report Header

Displays:
- Company Logo
- Company Name
- Payment Voucher title
- Payment Number
- Payment Date
- Partner
- Journal
- Payment Method
- Currency
- Payment Type
- Reference
- Memo
- Created By
- Posted By
- Move Number

## Report Detail

Journal items from `payment.move_id.line_ids`:

| Column | Source |
|--------|--------|
| Account Code | `line.account_id.code` |
| Chart of Account | `line.account_id.name` |
| Partner | `line.partner_id.name` |
| Label | `line.name` |
| Analytic Account | `line.analytic_account_id` (if enabled) |
| Currency | payment currency |
| Amount Currency | `line.amount_currency` |
| Debit | `line.debit` |
| Credit | `line.credit` |

## Total

- Total Debit
- Total Credit
- Difference (must be zero)
- Highlighted in red if journal is unbalanced

## Reconciled Documents

Shows invoices/bills reconciled with the payment:
- Invoice Number
- Invoice Date
- Residual
- Paid Amount

## Footer

- Prepared By
- Checked By
- Approved By
- Received By
- Signature Area
- Page Number
- Print Date

## Smart Button

A **Print Payment Voucher** button is added to the `account.payment` form view header.

The button prints the PDF directly for the current payment (must be posted/sent/reconciled).

## Wizard

Access via **Accounting > Reports > Payment Voucher Report**.

The wizard (`payment.voucher.wizard`) allows:
- Filtering by date range, partner, journal, company, payment type, state
- Sorting by payment date, number, partner, journal
- Grouping by partner, journal, payment method
- Selecting output format (PDF or XLSX)
- Toggling display options (checkboxes)

### Wizard Fields

| Field | Type | Description |
|-------|------|-------------|
| `date_from` | Date | Start date |
| `date_to` | Date | End date |
| `partner_id` | Many2one | Partner filter |
| `journal_id` | Many2one | Journal filter |
| `company_id` | Many2one | Company (default: current) |
| `payment_type` | Selection | inbound/outbound/transfer |
| `state` | Selection | draft/posted/sent/reconciled |
| `sort_by` | Selection | date/name/partner/journal |
| `group_by` | Selection | none/partner/journal/payment_method |
| `output_format` | Selection | pdf/xlsx |
| `show_*` | Boolean | 10 display option checkboxes |

## Filters

Available in wizard:
- Partner
- Journal
- Company
- Payment Type (Customer/Vendor/Transfer)
- State (Draft/Posted)

## Sorting

- Payment Date
- Payment Number
- Partner
- Journal

## Grouping

- None
- Partner
- Journal
- Payment Method

## Options (Checkboxes)

- Show Account Code
- Show Chart of Account
- Show Partner
- Show Label
- Show Reference
- Show Memo
- Show Analytic
- Show Currency
- Show Amount Currency
- Show Reconciled Invoices

## Excel Export

Export using `xlsxwriter` (requires `report_xlsx` module).

### Columns

Payment Number, Payment Date, Partner, Journal, Account Code, Chart of Account, Partner, Label, Debit, Credit, Currency, Amount Currency, Reference, Invoice

## Security

Only the following groups can print:
- `account.group_account_user` (Accountant)
- `account.group_account_manager` (Account Manager)

## Menu

**Accounting > Reports > Payment Voucher Report**

## Technical Requirements

- Follows Odoo 17 coding standards
- Uses ORM only (no raw SQL except for SQL view init)
- No N+1 queries (uses `read_group` where applicable)
- Supports multi-company
- Supports multi-currency
- Supports translations
- Supports paperformat (Landscape A4)
- Uses `external_layout_standard`
- Complete XML IDs
- Uses `report_action`

## Module Structure

```
buz_payment_voucher_report/
├── __init__.py
├── __manifest__.py
├── security/
│   └── ir.model.access.csv
├── models/
│   ├── __init__.py
│   ├── payment_voucher.py        # SQL view model
│   └── account_payment.py        # Smart button method
├── wizard/
│   ├── __init__.py
│   ├── payment_voucher_wizard.py
│   └── payment_voucher_wizard_view.xml
├── report/
│   ├── __init__.py
│   ├── paperformat.xml
│   ├── report_action.xml
│   ├── payment_voucher_report.xml  # QWeb PDF template
│   └── payment_voucher_xlsx.py    # xlsxwriter export
├── views/
│   ├── account_payment_view.xml    # Smart button injection
│   ├── payment_voucher_view.xml    # Tree view
│   └── payment_voucher_menu.xml    # Menu
├── data/
├── static/
│   └── description/
├── demo/
├── tests/
│   ├── __init__.py
│   └── test_payment_voucher.py
└── README.md
```

## Dependencies

- `account` (Odoo Community)
- `mail` (Odoo Community)
- `report_xlsx` (OCA module)

## Installation

1. Place module in Odoo addons path
2. Update app list
3. Install `buz_payment_voucher_report`
4. Ensure `report_xlsx` is installed

## Testing

Run tests:
```bash
# On DEV server
docker exec odoo odoo -d MOG_DEV -u buz_payment_voucher_report --test-enable --stop-after-init --no-http
```

Test coverage:
- Customer Payment
- Vendor Payment
- Internal Transfer
- Debit Total == Credit Total
- Multi Currency
- PDF generation
- Excel export

## Author

Mogen Co., Thailand

## License

LGPL-3
