# Transfer Wizard Implementation - Quick Reference

## 🎯 What Was Implemented

The `buz_stock_current_report` module now provides a complete **Stock Transfer Management System** with the following workflow:

### User Journey

```
┌─────────────────────────────────────────────────────────────┐
│ 1. CURRENT STOCK VIEW                                       │
│    - Navigate to Inventory > Current Stock Report           │
│    - See all products with quantities by location           │
│    - Use sidebar to filter by warehouse/location            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. SELECT PRODUCTS                                          │
│    - Check boxes to select products to transfer             │
│    - Button shows: "Create Transfer (3)" showing count      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. TRANSFER WIZARD OPENS                                    │
│    - Shows selected products pre-populated                  │
│    - Source location auto-filled (if all from same loc)     │
│    - User selects destination location                      │
│    - User adjusts quantities if needed                      │
│    - Optional: Enable immediate transfer                    │
│    - Optional: Add transfer notes                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. VALIDATION & CREATION                                    │
│    ✓ Validates quantities against available stock           │
│    ✓ Creates stock.picking (draft state)                    │
│    ✓ Optionally auto-confirms if immediate=True             │
│    ✓ Shows created transfer in form view                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Core Components

### 1. Transfer Wizard Model
**File**: `models/stock_current_transfer_wizard.py`

```python
class StockCurrentTransferWizard(models.TransientModel):
    # Main wizard form
    source_location_id          # Read-only, auto-populated
    destination_location_id     # Required, user selects
    picking_type_id            # Read-only internal transfer type
    immediate_transfer         # Boolean, auto-confirm if true
    scheduled_date             # Date field for future transfers
    notes                       # Text field for transfer notes
    line_ids                    # One2many to transfer lines
    
    # Key Methods:
    default_get()              # Pre-populates from context
    _get_picking_type()        # Gets internal transfer type
    action_create_transfer()   # Creates stock.picking + moves

class StockCurrentTransferWizardLine(models.TransientModel):
    # Transfer line details
    wizard_id                   # Parent wizard
    product_id                 # Product to transfer
    source_location_id         # Where from
    available_quantity         # Read-only display
    quantity_to_transfer       # User enters amount
    uom_id                     # Unit of measure
```

### 2. Export Wizard Model
**File**: `models/stock_current_export_wizard.py`

```python
class StockCurrentExportWizard(models.TransientModel):
    date_from                  # Optional date range start
    date_to                    # Optional date range end
    location_ids               # Multi-select locations
    product_ids                # Multi-select products
    category_ids               # Multi-select categories
    
    # Key Methods:
    get_filtered_stock_data()  # Returns filtered records
    action_export_excel()      # Triggers Excel export
```

### 3. Stock Report View Model
**File**: `models/stock_current_report.py`

```python
class StockCurrentReport(models.Model):
    # Read-only SQL view with real-time stock data
    product_id
    location_id
    warehouse_id
    quantity                   # On-hand
    free_to_use               # Available after moves
    incoming                  # Pending inbound
    outgoing                  # Pending outbound
    unit_cost                 # From product (cost viewer only)
    total_value               # Cost viewer only
    
    # Key Methods:
    action_transfer_single_product()    # Quick transfer button
    action_view_product_moves()         # View stock moves
    init()                              # Creates SQL view
```

---

## 🎨 UI Components

### Views Provided

| View | Type | Purpose |
|------|------|---------|
| Current Stock View | Kanban + Tree | Main dashboard with warehouse sidebar |
| Stock Detail | Form | Detailed stock information |
| Transfer Wizard | Form | Multi-product transfer creation |
| Export Wizard | Form | Excel export with filters |

### Menu Structure

```
Inventory
└── Current Stock Report
    ├── Current Stock View (main dashboard)
    ├── Create Transfer (wizard entry)
    └── Export Stock to Excel (export wizard)
```

### Top Menu Button

- **"Create Transfer (N)"** button appears on Current Stock View
  - Shows count of selected products
  - Enabled only when products selected
  - Opens transfer wizard with selected data

---

## 🔧 Technical Details

### JavaScript Integration

**File**: `static/src/js/stock_current_report.js`

```javascript
// Manages product selection
ProductSelectionManager {
    selectedProducts: Map
    toggleProductSelection(productData)
    getSelectedProducts()
    getSelectedCount()
    clearSelection()
    onSelectionChange(callback)
}

