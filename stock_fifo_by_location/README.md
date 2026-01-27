# Stock FIFO by Location

A comprehensive Odoo 17 module that extends the stock valuation system to support FIFO (First-In-First-Out) cost accounting on a per-location basis.

## Overview

By default, Odoo 17's stock accounting calculates COGS based on a company-wide FIFO queue, which can lead to inaccurate cost assignments when inventory is distributed across multiple storage locations. This module adds a `location_id` field to `stock.valuation.layer` records, enabling precise per-location FIFO tracking and correct cost accounting in multi-warehouse environments.

### Key Features

✅ **Per-Location FIFO Tracking** - Each valuation layer now tracks its storage location  
✅ **Transit Location Support** - Full support for inter-warehouse transfers via transit locations  
✅ **Automatic Location Capture** - Location is automatically populated during receiving, transferring, and delivering  
✅ **Shortage Handling** - Configurable policies for dealing with insufficient stock at a location  
✅ **Landed Cost Support** - Proportional landed cost allocation during internal transfers  
✅ **Migration Support** - Comprehensive migration scripts including transit location scenarios  
✅ **Comprehensive Tests** - Full test coverage including FIFO calculations and edge cases  
✅ **Security** - Proper access controls and audit trails  

## Installation

### Prerequisites

- Odoo 17 installed and running
- `stock` module enabled
- `stock_account` module enabled
- `stock_landed_costs` module enabled (for landed cost support)
- Write access to custom-addons folder

### Steps

1. **Copy module to Odoo addons folder:**
   ```bash
   cp -r stock_fifo_by_location /path/to/odoo17/custom-addons/
   ```

2. **Restart Odoo service:**
   ```bash
   sudo systemctl restart odoo17
   # or
   docker restart odoo17
   ```

3. **Install module via UI:**
   - Navigate to: **Apps** → **Update Apps List** (Ctrl+R in developer mode)
   - Search for: `Stock FIFO by Location`
   - Click **Install**

4. **Run migration (for existing data):**
   - Navigate to: **Inventory** → **Warehouse Management** → **Valuation Layers**
   - Use the `Populate Location IDs` server action (if available)
   - Or run the migration script via shell (see Migration section below)

## Architecture

### Data Model

#### stock.valuation.layer Extension

A new field is added to the existing `stock.valuation.layer` model:

```python
location_id = fields.Many2one(
    'stock.location',
    string='Stock Location',
    index=True,
    help='The stock location where this layer applies. Used for per-location FIFO tracking.',
    ondelete='restrict',
)
```

**Properties:**
- Indexed for fast lookups
- Cascading restrictions prevent orphaned references
- Mandatory in most scenarios (validated during moves)

### Module Components

```
stock_fifo_by_location/
├── __manifest__.py                 # Module metadata and dependencies
├── __init__.py                     # Package initialization
├── models/
│   ├── __init__.py                # Models package
│   ├── stock_valuation_layer.py   # SVL model extension with location support
│   ├── stock_move.py              # Stock move override for location capture
│   └── fifo_service.py            # FIFO calculation and validation service
├── security/
│   └── ir.model.access.csv        # Access control rules
├── data/
│   └── config_parameters.xml      # Module configuration defaults
├── views/
│   └── stock_valuation_layer_views.xml  # UI views with location field
├── migrations/
│   ├── __init__.py
│   └── populate_location_id.py    # Comprehensive migration with transit support
├── tests/
│   ├── __init__.py
│   └── test_fifo_by_location.py   # Unit and integration tests
└── README.md                       # This file
```

## Usage

### Basic Workflow

#### 1. Receiving Goods

When you create and validate a Purchase Order Receipt:

```
Supplier → Location A: 100 units @ $100/unit
```

**Result:** A new `stock.valuation.layer` is created with:
- `product_id` = Product X
- `location_id` = Location A
- `quantity` = 100
- `unit_cost` = 100

#### 2. Transferring Between Locations

Internal transfer from Location A to Location B:

```
Location A → Location B: 50 units
```

**Result:** 
- Location A layer quantity reduced by 50
- Location B layer created/updated with 50 units from the same cost basis

#### 3. Outgoing Delivery

When validating a Sales Order Delivery from Location A:

```
Location A → Customer: 30 units
```

**FIFO Consumption:**
- The system consumes from the oldest layers at Location A only
- COGS is calculated using Location A's FIFO queue
- Accounting entries reflect the per-location cost

### Configuration

Module settings are stored as configuration parameters. Access via:
**Settings → Technical → Parameters**

#### Available Settings

| Parameter | Values | Default | Description |
|-----------|--------|---------|-------------|
| `stock_fifo_by_location.shortage_policy` | `error`, `fallback` | `error` | How to handle insufficient stock at location |
| `stock_fifo_by_location.enable_validation` | `True`, `False` | `True` | Enable location validation during moves |
| `stock_fifo_by_location.debug_mode` | `True`, `False` | `False` | Enable debug logging |

