from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    analytic_auto_sync = fields.Boolean(
        string="Auto Sync Analytic",
        default=True,
        help="Automatically sync analytic from first line to other lines",
    )

    def _sync_analytic_from_first_line(self):
        for picking in self:
            if (
                not picking.analytic_auto_sync
                or picking.picking_type_code != "internal"
                or picking.state in ("done", "cancel")
            ):
                continue

            moves = picking.move_ids_without_package.sorted(
                key=lambda move: move.sequence
            )
            if not moves or not moves[0].analytic_distribution:
                continue

            analytic_distribution = moves[0].analytic_distribution
            for move in moves[1:]:
                if not move.analytic_distribution:
                    move.analytic_distribution = analytic_distribution

    @api.onchange("move_ids_without_package", "analytic_auto_sync")
    def _onchange_move_ids_without_package_analytic_sync(self):
        self._sync_analytic_from_first_line()

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super().create(vals_list)
        pickings._sync_analytic_from_first_line()
        return pickings

    def write(self, vals):
        result = super().write(vals)
        if "move_ids_without_package" in vals or "analytic_auto_sync" in vals:
            self._sync_analytic_from_first_line()
        return result

    def button_validate(self):
        self._sync_analytic_from_first_line()
        return super().button_validate()
