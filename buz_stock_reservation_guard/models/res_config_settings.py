from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    stock_reservation_guard_bypass_location_ids_str = fields.Char(
        string="Bypass Location IDs (Internal)",
        config_parameter="stock.reservation.guard.bypass.location_ids",
    )

    stock_reservation_guard_bypass_location_ids = fields.Many2many(
        "stock.location",
        string="Stock Locations (Bypass Reservation Guard)",
        help="Locations in this list bypass reservation guard checks",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "stock_reservation_guard_bypass_location_ids" in fields_list:
            ids_str = self.env["ir.config_parameter"].sudo().get_param(
                "stock.reservation.guard.bypass.location_ids", default=""
            )
            if ids_str.strip():
                try:
                    location_ids = [
                        int(id_str)
                        for id_str in ids_str.split(",")
                        if id_str.strip()
                    ]
                    res["stock_reservation_guard_bypass_location_ids"] = [(6, 0, location_ids)]
                except (ValueError, TypeError):
                    res["stock_reservation_guard_bypass_location_ids"] = [(6, 0, [])]
            else:
                res["stock_reservation_guard_bypass_location_ids"] = [(6, 0, [])]
        return res

    def write(self, vals):
        """Sync m2m field to config parameter before save."""
        if "stock_reservation_guard_bypass_location_ids" in vals:
            ids_list = vals.get("stock_reservation_guard_bypass_location_ids")
            if ids_list:
                location_ids = [
                    id for cmd, id, __ in ids_list if cmd == 4
                ] if ids_list else []
                if not location_ids and ids_list and ids_list[0][0] == 6:
                    location_ids = ids_list[0][2]
                vals["stock_reservation_guard_bypass_location_ids_str"] = ",".join(
                    str(id) for id in location_ids
                )
            else:
                vals["stock_reservation_guard_bypass_location_ids_str"] = ""
        return super().write(vals)