#### Shortage Policies

**Mode: `error` (Default)**
- Blocks delivery if insufficient stock at specified location
- Prevents inadvertent shipments from wrong warehouses
- Raises `UserError` with shortage details

**Mode: `fallback`**
- Allows pulling inventory from alternative locations
- Logs fallback usage for audit
- Requires manual configuration per move

### Service Methods

The `fifo.service` model provides utility methods for custom code:

#### Get FIFO Queue
```python
queue = env['fifo.service'].get_valuation_layer_queue(
    product_id=product,
    location_id=location,
    company_id=company.id
)
```

#### Calculate FIFO Cost
```python
cost_info = env['fifo.service'].calculate_fifo_cost(
    product_id=product,
    location_id=location,
    quantity=30,  # units to consume
    company_id=company.id
)
# Returns: {
#   'cost': 3000.0,           # Total cost
#   'qty': 30.0,              # Quantity consumed
#   'unit_cost': 100.0,       # Average unit cost
#   'layers': [               # Detail per layer
#     {
#       'layer_id': 123,
#       'qty_consumed': 30.0,
#       'layer_unit_cost': 100.0,
#       'cost': 3000.0
#     }
#   ]
# }
```

#### Validate Availability
```python
result = env['fifo.service'].validate_location_availability(
    product_id=product,
    location_id=location,
    quantity=30,
    allow_fallback=False,
    company_id=company.id
)
# Returns: {
#   'available': False,
#   'available_qty': 20.0,
#   'needed_qty': 30.0,
#   'shortage': 10.0,
#   'fallback_locations': [...]
# }
```

## Migration

### For Existing Installations

If you're installing this module on an existing Odoo instance with prior stock movements, you need to populate the `location_id` field for existing valuation layers.

#### Quick Start Migration

```bash
# Access Odoo shell
cd /path/to/odoo17
python -m odoo.bin shell -d your_database

# Run comprehensive migration (includes transit locations)
from odoo.addons.stock_fifo_by_location.migrations import populate_location_id
result = populate_location_id.populate_location_id(env)
# Output shows migration progress and any items needing manual review

# Check results
print(f"Total: {result['total']}")
print(f"Successful: {result['successful']}")
print(f"Failed: {result['failed']}")
```

#### Transit Location Migration

For systems using transit locations in inter-warehouse transfers, use the specialized migration:

```bash
# Analyze transit locations first
from odoo.addons.stock_fifo_by_location.migrations import populate_location_id
stats = populate_location_id.analyze_transit_locations(env)

# Run transit-specific migration
result = populate_location_id.populate_transit_location_layers(env)

# Review transit statistics
print(f"Internal → Transit: {result['stats']['internal_to_transit']}")
print(f"Transit → Internal: {result['stats']['transit_to_internal']}")
print(f"Transit → Transit: {result['stats']['transit_to_transit']}")
```

**Transit Location Scenarios Supported:**
- ✅ Internal → Transit (warehouse shipments)
- ✅ Transit → Internal (warehouse receipts)
- ✅ Transit → Transit (inter-transit moves)
- ✅ Supplier → Transit (direct imports)
- ✅ Transit → Customer (direct deliveries)

For detailed transit migration guide, see: [TRANSIT_LOCATION_MIGRATION_GUIDE.md](TRANSIT_LOCATION_MIGRATION_GUIDE.md)

#### Option 1: Via Python Shell (Recommended)

```bash
# Access Odoo shell
cd /path/to/odoo17
python -m odoo.bin shell -d your_database

# Run migration
from odoo.addons.stock_fifo_by_location.migrations import populate_location_id
result = populate_location_id.populate_location_id(env)
# Output shows migration progress and any items needing manual review
```

#### Option 2: Via Server Action (UI)

1. Navigate to: **Inventory** → **Valuation Layers**
2. Look for server action: **Populate Location IDs**
3. Click and execute

#### Option 3: Direct SQL (For Large Datasets)

⚠️ **Warning:** This method doesn't handle transit locations properly. Use Python migration for transit scenarios.

```sql
-- Populate from stock_move relationship (basic cases only)
UPDATE stock_valuation_layer svl
SET location_id = sm.location_dest_id
FROM stock_move sm
WHERE svl.stock_move_id = sm.id
  AND svl.location_id IS NULL;

-- Verify completeness
SELECT COUNT(*) FROM stock_valuation_layer WHERE location_id IS NULL;
```

### Migration Testing

A comprehensive test script is available:

```bash
# Run all migration tests
cd /opt/instance1/odoo17/custom-addons
python -m odoo.bin shell -d your_database
>>> exec(open('test_transit_migration.py').read())
```

