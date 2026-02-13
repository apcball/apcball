from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PlanningSlot(models.Model):
    _name = "planning.slot"
    _description = "Planning Slot"
    _order = "start_datetime"

    name = fields.Char(string="Name", required=True)
    start_datetime = fields.Datetime(string="Start", required=True)
    end_datetime = fields.Datetime(string="End", required=True)
    duration_hours = fields.Float(
        string="Duration (Hours)",
        compute="_compute_duration_hours",
        store=True,
    )
    employee_id = fields.Many2one(
        "hr.employee", string="Employee", index=True,
    )
    workcenter_id = fields.Many2one(
        "mrp.workcenter", string="Work Center", index=True,
    )
    project_task_id = fields.Many2one(
        "project.task", string="Task", index=True,
    )
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        related="project_task_id.project_id",
        store=True,
        index=True,
    )
    task_stage_id = fields.Many2one(
        "project.task.type",
        string="Task Stage",
        related="project_task_id.stage_id",
        store=True,
        index=True,
    )
    mrp_workorder_id = fields.Many2one(
        "mrp.workorder", string="Work Order", index=True,
    )
    production_id = fields.Many2one(
        "mrp.production",
        string="Manufacturing Order",
        related="mrp_workorder_id.production_id",
        store=True,
        index=True,
    )
    workorder_state = fields.Selection(
        related="mrp_workorder_id.state",
        string="WO State",
        store=True,
        index=True,
    )
    slot_type = fields.Selection(
        [("manual", "Manual"), ("task", "Task"), ("workorder", "Work Order")],
        string="Type",
        compute="_compute_slot_type",
        store=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        string="State",
        default="draft",
        required=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        required=True,
    )
    color = fields.Integer(string="Color Index", default=0)

    @api.depends("start_datetime", "end_datetime")
    def _compute_duration_hours(self):
        for slot in self:
            if slot.start_datetime and slot.end_datetime:
                delta = slot.end_datetime - slot.start_datetime
                slot.duration_hours = delta.total_seconds() / 3600.0
            else:
                slot.duration_hours = 0.0

    @api.depends("project_task_id", "mrp_workorder_id")
    def _compute_slot_type(self):
        for slot in self:
            if slot.project_task_id:
                slot.slot_type = "task"
            elif slot.mrp_workorder_id:
                slot.slot_type = "workorder"
            else:
                slot.slot_type = "manual"

    @api.onchange("project_task_id")
    def _onchange_project_task_id(self):
        if self.project_task_id:
            self.name = self.project_task_id.name

    @api.onchange("mrp_workorder_id")
    def _onchange_mrp_workorder_id(self):
        if self.mrp_workorder_id:
            self.name = self.mrp_workorder_id.name
            if self.mrp_workorder_id.workcenter_id:
                self.workcenter_id = self.mrp_workorder_id.workcenter_id

    @api.constrains("start_datetime", "end_datetime")
    def _check_dates(self):
        for slot in self:
            if slot.start_datetime and slot.end_datetime:
                if slot.start_datetime >= slot.end_datetime:
                    raise ValidationError(
                        "Start datetime must be before end datetime."
                    )

    @api.constrains("project_task_id", "mrp_workorder_id")
    def _check_single_link(self):
        for slot in self:
            if slot.project_task_id and slot.mrp_workorder_id:
                raise ValidationError(
                    "A slot must link to only one of: Task or Work Order, not both."
                )

    def write(self, vals):
        res = super().write(vals)
        if "start_datetime" in vals or "end_datetime" in vals:
            self._after_slot_write_hook(vals)
        return res

    def _after_slot_write_hook(self, vals):
        """Hook called after slot write when dates change.
        Override in other modules to add sync logic."""
        self._sync_dates_to_linked_records()

    def _sync_dates_to_linked_records(self):
        for slot in self:
            if slot.project_task_id:
                task_vals = {}
                if slot.start_datetime:
                    task_vals["x_planned_start"] = slot.start_datetime
                if slot.end_datetime:
                    task_vals["x_planned_end"] = slot.end_datetime
                if task_vals:
                    slot.project_task_id.sudo().write(task_vals)
            if slot.mrp_workorder_id:
                wo_vals = {}
                if slot.start_datetime:
                    wo_vals["date_start"] = slot.start_datetime
                if slot.end_datetime:
                    wo_vals["date_finished"] = slot.end_datetime
                if wo_vals:
                    slot.mrp_workorder_id.sudo().write(wo_vals)

    def action_confirm(self):
        self.filtered(lambda s: s.state == "draft").write({"state": "confirmed"})

    def action_done(self):
        self.filtered(lambda s: s.state == "confirmed").write({"state": "done"})

    def action_cancel(self):
        self.filtered(lambda s: s.state != "cancelled").write({"state": "cancelled"})

    def action_draft(self):
        self.filtered(lambda s: s.state == "cancelled").write({"state": "draft"})
