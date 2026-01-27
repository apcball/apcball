# Code Reference - Export Filter Implementation

## Method Reference

### `stock.current.export.wizard.action_export_excel()`

**Purpose**: Collect filter parameters and trigger Excel report generation

**Parameters**: Self (wizard record)

**Returns**: Report action dict

**Example**:
```python
def action_export_excel(self):
    """Export filtered stock report to Excel"""
    filter_data = {
        'date_from': self.date_from,
        'date_to': self.date_to,
        'location_ids': self.location_ids.ids if self.location_ids else [],
        'product_ids': self.product_ids.ids if self.product_ids else [],
        'category_ids': self.category_ids.ids if self.category_ids else [],
    }
```

---

### `stock.current.export.wizard.get_filtered_stock_data()`

**Purpose**: Retrieve stock data with specified filters

**Parameters**:
- `date_from` (date) - Required: Start date
- `date_to` (date) - Required: End date
- `location_ids` (list, optional) - Location IDs to filter
- `product_ids` (list, optional) - Product IDs to filter
- `category_ids` (list, optional) - Category IDs to filter

**Returns**: List of dicts with stock data

**Example Usage**:
```python
data = self.env['stock.current.export.wizard'].get_filtered_stock_data(
    date_from=date(2024, 11, 1),
    date_to=date(2024, 11, 30),
    location_ids=[1, 2, 3],
    product_ids=[10, 20, 30],
    category_ids=[5]
)

# Returns:
[
    {
        'id': 1,
        'product_id': 10,
        'location_id': 1,
        'category_id': 5,
        'quantity': 100.0,
        'unit_cost': 50.0,
        'total_value': 5000.0,
        ...
    },
    ...
]
```

---

### Data Structure

**Output Record Structure**:
```python
{
    'id': int,                          # Record ID
    'product_id': int,                  # Product ID
    'location_id': int,                 # Location ID
    'category_id': int,                 # Category ID
    'uom_id': int,                      # Unit of Measure ID
    'quantity': float,                  # Current on-hand quantity
    'free_to_use': float,               # Available (not reserved)
    'incoming': float,                  # Pending incoming qty
    'outgoing': float,                  # Pending outgoing qty
    'unit_cost': float,                 # Unit cost from product
    'total_value': float,               # quantity × unit_cost
}
```

---

## SQL Query Structure

### Base Query
```sql
SELECT
    sq.id,
    sq.product_id,
    sq.location_id,
    pt.categ_id AS category_id,
    pt.uom_id,
    COALESCE(sq.quantity, 0) AS quantity,
    COALESCE(sq.quantity, 0) AS free_to_use,
    COALESCE(incoming.qty, 0) AS incoming,
    COALESCE(outgoing.qty, 0) AS outgoing,
    COALESCE(pt.list_price, 0) AS unit_cost,
    COALESCE(sq.quantity, 0) * COALESCE(pt.list_price, 0) AS total_value
FROM stock_quant sq
JOIN product_product pp ON pp.id = sq.product_id
JOIN product_template pt ON pt.id = pp.product_tmpl_id
JOIN stock_location sl ON sl.id = sq.location_id
LEFT JOIN ... incoming ...
LEFT JOIN ... outgoing ...
WHERE sl.usage = 'internal'
```

### Dynamic Filters Applied
```sql
-- If location_ids provided:
AND sq.location_id IN (1, 2, 3)

-- If product_ids provided:
AND sq.product_id IN (10, 20, 30)

-- If category_ids provided:
AND pt.categ_id IN (5, 6, 7)
```

---

## Field Definitions

### Date Fields
```python
date_from = fields.Date(
    string="Date From",
    required=True,
    default=fields.Date.context_today
)

date_to = fields.Date(
    string="Date To",
    required=True,
    default=fields.Date.context_today
)
```

### Many2many Filter Fields
```python
location_ids = fields.Many2many(
    'stock.location',                              # Related model
    'stock_export_wizard_location_rel',            # Junction table
    'wizard_id',                                   # Foreign key in junction table
    'location_id',                                 # Related field in junction table
    string='Locations',
    domain=[('usage', '=', 'internal')],
    help='Leave empty to include all internal locations'
)

product_ids = fields.Many2many(
    'product.product',
    'stock_export_wizard_product_rel',
    'wizard_id',
    'product_id',
    string='Products',
    help='Leave empty to include all products'
)

category_ids = fields.Many2many(
    'product.category',
    'stock_export_wizard_category_rel',
    'wizard_id',
    'category_id',
    string='Product Categories',
    help='Leave empty to include all categories'
)
```

---

## XML Form Definition

### Form Structure
```xml
<form string="Export Current Stock">
    <group>
        <group string="Date Range">
            <field name="date_from"/>
            <field name="date_to"/>
        </group>
        <group string="Filters (Optional)">
            <field name="location_ids" widget="many2many_tags"/>
            <field name="product_ids" widget="many2many_tags"/>
            <field name="category_ids" widget="many2many_tags"/>
        </group>
    </group>
    <footer>
        <button name="action_export_excel" type="object" class="btn-primary"/>
    </footer>
</form>
```