Tests include:
- Transit location analysis
- Transit-specific migration
- Full migration
- Consistency verification

### Migration Details

The migration script attempts to derive `location_id` using this priority:

1. **Direct link from stock.move** - destination location
2. **Fallback from stock.move.line** - destination location  
3. **Temporal matching** - finds similar moves within ±1 day window
4. **Manual review** - logs items that cannot be auto-resolved

**Items requiring manual review** are reported with layer IDs for investigation.

## Testing

The module includes comprehensive unit and integration tests covering all major scenarios.

### Running Tests

#### Via Pytest

```bash
cd /path/to/odoo17
pytest -xvs addons/stock_fifo_by_location/tests/test_fifo_by_location.py
```

#### Via Odoo Test Runner

```bash
python -m odoo.bin -d your_database -m stock_fifo_by_location --test-enable
```

#### Via UI

1. **Activate Developer Mode:** Settings → Developer Tools → Activate
2. Navigate to: **Apps** → **Stock FIFO by Location**
3. Click **Tests** (if available)

### Test Coverage

| Scenario | Test | Status |
|----------|------|--------|
| Incoming receipt to location | `test_incoming_receipt_location_captured` | ✅ |
| FIFO queue per-location isolation | `test_fifo_queue_retrieval_by_location` | ✅ |
| Cost calculation (FIFO order) | `test_fifo_cost_calculation_at_location` | ✅ |
| Multiple cost bases per location | `test_multiple_locations_isolated_fifo` | ✅ |
| Shortage handling (error mode) | `test_location_shortage_error_mode` | ✅ |
| Shortage handling (fallback mode) | `test_location_shortage_fallback_mode` | ✅ |
| Internal transfers | `test_internal_transfer_location_assignment` | ✅ |

### Example Test Scenario

**Setup:**
```python
# Product P, two incoming receipts to Location A:
Receipt 1 (2025-01-01): qty 10, cost $100 → SVL1
Receipt 2 (2025-01-10): qty 5, cost $120 → SVL2

# Validate sale from Location A: qty 12
```

**Expected Result:**
```python
# FIFO consumption:
# - 10 units from SVL1 @ $100 = $1,000
# - 2 units from SVL2 @ $120 = $240
# Total COGS = $1,240

# Journal Entry (simplified):
# Debit: COGS          $1,240
#   Credit: Inventory            $1,240
```

## Known Limitations & Considerations

### Multi-Company Behavior

✅ **Supported** - Module respects company boundaries in FIFO calculations  
- Each company has separate valuation layer queues
- Location FIFO only applies within same company

### Multi-Warehouse

✅ **Fully Supported** - Designed for multi-warehouse scenarios  
- Each warehouse location has isolated FIFO queue
- No cross-warehouse mixing in FIFO calculations
- **Transit Location Support:** Full FIFO tracking during inter-warehouse transfers
  - Warehouse A → Transit → Warehouse B properly tracked
  - Transit locations maintain separate FIFO queues
  - Accurate cost tracking throughout the transfer process

### Negative Quantities

⚠️ **Handled but Logged** - Negative quantities in layers are:
- Excluded from FIFO queue calculations
- Logged for investigation
- Typically indicate inventory adjustments

### Rounding

✅ **Precision Preserved** - Module uses Odoo's precision settings:
- Product Price precision respected
- Floating-point comparisons use defined tolerance
- Rounding applied consistently across calculations

### Standard Costing

❌ **Not Supported in FIFO Mode** - Products using standard costing:
- Should not use this module
- Will have no effect on standard-costing products
- Maintains backward compatibility

### Scrap & Adjustments

✅ **Handled** - Scrap/loss locations:
- If configured as internal, tracked with location_id
- If scrap location, may not have meaningful FIFO
- Adjustments preserved with location context

## Accounting Impact

### Journal Entries

The module doesn't directly create journal entries but provides accurate data for Odoo's accounting engine:

**Receiving:**
```
Debit: Inventory (Location A)
  Credit: Accounts Payable
```

**Delivery (from Location A):**
```
Debit: Cost of Goods Sold
  Credit: Inventory (Location A) [using Location A's FIFO cost]
```

**Internal Transfer (A→B):**
```
Debit: Inventory (Location B)
  Credit: Inventory (Location A)
```

### Cost Flows

- **Incoming:** All goods record location_id at receipt
- **Transfers:** Location updated, cost basis maintained
- **Outgoing:** COGS drawn from destination location's FIFO queue
- **Adjustments:** Location preserved for audit trail

## Troubleshooting

### Issue: Layers Missing location_id After Install

**Solution:**
1. Run migration script (see Migration section)
2. Check if `enable_validation` is True
3. Review logs for errors during layer creation

