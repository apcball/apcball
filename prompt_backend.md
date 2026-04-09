# Objective
Create an Odoo 17 module to export stock picking (receipt, delivery, internal transfer) into Excel.

---

## Model Extension: stock.picking

Add button:
- action_export_excel()

---

## Export Engine (service layer)

Create class:
export.engine

Methods:

### get_picking_data(picking_ids)

Return normalized structure:

[
  {
    "document": picking.name,
    "type": picking.picking_type_code,  # incoming / outgoing / internal
    "date": picking.scheduled_date,
    "partner": picking.partner_id.name,
    "source_location": picking.location_id.complete_name,
    "dest_location": picking.location_dest_id.complete_name,
    "lines": [
        {
          "default_code": move.product_id.default_code,
          "product_name": move.product_id.display_name,
          "qty": move.quantity_done,
          "uom": move.product_uom.name,
          "cost": get_fifo_cost(move),
          "lot": lot_name,
        }
    ]
  }
]

---

### get_fifo_cost(move)

Use:
stock.valuation.layer

Logic:
- find valuation layers linked to move_id
- sum(value) / sum(quantity)

Return unit_cost

---

## Excel Builder

Use xlsxwriter

Sheet structure:

HEADER:
Document | Type | Date | Partner | Source | Destination

LINES:
Product Code | Product Name | Qty | UOM | Cost | Lot

---

## Output

Return binary:
base64 encoded file

filename:
stock_transfer_<date>.xlsx

---

## Optional (Advanced)

- group by document (multi-sheet)
- add summary sheet
- support multi-company