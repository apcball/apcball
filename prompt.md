# Module: sale_invoice_policy_bypass

## Objective
Create an Odoo 17 module that bypasses the invoicing policy restriction on Sale Orders.

The goal is to allow users to create invoices regardless of:
- Product invoicing policy (Ordered quantities vs Delivered quantities)
- Delivery status
- Quantity delivered

This is intended for temporary use (e.g., accounting backlog processing), and the module will be uninstalled afterward.

---

## Functional Requirements

### 1. Override Invoice Creation Logic

Override the method:
- `sale.order._create_invoices()`

And bypass:
- `_get_invoiceable_lines()`
- `_get_invoice_qty()`

### Expected Behavior:
- All sale order lines (excluding display types like section/note) should be invoiceable
- Ignore:
  - delivered_qty
  - invoicing_policy
  - qty_to_invoice

---

### 2. Logic Rules

For each `sale.order.line`:

- Include line if:
  - `display_type` is False

- Force:
  - `qty_to_invoice = product_uom_qty`

- Even if:
  - product type = service
  - invoicing_policy = delivery
  - nothing delivered yet

---

### 3. Implementation Approach

#### Option A (Recommended - Clean Override)

Override `_get_invoiceable_lines()`:

```python
from odoo import models

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_invoiceable_lines(self, final=False):
        lines = self.order_line.filtered(lambda l: not l.display_type)
        return lines