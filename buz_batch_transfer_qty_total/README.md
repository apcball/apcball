# Batch Transfer Quantity Total

This module adds a total quantity field to batch transfers in Odoo 17, providing users with a quick overview of the total quantity of all products within a batch.

## Features

- Displays the total quantity of all products in a batch transfer
- Shows the total in the form view under a "Summary" section
- Adds a summary column in the tree/list view
- Displays total quantity in the kanban view
- Uses quantity_done if available, otherwise falls back to product_uom_qty
- Excludes cancelled transfers from the total calculation
- Compatible with Odoo 17 Community & Enterprise editions

## Installation

1. Copy the module to your Odoo addons directory
2. Update the module list in Odoo
3. Install the module from the Apps menu

## Usage

Once installed, the total quantity will be automatically calculated and displayed:

1. **Form View**: Navigate to any batch transfer form to see the total quantity displayed in the "Summary" group below the transfer list.

2. **Tree View**: The total quantity column is available in the batch transfer list view with a sum at the bottom.

3. **Kanban View**: The total quantity is displayed on each batch transfer card.

## Technical Details

### Model Extension

The module extends the `stock.picking.batch` model with a new computed field:

```python
total_qty = fields.Float(
    string="Total Quantity",
    compute="_compute_total_qty",
    store=False,
    digits=(16, 4)
)
```

### Calculation Logic

The total quantity is calculated by:
1. Iterating through all transfers (pickings) in the batch
2. Skipping cancelled transfers
3. For each transfer, summing the quantities from all move lines
4. Using `quantity_done` if available, otherwise `product_uom_qty`

### View Customizations

The module modifies the following views:
- Form view: Adds a "Summary" group with the total quantity field
- Tree view: Adds the total quantity column with sum functionality
- Kanban view: Displays total quantity on each card
- Search view: Adds grouping by total quantity option

## Compatibility

- Odoo Version: 17.0
- Dependencies: stock

## License

This module is licensed under LGPL-3.

## Support

For support and inquiries, please contact BUZ at https://www.buz.co.th