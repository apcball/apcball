from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    freeze_warning = fields.Char(
        string="Stock Freeze Warning",
        compute="_compute_freeze_warning",
        compute_sudo=True,
    )

    def _compute_freeze_warning(self):
        FreezePeriod = self.env["stock.freeze.period"].sudo()
        for picking in self:
            picking.freeze_warning = False
            moves = picking.move_ids
            if not moves or not picking.company_id:
                continue
            location_ids = (moves.location_id | moves.location_dest_id).ids
            periods = FreezePeriod._get_active_periods_for_locations(
                picking.company_id, location_ids
            )
            if not periods:
                continue
            period = periods[0]
            tz_end = fields.Datetime.context_timestamp(period, period.date_end)
            picking.freeze_warning = (
                "Stock Freeze active: inventory counting is in progress for "
                "%(scope)s. Stock validation is blocked until %(end)s."
            ) % {
                "scope": period.location_summary,
                "end": fields.Datetime.to_string(tz_end),
            }

    def _pre_action_done_hook(self):
        self.env["stock.freeze.period"].sudo()._check_moves(self.move_ids)
        return super()._pre_action_done_hook()
