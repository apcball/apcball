from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    buz_reservation_default_expiry_days = fields.Integer(
        string="Default Expiry (Days)",
        config_parameter="buz_stock_reservation.default_expiry_days",
        default=7,
        help="Default number of days before a new reservation expires.",
    )
    buz_reservation_expiring_soon_days = fields.Integer(
        string="Expiring Soon Threshold (Days)",
        config_parameter="buz_stock_reservation.expiring_soon_days",
        default=2,
        help="Reservations expiring within this many days are flagged as "
        "'Expiring Soon'.",
    )
