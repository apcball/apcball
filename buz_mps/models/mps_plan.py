import json
import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MpsPlan(models.Model):
    _name = "mps.plan"
    _description = "Master Production Schedule"
    _order = "date_start desc, id desc"

    name = fields.Char(string="Name", required=True, default="New")
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Warehouse",
        required=True,
        default=lambda self: self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        ),
    )
    date_start = fields.Date(string="Start Date", required=True, default=fields.Date.today)
    date_end = fields.Date(string="End Date", required=True)
    bucket_type = fields.Selection(
        [("day", "Day"), ("week", "Week"), ("month", "Month")],
        string="Bucket Type",
        default="week",
        required=True,
    )
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed")],
        string="State",
        default="draft",
        required=True,
    )
    line_ids = fields.One2many("mps.plan.line", "plan_id", string="Plan Lines")
    line_count = fields.Integer(compute="_compute_line_count", string="# Lines")
    mo_count = fields.Integer(compute="_compute_mo_count", string="# MOs")
    po_count = fields.Integer(compute="_compute_po_count", string="# POs")

    @api.depends("line_ids")
    def _compute_line_count(self):
        for plan in self:
            plan.line_count = len(plan.line_ids)

    @api.depends("line_ids.generated_mo_ids")
    def _compute_mo_count(self):
        for plan in self:
            plan.mo_count = sum(len(line.generated_mo_ids) for line in plan.line_ids)

    @api.depends("line_ids.generated_po_ids")
    def _compute_po_count(self):
        for plan in self:
            plan.po_count = sum(len(line.generated_po_ids) for line in plan.line_ids)

    def action_confirm(self):
        self.write({"state": "confirmed"})

    def action_draft(self):
        self.write({"state": "draft"})

    # ── Bucket helpers ──────────────────────────────────────────────

    def _get_periods(self):
        """Return list of (period_start, period_end) date tuples."""
        self.ensure_one()
        periods = []
        current = self.date_start
        while current < self.date_end:
            if self.bucket_type == "day":
                next_date = current + timedelta(days=1)
            elif self.bucket_type == "week":
                next_date = current + timedelta(weeks=1)
            else:  # month
                next_date = current + relativedelta(months=1)
            period_end = min(next_date, self.date_end)
            periods.append((current, period_end))
            current = next_date
        return periods

    # ── Compute suggested for all lines ─────────────────────────────

    def action_compute_suggested(self):
        for plan in self:
            for line in plan.line_ids:
                line._compute_suggested()

    # ── Generate MOs ────────────────────────────────────────────────

    def action_generate_mo(self):
        self.ensure_one()
        if self.state != "confirmed":
            raise UserError("Please confirm the plan before generating orders.")

        created_mos = self.env["mrp.production"]
        created_pos = self.env["purchase.order"]
        errors = []

        for line in self.line_ids:
            try:
                if line.route_type == "manufacture":
                    mos = line._generate_mos()
                    created_mos |= mos
                elif line.route_type == "buy":
                    pos = line._generate_pos()
                    created_pos |= pos
            except UserError as e:
                errors.append(str(e))

        if errors and not created_mos and not created_pos:
            raise UserError("\n".join(errors))

        # Create planning slots for workorders / MOs
        if created_mos:
            created_mos._create_planning_slots()

        parts = []
        if created_mos:
            parts.append(f"{len(created_mos)} Manufacturing Order(s)")
        if created_pos:
            parts.append(f"{len(created_pos)} Purchase Order(s)")
        msg = " and ".join(parts) + " created." if parts else "No orders created."
        if errors:
            msg += "\n\nWarnings:\n" + "\n".join(errors)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "MPS — Generate Orders",
                "message": msg,
                "type": "success" if not errors else "warning",
                "sticky": False,
            },
        }

    # ── Smart buttons ───────────────────────────────────────────────

    def action_view_mos(self):
        self.ensure_one()
        mo_ids = self.line_ids.mapped("generated_mo_ids").ids
        return {
            "type": "ir.actions.act_window",
            "name": "Manufacturing Orders",
            "res_model": "mrp.production",
            "view_mode": "tree,form",
            "domain": [("id", "in", mo_ids)],
        }

    def action_view_pos(self):
        self.ensure_one()
        po_ids = self.line_ids.mapped("generated_po_ids").ids
        return {
            "type": "ir.actions.act_window",
            "name": "Purchase Orders",
            "res_model": "purchase.order",
            "view_mode": "tree,form",
            "domain": [("id", "in", po_ids)],
        }

    def action_open_planning_gantt(self):
        self.ensure_one()
        mo_ids = self.line_ids.mapped("generated_mo_ids").ids
        slot_ids = self.env["planning.slot"].search([
            "|",
            ("production_id", "in", mo_ids),
            ("mps_production_id", "in", mo_ids),
        ]).ids
        return {
            "type": "ir.actions.act_window",
            "name": "Planning Gantt",
            "res_model": "planning.slot",
            "view_mode": "mog_gantt,tree,form",
            "domain": [("id", "in", slot_ids)],
        }
