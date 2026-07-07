from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _get_discounted_unit_price(self):
        self.ensure_one()
        po_line = self.purchase_line_id
        if not po_line:
            return 0.0

        price_unit = po_line.price_unit or 0.0
        product_qty = po_line.product_qty or 1.0
        discount_pct = po_line.discount or 0.0

        if not discount_pct and po_line.fixed_discount and price_unit:
            discount_pct = (po_line.fixed_discount / (price_unit * product_qty)) * 100.0

        return price_unit * (1 - discount_pct / 100.0)
