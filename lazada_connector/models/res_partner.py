from odoo import api, fields, models

class ResPartner(models.Model):
    _inherit = "res.partner"
    lazada_buyer_id = fields.Char(string="Lazada Buyer ID", copy=False)
    lazada_config_id = fields.Many2one(
        "lazada.config", string="Lazada Seller Config", copy=False,
        ondelete="set null"
    )

    _sql_constraints = [
        (
            "lazada_buyer_seller_unique",
            "unique(lazada_config_id, lazada_buyer_id)",
            "A Lazada buyer can only have one partner per seller.",
        ),
    ]

    @api.model
    def find_or_create_lazada_buyer(self, config, order):
        buyer_name = " ".join(filter(None, [
            order.get("customer_first_name"), order.get("customer_last_name"),
        ])) or "Lazada Buyer"
        buyer_id = str(
            order.get("customer_email") or buyer_name or ""
        )
        partner = self.search([
            ("lazada_config_id", "=", config.id),
            ("lazada_buyer_id", "=", buyer_id),
        ], limit=1)
        address = order.get("address_shipping") or {}
        street = " ".join(filter(None, [
            address.get("address1"), address.get("address2"),
            address.get("address3"), address.get("address4"),
            address.get("address5"),
        ])) or False
        values = {
            "name": " ".join(filter(None, [
                address.get("first_name"), address.get("last_name"),
            ])) or buyer_name,
            "phone": address.get("phone") or False,
            "street": street,
            "zip": address.get("postcode") or False,
            "city": address.get("city") or False,
            "lazada_buyer_id": buyer_id or False,
            "lazada_config_id": config.id,
            "customer_rank": 1,
        }
        if partner:
            partner.write({k: v for k, v in values.items() if v})
            return partner
        return self.create(values)
