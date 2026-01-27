# Technical Documentation: buz_commercial_invoice

## Architecture Overview

The module extends Odoo's Sale Order and Account Move models to support Commercial Invoice generation independent of accounting invoices.

### Data Flow

```
User creates/opens Sale Order
         ↓
   User checks "Generate Commercial Invoice" checkbox
         ↓
   SaleOrder.write() method triggered
         ↓
   System calls _get_commercial_invoice_number()
         ↓
   ir.sequence generates next CIV number (CIV-000001, CIV-000002, etc)
         ↓
   Number stored in commercial_invoice_number field
         ↓
   User clicks "Print Commercial Invoice" button
         ↓
   Report action generates PDF from Sale Order
         ↓
   Professional report displayed with all details
```

## Model Extensions

### 1. SaleOrder Model (`models/sale_order.py`)

**Fields Added:**
```python
commercial_invoice_enabled = Boolean    # Master enable/disable flag
commercial_invoice_number = Char        # Generated CIV number (read-only)
incoterms_id = Many2one                 # Link to account.incoterms
loading_date = Date                     # Expected shipping date
shipping_mark = Char                    # Container/package marking
shipping_by = Selection                 # Transport method: air/sea/land
bank_info = Text                        # Bank payment details
amount_text = Char                      # Computed: amount in words
```

**Methods:**

```python
def create(vals_list):
    """Override create method"""
    # When commercial_invoice_enabled is True in vals:
    # - Auto-generates CIV number via _get_commercial_invoice_number()

def write(vals):
    """Override write method"""
    # When commercial_invoice_enabled changes from False to True:
    # - Auto-generates CIV number if not already present
    
def _get_commercial_invoice_number():
    """Get next CIV number from sequence"""
    # Calls ir.sequence.next_by_code('commercial.invoice.sequence')
    # Returns formatted number like 'CIV-000001'
    
def action_print_commercial_invoice():
    """Action method for print button"""
    # Validation checks
    # Triggers report action with self as document
    # Returns ir.actions.report action
    
def _compute_amount_text():
    """Compute amount in words"""
    # Uses currency.amount_to_text() method
    # Converts amount_total to written words
```

### 2. AccountMove Model (Legacy Support - `models/account_move.py`)

**Fields Added:**
```python
commercial_invoice_number = Char
incoterms_id = Many2one
loading_date = Date
shipping_mark = Char
shipping_by = Selection
bank_info = Text
amount_text = Char
```

**Methods:**
- `create()` - Auto-generate CIV for invoices if enabled
- `action_post()` - Ensure CIV number on posting
- `_get_commercial_invoice_number()` - Same sequence retrieval

### 3. StockPicking Model (`models/stock_picking.py`)

**Methods:**
```python
def action_print_commercial_invoice():
    """Print commercial invoice from delivery"""
    # Finds related sale order or invoice
    # Triggers report action
```

## Sequence Configuration

**File:** `data/sequence.xml`

```xml
<record id="sequence_commercial_invoice" model="ir.sequence">
    <field name="name">Commercial Invoice Sequence</field>
    <field name="code">commercial.invoice.sequence</field>
    <field name="prefix">CIV-</field>
    <field name="padding">6</field>
    <field name="company_id" eval="False"/>  <!-- Shared across companies -->
</record>
```

**Sequence Behavior:**
- Generates: CIV-000001, CIV-000002, ..., CIV-999999
- Company-independent (shared across all companies)
- Atomic operations (thread-safe)

## View Extensions

### 1. Sale Order Form View (`views/sale_order_view.xml`)

```xml
<!-- Inherits from sale.view_order_form -->
<!-- Adds new page "Commercial Invoice" with:
     - Enable checkbox
     - Generated CIV number display
     - Shipping details fields
     - Print button
-->
```

**Page Structure:**
```
Commercial Invoice Tab
├── Group: Main Details
│   ├── commercial_invoice_enabled [checkbox]
│   └── commercial_invoice_number [readonly text]
├── Group: Details
│   ├── incoterms_id
│   ├── loading_date
│   ├── shipping_mark
│   ├── shipping_by
│   └── bank_info
├── Separator: Generated Amount
│   └── amount_text [readonly]
└── Print Button: action_print_commercial_invoice
```

### 2. Sale Order Tree View (`views/sale_order_view.xml`)

**Enhancement:**
- Adds `commercial_invoice_number` column after order name
- Allows quick scanning of CIV status in list view

### 3. Account Move Form View (Legacy - `views/account_move_view.xml`)

```xml
<!-- Inherits from account.view_move_form -->
<!-- Adds commercial_invoice_details group in Other tab:
     - commercial_invoice_number
     - incoterms_id, loading_date, shipping_mark
     - shipping_by, bank_info
-->
```

## Reports

### 1. Sale Order Commercial Invoice Report

**Template:** `report/commercial_invoice_sale_order_report.xml`
**Template ID:** `report_commercial_invoice_sale_order_document`

**Uses Model:** `sale.order`
**Fields Referenced:**
- Basic: date_order, name (reference), currency_id
- Customers: partner_id, partner_shipping_id
- Commercial: commercial_invoice_number, incoterms_id, loading_date, shipping_mark, shipping_by, bank_info
- Items: order_line (product, quantity, price)
- Computed: amount_text, amount_untaxed, amount_total
- Company: company_id (vat, country_id)

