import logging
from datetime import timedelta

from odoo import models

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def _create_planning_slots(self):
        """Create planning.slot records for workorders of these MOs.
        If an MO has no workorders (BOM without routing), create a
        slot directly for the MO itself as fallback.
        """
        PlanningSlot = self.env["planning.slot"]
        created_slots = PlanningSlot

        for mo in self:
            if mo.workorder_ids:
                # Create one slot per workorder
                for wo in mo.workorder_ids:
                    existing = PlanningSlot.search([
                        ("mrp_workorder_id", "=", wo.id),
                    ], limit=1)
                    if existing:
                        _logger.info(
                            "Slot already exists for workorder %s, skipping.", wo.name,
                        )
                        continue

                    duration_minutes = wo.duration_expected or 60.0
                    duration_td = timedelta(minutes=duration_minutes)

                    start_dt = wo.date_start or mo.date_start or mo.create_date
                    end_dt = wo.date_finished
                    if not end_dt:
                        end_dt = start_dt + duration_td if start_dt else False

                    if not start_dt or not end_dt:
                        _logger.warning(
                            "Cannot determine dates for workorder %s, skipping.", wo.name,
                        )
                        continue

                    slot = PlanningSlot.create({
                        "name": wo.name,
                        "mrp_workorder_id": wo.id,
                        "workcenter_id": wo.workcenter_id.id if wo.workcenter_id else False,
                        "start_datetime": start_dt,
                        "end_datetime": end_dt,
                        "state": "confirmed",
                        "company_id": mo.company_id.id,
                    })
                    created_slots |= slot
                    _logger.info(
                        "Created planning slot '%s' for workorder %s (MO: %s)",
                        slot.name, wo.name, mo.name,
                    )
            else:
                # Fallback: BOM has no routing → create slot for the MO itself
                existing = PlanningSlot.search([
                    ("mps_production_id", "=", mo.id),
                ], limit=1)
                if existing:
                    _logger.info(
                        "Slot already exists for MO %s, skipping.", mo.name,
                    )
                    continue

                start_dt = mo.date_start or mo.create_date
                end_dt = mo.date_finished
                if not end_dt:
                    end_dt = start_dt + timedelta(hours=1) if start_dt else False

                if not start_dt or not end_dt:
                    _logger.warning(
                        "Cannot determine dates for MO %s, skipping.", mo.name,
                    )
                    continue

                slot = PlanningSlot.create({
                    "name": mo.name,
                    "mps_production_id": mo.id,
                    "start_datetime": start_dt,
                    "end_datetime": end_dt,
                    "state": "confirmed",
                    "company_id": mo.company_id.id,
                })
                created_slots |= slot
                _logger.info(
                    "Created planning slot '%s' for MO %s (no workorders).",
                    slot.name, mo.name,
                )

        return created_slots
