from odoo import models


class StockLocation(models.Model):
    _inherit = "stock.location"

    def _is_reservation_guard_bypassed(self):
        """Check if this location is in the reservation guard bypass allowlist."""
        bypass_ids_str = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("stock.reservation.guard.bypass.location_ids", default="")
        )
        if not bypass_ids_str:
            return False
        bypass_ids = [
            int(id_str)
            for id_str in bypass_ids_str.split(",")
            if id_str.strip()
        ]
        return self.id in bypass_ids
