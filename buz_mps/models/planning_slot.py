import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PlanningSlotMps(models.Model):
    _inherit = "planning.slot"

    mps_production_id = fields.Many2one(
        "mrp.production",
        string="MPS Manufacturing Order",
        index=True,
        help="Direct link to MO for slots created from MPS when BOM has no routing.",
    )

    def _after_slot_write_hook(self, vals):
        """Extension from buz_mps: additional sync logic for MPS-generated slots.

        The base _sync_dates_to_linked_records already handles writing
        date_start / date_finished to mrp.workorder.
        This hook is available for future MPS-specific logic (e.g. cascade
        to MO dates, update MPS plan line status, etc.).
        """
        res = super()._after_slot_write_hook(vals)
        # Cascade workorder date changes up to the parent MO
        for slot in self:
            if not slot.mrp_workorder_id:
                continue
            mo = slot.mrp_workorder_id.production_id
            if not mo:
                continue
            # Update MO planned dates to span all its workorders
            wo_starts = mo.workorder_ids.mapped("date_start")
            wo_ends = mo.workorder_ids.mapped("date_finished")
            wo_starts = [d for d in wo_starts if d]
            wo_ends = [d for d in wo_ends if d]
            mo_vals = {}
            if wo_starts:
                mo_vals["date_start"] = min(wo_starts)
            if wo_ends:
                mo_vals["date_finished"] = max(wo_ends)
            if mo_vals:
                mo.sudo().write(mo_vals)
                _logger.info(
                    "Synced MO '%s' dates from workorder slots.", mo.name,
                )
        return res
