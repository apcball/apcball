from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    stock_reservation_guard_bypass_location_ids_str = fields.Char(
        string="Bypass Location IDs (Internal)",
        config_parameter="stock.reservation.guard.bypass.location_ids",
    )

    stock_reservation_guard_bypass_location_ids = fields.Many2many(
        "stock.location",
        compute="_compute_bypass_location_ids",
        inverse="_inverse_bypass_location_ids",
        string="Stock Locations (Bypass Reservation Guard)",
        help="Locations in this list bypass reservation guard checks",
    )

    @api.depends("stock_reservation_guard_bypass_location_ids_str")
    def _compute_bypass_location_ids(self):
        for record in self:
            ids_str = record.stock_reservation_guard_bypass_location_ids_str or ""
            if not ids_str.strip():
                record.stock_reservation_guard_bypass_location_ids = [(6, 0, [])]
                continue
            try:
                location_ids = [int(id_str) for id_str in ids_str.split(",") if id_str.strip()]
                record.stock_reservation_guard_bypass_location_ids = [(6, 0, location_ids)]
            except (ValueError, TypeError):
                record.stock_reservation_guard_bypass_location_ids = [(6, 0, [])]

    def _inverse_bypass_location_ids(self):
        for record in self:
            ids_list = record.stock_reservation_guard_bypass_location_ids.ids
            record.stock_reservation_guard_bypass_location_ids_str = ",".join(
                str(id) for id in ids_list
            )