### Report Action
```xml
<record id="action_report_stock_current_xlsx" model="ir.actions.report">
    <field name="name">Current Stock Excel Report</field>
    <field name="model">stock.current.export.wizard</field>
    <field name="report_type">xlsx</field>
    <field name="report_name">buz_stock_current_report.stock_current_report_xlsx</field>
</record>
```

---

## Excel Report Generation

### Format Definitions
```python
bold = workbook.add_format({'bold': True})
header_format = workbook.add_format({
    'bold': True,
    'bg_color': '#D3D3D3'  # Light gray
})
number_format = workbook.add_format({
    'num_format': '#,##0.00'  # 2 decimals + thousand separator
})
```

### Column Structure
```python
headers = [
    'Location',      # A
    'Product',       # B
    'Category',      # C
    'Qty On Hand',   # D
    'Free to Use',   # E
    'Incoming',      # F
    'Outgoing',      # G
    'Unit Cost',     # H
    'Total Value',   # I
    'UoM'            # J
]

# Column widths
sheet.set_column('A:A', 25)  # Location
sheet.set_column('B:B', 30)  # Product
sheet.set_column('C:C', 20)  # Category
sheet.set_column('D:H', 15)  # Numeric columns
sheet.set_column('I:I', 15)  # Total Value
sheet.set_column('J:J', 12)  # UoM
```

---

## Integration Examples

### Call From Code
```python
# Get wizard model
wizard = self.env['stock.current.export.wizard'].create({
    'date_from': date(2024, 11, 1),
    'date_to': date(2024, 11, 30),
    'location_ids': [(6, 0, [1, 2, 3])],
    'product_ids': [(6, 0, [10, 20, 30])],
})

# Trigger export
result = wizard.action_export_excel()
```

### Access via API
```python
# REST API call (pseudocode)
POST /web/report/buz_stock_current_report.stock_current_report_xlsx
{
    'date_from': '2024-11-01',
    'date_to': '2024-11-30',
    'location_ids': [1, 2, 3],
    'product_ids': [10, 20, 30],
    'category_ids': [5]
}
```

---

## Error Handling

### In Wizard Model
```python
try:
    filter_data = {...}
    report_action = self.env.ref(...).report_action(self, data=filter_data)
    return report_action
except Exception as e:
    _logger.error(f"Error generating Excel export: {e}")
    raise
```

### In Report Generator
```python
try:
    sheet = workbook.add_worksheet('Current Stock')
    # ... generate report ...
except Exception as e:
    _logger.error(f"Error generating Excel report: {e}")
    raise
```

---

## Logging

### Key Log Messages

```python
# Wizard export initiation
_logger.info(f"Exporting stock report with filters - Date: {date_from} to {date_to}")

# Successful export
_logger.info("Successfully generated Excel export action")

# Report generation start
_logger.info("Generating Current Stock Excel Report with filters")

# Filter application
_logger.info(f"Report filters - Date: {date_from} to {date_to}, Locations: {location_ids}, Products: {product_ids}, Categories: {category_ids}")

# Data retrieval
_logger.info("Fetching filtered stock data")
_logger.info(f"Retrieved {len(results)} filtered stock records")

# Completion
_logger.info("Successfully completed Excel report generation")

# Errors
_logger.error(f"Error generating Excel export: {e}")
_logger.error(f"Error generating Excel report: {e}")
```

---

## Database Schema

### Junction Tables Created

**stock_export_wizard_location_rel**
```sql
CREATE TABLE stock_export_wizard_location_rel (
    wizard_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    PRIMARY KEY (wizard_id, location_id),
    FOREIGN KEY (wizard_id) REFERENCES stock_current_export_wizard(id),
    FOREIGN KEY (location_id) REFERENCES stock_location(id)
);
```

**stock_export_wizard_product_rel**
```sql
CREATE TABLE stock_export_wizard_product_rel (
    wizard_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    PRIMARY KEY (wizard_id, product_id),
    FOREIGN KEY (wizard_id) REFERENCES stock_current_export_wizard(id),
    FOREIGN KEY (product_id) REFERENCES product_product(id)
);
```

**stock_export_wizard_category_rel**
```sql
CREATE TABLE stock_export_wizard_category_rel (
    wizard_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    PRIMARY KEY (wizard_id, category_id),
    FOREIGN KEY (wizard_id) REFERENCES stock_current_export_wizard(id),
    FOREIGN KEY (category_id) REFERENCES product_category(id)
);
```

---

## Performance Considerations

### Query Optimization
- Single query with JOINs instead of multiple queries
- Date range filtering on movements reduces data scanned
- Specific filters (location, product) significantly improve speed
- Indexes recommended on: `stock_quant(location_id)`, `stock_quant(product_id)`, `product_template(categ_id)`

### Memory Usage
- Data retrieved as dict lists (memory efficient)
- Large result sets (10,000+) may require pagination
- Excel file generated in memory before download

### Recommended Filters
- For large datasets: Always use location filter
- For performance: Combine location + category filters
- Time-based: Use narrower date ranges when possible
