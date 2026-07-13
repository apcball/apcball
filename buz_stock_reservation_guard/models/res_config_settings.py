from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    stock_reservation_guard_bypass_location_ids = fields.Many2many(
        "stock.location",
        string="Stock Locations (Bypass Reservation Guard)",
        help="Locations in this list bypass reservation guard checks",
        config_parameter="stock.reservation.guard.bypass.location_ids",
    )
