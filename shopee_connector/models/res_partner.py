from odoo import api, fields, models

class ResPartner(models.Model):
    _inherit = "res.partner"
    shopee_buyer_id = fields.Char(string="Shopee Buyer ID", copy=False)
    shopee_config_id = fields.Many2one(
        "shopee.config", string="Shopee Shop Config", copy=False, ondelete="set null"
    )

    _sql_constraints = [
        (
            "shopee_buyer_shop_unique",
            "unique(shopee_config_id, shopee_buyer_id)",
            "A Shopee buyer can only have one partner per shop.",
        ),
    ]

    @api.model
    def find_or_create_shopee_buyer(self, config, order):
        buyer_id = str(order.get("buyer_user_id") or order.get("buyer_username") or "")
        buyer_name = order.get("buyer_username") or "Shopee Buyer"
        partner = self.search([
            ("shopee_config_id", "=", config.id),
            ("shopee_buyer_id", "=", buyer_id),
        ], limit=1) if buyer_id else self.env["res.partner"]
        address = order.get("recipient_address") or {}
        values = {
            "name": address.get("name") or buyer_name,
            "phone": address.get("phone") or False,
            "street": address.get("full_address") or False,
            "zip": address.get("zipcode") or False,
            "city": address.get("city") or False,
            "shopee_buyer_id": buyer_id or False,
            "shopee_config_id": config.id,
            "customer_rank": 1,
        }
        if partner:
            partner.write({k: v for k, v in values.items() if v})
            return partner
        return self.create(values)