**Report Features:**
- Professional layout with logo and company details
- Two-column information layout
- Itemized table with quantities and pricing
- Summary totals with amount in words
- Bank information display
- Signature blocks

### 2. Account Move Commercial Invoice Report (Legacy)

**Template:** `report/commercial_invoice_report.xml`
**Template ID:** `report_commercial_invoice_document`

**Uses Model:** `account.move`
**Differences:**
- References invoice_line_ids instead of order_line
- Uses invoice_date instead of date_order
- Uses invoice_payment_term_id instead of payment_term_id
- Uses ref field instead of name

## Report Actions

**File:** `report/report_action.xml`

```xml
<!-- Primary Action: Sale Order Based -->
<record id="action_report_commercial_invoice" model="ir.actions.report">
    <field name="name">Commercial Invoice</field>
    <field name="model">sale.order</field>
    <field name="report_type">qweb-pdf</field>
    <field name="report_name">buz_commercial_invoice.report_commercial_invoice_sale_order_document</field>
    <field name="binding_model_id" ref="sale.model_sale_order"/>
    <field name="binding_type">report</field>
    <field name="paperformat_id" ref="paperformat_commercial_invoice"/>
</record>

<!-- Legacy Action: Account Move Based -->
<record id="action_report_commercial_invoice_account_move" model="ir.actions.report">
    <field name="name">Commercial Invoice (Invoice)</field>
    <field name="model">account.move</field>
    <field name="report_type">qweb-pdf</field>
    <field name="report_name">buz_commercial_invoice.report_commercial_invoice_document</field>
    <field name="binding_model_id" ref="account.model_account_move"/>
    <field name="binding_type">report</field>
    <field name="paperformat_id" ref="paperformat_commercial_invoice"/>
</record>
```

## Access Control

**File:** `security/ir.model.access.csv`

Controls model access permissions for different user groups.

## Manifest Configuration

**File:** `__manifest__.py`

```python
{
    'name': 'Custom Commercial Invoice Report',
    'version': '17.0.1.0.0',
    'depends': [
        'base',
        'account',
        'stock',
        'sale',      # NEW DEPENDENCY
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'report/paperformat.xml',
        'report/report_action.xml',
        'report/commercial_invoice_report.xml',
        'report/commercial_invoice_sale_order_report.xml',  # NEW
        'views/account_move_view.xml',
        'views/stock_picking_view.xml',
        'views/sale_order_view.xml',  # NEW
    ],
}
```

## Key Implementation Details

### 1. Number Generation Strategy

```python
def write(self, vals):
    """Write method override"""
    for record in self:
        if 'commercial_invoice_enabled' in vals and vals['commercial_invoice_enabled']:
            if not record.commercial_invoice_number:
                vals['commercial_invoice_number'] = self._get_commercial_invoice_number()
    return super().write(vals)
```

**Logic:**
- Only generates when checkbox changes from False to True
- Prevents duplicate generation if already assigned
- Atomic operation ensures uniqueness

### 2. Amount to Text Computation

```python
@api.depends('amount_total', 'currency_id')
def _compute_amount_text(self):
    for record in self:
        if record.currency_id:
            record.amount_text = record.currency_id.amount_to_text(record.amount_total)
```

**Features:**
- Depends on amount_total and currency_id
- Auto-updates when either field changes
- Uses Odoo's built-in amount_to_text method
- Supports all currencies

### 3. Print Action Method

```python
def action_print_commercial_invoice(self):
    self.ensure_one()
    if not self.commercial_invoice_enabled:
        raise UserError(_("Commercial Invoice is not enabled..."))
    if not self.commercial_invoice_number:
        raise UserError(_("Commercial Invoice number was not generated..."))
    return self.env.ref('buz_commercial_invoice.action_report_commercial_invoice').report_action(self)
```

**Safety Checks:**
1. Ensures single record (ensure_one)
2. Validates commercial invoice is enabled
3. Validates CIV number exists
4. Returns proper report action

## Integration Points

### 1. Sale Order Module Integration
- Extends `sale.order` model
- Adds tab to `sale.view_order_form`
- Adds column to `sale.view_order_tree`

### 2. Accounting Integration
- Extends `account.move` model
- Extends `account.view_move_form`
- Compatible with invoicing workflow

### 3. Stock Integration
- Extends `stock.picking` model
- Enables printing from deliveries

## Error Handling

**User Errors Raised:**
1. "Commercial Invoice is not enabled for this sales order." 
   - When printing without enabling checkbox
2. "Commercial Invoice number was not generated..."
   - When printing after disabling checkbox

**Validation:**
- Automatic via ensure_one() for single record operations
- Manual checks in action methods

## Performance Considerations

1. **Sequence Generation**: Uses ir.sequence.next_by_code() - atomic, DB-level locking
2. **Computed Fields**: amount_text stored on save (store=True) - indexed access
3. **Report Generation**: QWeb PDF - generated on demand
4. **Field Dependencies**: Minimal - only amount_total and currency_id

## Future Extensions

Possible enhancements:
1. Multi-company sequence support
2. Custom sequence format per company
3. CIV number on picking/delivery confirmation
4. Automatic invoice CIV sync
5. Email report templates
6. Archive/void CIV numbers
