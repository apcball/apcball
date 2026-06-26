from odoo import api, fields, models


class ResPartner(models.Model):
    """Extend res.partner with VIP customer support."""

    _inherit = "res.partner"

    is_vip_customer = fields.Boolean(
        string="VIP Customer",
        help="If enabled, reservations for this customer will default to VIP type and priority.",
        default=False,
        tracking=True,
    )
    vip_since = fields.Date(
        string="VIP Since",
        readonly=True,
    )
    reservation_count = fields.Integer(
        string="Reservation Count",
        compute="_compute_reservation_count",
        store=True,
    )
    reservation_ids = fields.One2many(
        comodel_name="stock.reservation",
        inverse_name="customer_id",
        string="Reservations",
    )

    @api.depends("reservation_ids")
    def _compute_reservation_count(self):
        for partner in self:
            partner.reservation_count = len(partner.reservation_ids)

    def action_view_partner_reservations(self):
        """Smart button: open reservations for this customer."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "stock_reservation_management.action_stock_reservation"
        )
        action["domain"] = [("customer_id", "=", self.id)]
        action["context"] = {
            "default_customer_id": self.id,
        }
        return action
