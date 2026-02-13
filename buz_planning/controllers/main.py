from datetime import datetime

from odoo import http
from odoo.http import request


class MogPlanningController(http.Controller):

    def _serialize_slot(self, slot):
        return {
            "id": slot.id,
            "name": slot.name,
            "start_datetime": slot.start_datetime.isoformat() if slot.start_datetime else False,
            "end_datetime": slot.end_datetime.isoformat() if slot.end_datetime else False,
            "duration_hours": slot.duration_hours,
            "employee_id": slot.employee_id.id if slot.employee_id else False,
            "employee_name": slot.employee_id.name if slot.employee_id else "",
            "workcenter_id": slot.workcenter_id.id if slot.workcenter_id else False,
            "workcenter_name": slot.workcenter_id.name if slot.workcenter_id else "",
            "slot_type": slot.slot_type or "manual",
            "state": slot.state,
            "color": slot.color,
            "project_task_id": slot.project_task_id.id if slot.project_task_id else False,
            "project_id": slot.project_id.id if slot.project_id else False,
            "project_name": slot.project_id.name if slot.project_id else "",
            "mrp_workorder_id": slot.mrp_workorder_id.id if slot.mrp_workorder_id else False,
            "production_id": slot.production_id.id if slot.production_id else False,
            "production_name": slot.production_id.name if slot.production_id else "",
        }

    @http.route("/mog_planning/gantt/fetch", type="json", auth="user")
    def gantt_fetch(self, date_start, date_end, group_mode="employee"):
        date_start_dt = datetime.fromisoformat(date_start)
        date_end_dt = datetime.fromisoformat(date_end)

        domain = [
            ("start_datetime", "<", date_end_dt),
            ("end_datetime", ">", date_start_dt),
            ("state", "!=", "cancelled"),
        ]
        slots = request.env["planning.slot"].search(domain)

        rows = []
        if group_mode == "employee":
            employees = request.env["hr.employee"].search([])
            rows = [{"id": e.id, "name": e.name} for e in employees]
            unassigned_slots = slots.filtered(lambda s: not s.employee_id)
            if unassigned_slots:
                rows.insert(0, {"id": False, "name": "Unassigned"})
        else:
            workcenters = request.env["mrp.workcenter"].search([])
            rows = [{"id": w.id, "name": w.name} for w in workcenters]
            unassigned_slots = slots.filtered(lambda s: not s.workcenter_id)
            if unassigned_slots:
                rows.insert(0, {"id": False, "name": "Unassigned"})

        return {
            "rows": rows,
            "slots": [self._serialize_slot(s) for s in slots],
        }

    @http.route("/mog_planning/gantt/update_slot", type="json", auth="user")
    def gantt_update_slot(self, slot_id, start_datetime=None, end_datetime=None,
                          employee_id=None, workcenter_id=None):
        slot = request.env["planning.slot"].browse(int(slot_id))
        if not slot.exists():
            return {"error": "Slot not found"}

        vals = {}
        if start_datetime:
            vals["start_datetime"] = datetime.fromisoformat(start_datetime)
        if end_datetime:
            vals["end_datetime"] = datetime.fromisoformat(end_datetime)
        if employee_id is not None:
            vals["employee_id"] = int(employee_id) if employee_id else False
        if workcenter_id is not None:
            vals["workcenter_id"] = int(workcenter_id) if workcenter_id else False

        if vals:
            slot.write(vals)

        return {"slot": self._serialize_slot(slot)}

    @http.route("/mog_planning/gantt/create_slot", type="json", auth="user")
    def gantt_create_slot(self, name, start_datetime, end_datetime,
                          employee_id=False, workcenter_id=False,
                          slot_type=None, project_task_id=False,
                          mrp_workorder_id=False):
        vals = {
            "name": name,
            "start_datetime": datetime.fromisoformat(start_datetime),
            "end_datetime": datetime.fromisoformat(end_datetime),
        }
        if employee_id:
            vals["employee_id"] = int(employee_id)
        if workcenter_id:
            vals["workcenter_id"] = int(workcenter_id)
        if project_task_id:
            vals["project_task_id"] = int(project_task_id)
        if mrp_workorder_id:
            vals["mrp_workorder_id"] = int(mrp_workorder_id)

        slot = request.env["planning.slot"].create(vals)
        return {"slot": self._serialize_slot(slot)}