**SQL Check:**
```sql
SELECT COUNT(*) FROM stock_valuation_layer WHERE location_id IS NULL;
```

### Issue: Unexpected COGS Amounts

**Debugging Steps:**
1. Enable debug_mode in settings
2. Check valuation layer queue for product/location:
   ```python
   layers = env['fifo.service'].get_valuation_layer_queue(product, location)
   for layer in layers:
       print(f"Layer {layer.id}: qty={layer.quantity}, cost={layer.unit_cost}")
   ```
3. Verify shortage policy is set correctly
4. Check for negative quantities in queue

### Issue: Migration Fails on Existing Data

**Causes & Solutions:**
- Orphaned layers (no related move):
  - Review SQL check above
  - Manually assign location if move cannot be found
  - Or set to default warehouse location
  
- Circular location relationships:
  - Validate location hierarchy via UI
  - Use SQL to check: `SELECT * FROM stock_location WHERE location_id = id;`

## Development & Extending

### Adding Custom Behavior

Extend the module by inheriting the service:

```python
# In your custom module:

class FifoServiceCustom(models.AbstractModel):
    _inherit = 'fifo.service'
    
    @api.model
    def get_valuation_layer_queue(self, product_id, location_id, company_id=None):
        # Custom filtering or logging
        queue = super().get_valuation_layer_queue(product_id, location_id, company_id)
        # Your custom logic here
        return queue
```

### Overriding Location Logic

To customize how location is determined for layers:

```python
# In your custom module:

class StockMoveFifoCustom(models.Model):
    _inherit = 'stock.move'
    
    def _get_fifo_valuation_layer_location(self):
        # Your custom location determination logic
        return super()._get_fifo_valuation_layer_location()
```

## Support & Maintenance

### Common Operations

**Query: All layers for a product across all locations**
```sql
SELECT * FROM stock_valuation_layer 
WHERE product_id = <product_id>
ORDER BY location_id, create_date;
```

**Query: Total inventory value by location**
```sql
SELECT 
    location_id,
    COALESCE(location.name, 'Unassigned') as location,
    SUM(quantity) as total_qty,
    SUM(value) as total_value
FROM stock_valuation_layer
LEFT JOIN stock_location location ON stock_valuation_layer.location_id = location.id
GROUP BY location_id, location.name;
```

## Performance Notes

- `location_id` is indexed for fast FIFO queue retrieval
- Recommend periodic maintenance: `VACUUM ANALYZE stock_valuation_layer`
- Monitor for orphaned layers: `SELECT * FROM stock_valuation_layer WHERE location_id IS NULL`

## License

LGPL-3 - See LICENSE file for details

## Changelog

### Version 17.0.1.0.0 (Current Release)

#### Core Features
- ✨ Added location_id field to stock.valuation.layer
- ✨ Per-location FIFO queue management
- ✨ Automatic location capture during stock moves
- ✨ Shortage handling policies (error/fallback)
- ✨ Migration script for existing layers
- ✨ Comprehensive test suite
- 📖 Full documentation and examples

#### Landed Cost Support (NEW)
- ✨ Per-location landed cost tracking
- ✨ Automatic landed cost allocation during internal transfers
- ✨ Proportional landed cost distribution
- ✨ Audit trail for all allocations
- ✨ New service methods: `calculate_fifo_cost_with_landed_cost()`
- ✨ 3 new models for landed cost management
- ✨ Comprehensive landed cost tests
- 📖 Landed cost documentation

#### Technical Additions
- 2 new models: `stock.valuation.layer.landed.cost`, `stock.landed.cost.allocation`
- 3 enhanced models: `stock.valuation.layer`, `stock.landed.cost`, `stock.move`
- New dependency: `stock_landed_costs`
- Backward compatible with existing installations

## Documentation

- **[README.md](README.md)** - This file, module overview
- **[LANDED_COST_SUPPORT.md](LANDED_COST_SUPPORT.md)** - Detailed landed cost feature
- **[LANDED_COST_IMPLEMENTATION_GUIDE.md](LANDED_COST_IMPLEMENTATION_GUIDE.md)** - Step-by-step implementation guide
- **[ANALYSIS_STOCK_FIFO_BY_LOCATION.md](../ANALYSIS_STOCK_FIFO_BY_LOCATION.md)** - Architecture analysis
- **Tests** - `tests/test_fifo_by_location.py` (482+ lines)

## Support

For issues, questions, or improvements:

1. Check this README for common scenarios
2. Review test cases in `tests/test_fifo_by_location.py`
3. Read landed cost documentation: `LANDED_COST_SUPPORT.md`
4. Check module logs: **Settings → Technical → Logs**
5. Contact development team with:
   - Odoo version
   - Module version
   - Affected products/locations
   - Error messages or behavior description

