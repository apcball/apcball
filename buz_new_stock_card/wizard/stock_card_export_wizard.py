from urllib.parse import urlencode

from odoo import fields, models
from odoo.exceptions import UserError


class StockCardExportWizard(models.TransientModel):
    _name = "buz.stock.card.export.wizard"
    _description = "Stock Card Export Wizard"

    product_id = fields.Many2one("product.product", string="Product")
    date_from = fields.Date(string="Date From", required=True,
                             default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(string="Date To", required=True,
                           default=lambda self: fields.Date.context_today(self))
    warehouse_ids = fields.Many2many("stock.warehouse", string="Warehouses")
    location_ids = fields.Many2many(
        "stock.location", string="Locations",
        domain=[("usage", "=", "internal")],
    )
    show_movements_only = fields.Boolean(string="Show Movements Only")

    def action_export_xlsx(self):
        self.ensure_one()
        all_mode = not self.product_id and not self.warehouse_ids and not self.location_ids
        if not all_mode and not self.warehouse_ids and not self.location_ids:
            # product only, no scope: not supported - needs a scope to bound the report
            raise UserError("กรุณาเลือกคลังสินค้าหรือ Location อย่างน้อย 1 รายการ")
        params = {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "show_movements_only": "1" if self.show_movements_only else "0",
            "company_id": self.env.company.id,
        }
        if not all_mode:
            if self.product_id:
                params["product_id"] = self.product_id.id
            params["warehouse_ids"] = ",".join(str(i) for i in self.warehouse_ids.ids)
            params["location_ids"] = ",".join(str(i) for i in self.location_ids.ids)
        return {
            "type": "ir.actions.act_url",
            "url": "/stock_card/export_xlsx?" + urlencode(params),
            "target": "new",
        }