// Kanban view enhancements
StockKanbanController {
    setupProductSelection()      // Attach checkbox listeners
    renderTransferButton()        // Add button to toolbar
    onTransferSelected()          // Handle multi-select transfer
    onTransferSingleProduct()     // Single product quick transfer
    openTransferWizard()          // Pass data to wizard
}
```

### Context Data Format

When JavaScript sends selected products to wizard:
```javascript
[
    {
        productId: 123,
        locationId: 456,
        quantity: 100.0,
        uomId: 1,
        productName: "Product A",
        locationName: "Location X"
    },
    // ... more products
]
```

Wizard's `default_get()` accepts both camelCase (JS) and snake_case (Python) keys.

---

## ✅ Validation Rules

### Transfer Wizard Validations

```
✓ At least 1 product selected
✓ Source location is set
✓ Destination location is different from source
✓ Destination location is internal
✓ Transfer quantity > 0 for each product
✓ Transfer quantity ≤ available quantity
✓ Picking type is available
```

### Line Item Validations

```
✓ Each line has product_id
✓ Each line has source_location_id
✓ Quantity constraints enforced
✓ UoM is valid
✓ Available quantity is displayed
```

---

## 🔐 Security

**Access Control Groups**:

| Group | Permission | Access |
|-------|-----------|--------|
| stock_user | Read | View current stock |
| stock_manager | Read | Full access |
| stock_cost_viewer | Read | See cost fields (unit_cost, total_value) |

**Model Access**:
- `stock.current.report`: Read-only access
- Transfer wizard: All users can create transfers
- Export wizard: All users can export

---

## 📋 API Examples

### Create Transfer via Python

```python
# In a Python script or method:
wizard = self.env['stock.current.transfer.wizard'].create({
    'source_location_id': 5,
    'destination_location_id': 10,
    'immediate_transfer': True,
    'line_ids': [
        (0, 0, {
            'product_id': 123,
            'source_location_id': 5,
            'quantity_to_transfer': 100,
            'uom_id': 1,
        }),
    ]
})
result = wizard.action_create_transfer()
# Returns: {picking record with moves}
```

### Query Current Stock via Python

```python
# Get all products in a location
stocks = self.env['stock.current.report'].search([
    ('location_id', '=', location_id),
    ('quantity', '>', 0)
])

for stock in stocks:
    print(f"{stock.product_id.name}: {stock.quantity} {stock.uom_id.name}")
    print(f"  Free to Use: {stock.free_to_use}")
    print(f"  Incoming: {stock.incoming}")
    print(f"  Value: {stock.total_value}")
```

### Export Stock Data via Python

```python
# Manually trigger export
export_wizard = self.env['stock.current.export.wizard'].create({
    'date_from': '2024-01-01',
    'date_to': '2024-01-31',
    'location_ids': [(6, 0, [5, 10, 15])],
})
data = export_wizard.get_filtered_stock_data()
action = export_wizard.action_export_excel()
```

---

## 🚀 Deployment

### Installation Steps

1. **Enable module** in Odoo:
   ```bash
   # In Odoo settings or via CLI
   pip install report_xlsx  # Ensure dependency is installed
   ```

2. **Update module list** in Odoo backend or:
   ```bash
   odoo -d database --update=all
   ```

3. **Access the feature**:
   - Navigate to **Inventory > Current Stock Report > Current Stock View**
   - Select products and click "Create Transfer"

### Dependencies

- **stock**: Odoo's standard inventory module
- **report_xlsx**: For Excel export functionality

---

## 🧪 Testing Checklist

- ✅ Transfer wizard opens with selected products
- ✅ Source location auto-populates when all products from same location
- ✅ Quantity validation works (zero, negative, exceeds available)
- ✅ Destination location validation (internal only, must differ)
- ✅ Stock.picking created in draft state
- ✅ Stock moves created for each line
- ✅ Immediate transfer auto-confirms if enabled
- ✅ Export wizard filters work correctly
- ✅ Excel export contains correct data
- ✅ Security restrictions enforced (cost viewer)
- ✅ Menu items appear correctly
- ✅ Kanban checkboxes track selection state

---

## 📊 Database Impact

### New Tables (Transient - not persistent)
- `stock_current_transfer_wizard` (temporary session data)
- `stock_current_transfer_wizard_line` (temporary session data)
- `stock_current_export_wizard` (temporary session data)

### Views Created
- `stock_current_report` (SQL view - real-time stock data)

### Existing Tables Modified
- `stock_picking`: New records created when transfer is submitted
- `stock_move`: New records created for each transfer line

---

## 🐛 Known Limitations & Future Work

### Current Limitations
1. Bulk transfers create single picking with multiple moves
2. No scheduled transfer workflow (but dates can be set)
3. No approval workflow (auto-confirms based on user choice)
4. Export filters are AND-based (no OR logic)

### Future Enhancements
- [ ] Transfer approval workflow
- [ ] Batch scheduling
- [ ] Historical stock analytics
- [ ] Inventory discrepancy detection
- [ ] Automated reorder alerts
- [ ] Multi-warehouse consolidation

---

## 📞 Support

For issues or questions:

1. Check **QUICK_START.md** for basic usage
2. Review **TESTING_GUIDE.md** for validation
3. See **TECHNICAL_SPECIFICATION_TRANSFER.md** for deep dive
4. Check **ARCHITECTURE_DIAGRAM.md** for system design

---

## ✨ Implementation Status

**Status**: ✅ **COMPLETE AND READY FOR PRODUCTION**

All components:
- ✅ Implemented
- ✅ Tested
- ✅ Validated
- ✅ Documented

**Last Updated**: November 14, 2024  
**Module Version**: 17.0.1.0.0
