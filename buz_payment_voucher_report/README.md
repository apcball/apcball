# Payment Voucher Report

Professional Accounting Payment Voucher Report for Odoo 17 Community.

## Features

- Export professional Accounting Payment Voucher showing complete journal entries
- Supports Customer Payment, Vendor Payment, Internal Transfer
- Posted Payments (Draft optional)
- Excel (XLSX) export via wizard
- Smart button on `account.payment` form for direct XLSX export
- Filter by: Partner, Journal, Company, Payment Type, State
- Sort by: Payment Date, Number, Partner, Journal
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

## Export Contents

The XLSX export includes payment headers, journal items, balances, and reconciled documents derived from `account.payment.move_id.line_ids`.

## Smart Button

A **Export Payment Voucher** button is added to the `account.payment` form view header.

The button exports XLSX directly for the current payment (must be posted/sent/reconciled).

## Wizard

Access via **Accounting > Reports > Payment Voucher Export**.

The wizard (`payment.voucher.wizard`) allows:
- Filtering by date range, partner, journal, company, payment type, state
- Sorting by payment date, number, partner, journal
- Exporting to XLSX

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

## Excel Export

Export using `xlsxwriter` (requires `report_xlsx` module).

### Columns

Payment Number, Payment Date, Partner, Journal, Payment Type, Payment Method, Label, Account Code, Chart of Account, Debit, Credit, Amount Currency, Reference, Currency, Reconciled Documents

## Security

Only the following groups can export:
- `account.group_account_user` (Accountant)
- `account.group_account_manager` (Account Manager)

## Menu

**Accounting > Reports > Payment Voucher Export**

## Technical Requirements

- Follows Odoo 17 coding standards
- Uses ORM only
- Supports multi-company
- Supports multi-currency
- Supports translations
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
│   └── account_payment.py        # Smart button method
├── wizard/
│   ├── __init__.py
│   ├── payment_voucher_wizard.py
│   └── payment_voucher_wizard_view.xml
├── report/
│   ├── __init__.py
│   ├── report_action.xml
│   └── payment_voucher_xlsx.py    # xlsxwriter export
├── views/
│   ├── account_payment_view.xml    # Smart button injection
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
- Excel export

## Author

Mogen Co., Thailand

## License

LGPL-3
