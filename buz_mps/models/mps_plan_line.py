import json
import logging
from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MpsPlanLine(models.Model):
    _name = "mps.plan.line"
    _description = "MPS Plan Line"
    _order = "plan_id, product_id"

    plan_id = fields.Many2one(
        "mps.plan", string="Plan", required=True, ondelete="cascade", index=True,
    )
    product_id = fields.Many2one(
        "product.product", string="Product", required=True, index=True,
    )
    route_type = fields.Selection(
        [("manufacture", "Manufacture"), ("buy", "Buy")],
        string="Route Type",
        default="manufacture",
        required=True,
    )
    safety_stock = fields.Float(string="Safety Stock", default=0.0)
    lead_time_days = fields.Integer(string="Lead Time (Days)", default=0)

    # User-friendly qty fields
    forecast_qty = fields.Float(string="Forecast Qty", default=0.0)
    suggested_qty = fields.Float(string="Suggested Qty", readonly=True, default=0.0)
    confirmed_qty = fields.Float(string="Confirmed Qty", default=0.0)

    # Internal JSON fields (hidden from UI)
    period_forecast_json = fields.Text(default="{}")
    period_suggested_json = fields.Text(default="{}", readonly=True)
    period_confirmed_json = fields.Text(default="{}")

    # Links to generated records
    generated_mo_ids = fields.Many2many(
        "mrp.production",
        "mps_plan_line_mo_rel",
        "line_id",
        "production_id",
        string="Generated MOs",
    )
    generated_po_ids = fields.Many2many(
        "purchase.order",
        "mps_plan_line_po_rel",
        "line_id",
        "order_id",
        string="Generated POs",
    )
    mo_count = fields.Integer(compute="_compute_mo_count", string="# MOs")

    company_id = fields.Many2one(related="plan_id.company_id", store=True)

    @api.depends("generated_mo_ids")
    def _compute_mo_count(self):
        for line in self:
            line.mo_count = len(line.generated_mo_ids)

    # ── JSON helpers ────────────────────────────────────────────────

    def _get_json(self, field_name):
        """Parse a JSON field. Returns (dict, scalar_fallback).
        If the value is a dict, returns (dict, 0.0).
        If the value is a bare number, returns ({}, number) so callers
        can use the number as a flat qty for every period.
        """
        self.ensure_one()
        raw = getattr(self, field_name) or "{}"
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}, 0.0
        if isinstance(data, dict):
            return data, 0.0
        if isinstance(data, (int, float)):
            return {}, float(data)
        return {}, 0.0

    def _get_period_qty(self, field_name, pkey):
        """Get qty for a specific period key from a JSON field.
        Handles both dict format {"2026-02-12": 50} and bare number 50."""
        data, scalar = self._get_json(field_name)
        if data:
            return float(data.get(pkey, 0.0))
        return scalar

    def _set_json(self, field_name, data):
        self.ensure_one()
        self.write({field_name: json.dumps(data)})

    def _period_key(self, date_start):
        return str(date_start)

    # ── Compute suggested replenishment ─────────────────────────────

    def _compute_suggested(self):
        """Compute suggested replenishment qty based on forecast, stock, and safety stock."""
        self.ensure_one()
        plan = self.plan_id
        product = self.product_id
        warehouse = plan.warehouse_id
        location = warehouse.lot_stock_id

        stock_on_hand = product.with_context(location=location.id).qty_available
        forecast = self.forecast_qty or 0.0

        # Net stock after forecast
        net_stock = stock_on_hand - forecast

        # Suggested qty to bring stock above safety stock
        if net_stock < self.safety_stock:
            suggested = self.safety_stock - net_stock
        else:
            suggested = 0.0

        self.write({"suggested_qty": max(suggested, 0.0)})

    def _get_incoming_supply(self, product, date_start, date_end):
        """Sum of open MO + open PO quantities arriving in the period."""
        # Open MOs
        mo_qty = 0.0
        mos = self.env["mrp.production"].search([
            ("product_id", "=", product.id),
            ("state", "in", ("confirmed", "progress")),
            ("date_start", ">=", datetime.combine(date_start, datetime.min.time())),
            ("date_start", "<", datetime.combine(date_end, datetime.min.time())),
        ])
        for mo in mos:
            mo_qty += mo.product_qty

        # Open POs
        po_qty = 0.0
        po_lines = self.env["purchase.order.line"].search([
            ("product_id", "=", product.id),
            ("order_id.state", "in", ("purchase", "done")),
            ("date_planned", ">=", datetime.combine(date_start, datetime.min.time())),
            ("date_planned", "<", datetime.combine(date_end, datetime.min.time())),
        ])
        for pol in po_lines:
            po_qty += pol.product_qty

        return mo_qty + po_qty

    def _get_outgoing_demand(self, product, date_start, date_end, warehouse):
        """Sum of confirmed delivery quantities in the period."""
        moves = self.env["stock.move"].search([
            ("product_id", "=", product.id),
            ("state", "in", ("confirmed", "assigned", "waiting")),
            ("location_id", "=", warehouse.lot_stock_id.id),
            ("date", ">=", datetime.combine(date_start, datetime.min.time())),
            ("date", "<", datetime.combine(date_end, datetime.min.time())),
        ])
        return sum(moves.mapped("product_uom_qty"))

    # ── Generate MOs ────────────────────────────────────────────────

    def _generate_mos(self):
        """Generate one MO for this plan line. Returns created mrp.production recordset."""
        self.ensure_one()
        if self.route_type != "manufacture":
            return self.env["mrp.production"]

        product = self.product_id
        bom = self.env["mrp.bom"]._bom_find(product)[product]
        if not bom:
            raise UserError(
                f"No Bill of Materials found for product '{product.display_name}'. "
                f"Cannot generate Manufacturing Orders."
            )

        # Use confirmed qty if set, else suggested
        qty = self.confirmed_qty if self.confirmed_qty > 0 else self.suggested_qty
        if qty <= 0:
            return self.env["mrp.production"]

        plan = self.plan_id
        warehouse = plan.warehouse_id
        picking_type = warehouse.manu_type_id
        if not picking_type:
            picking_type = self.env["stock.picking.type"].search([
                ("code", "=", "mrp_operation"),
                ("warehouse_id", "=", warehouse.id),
            ], limit=1)

        # Compute planned dates
        date_finished = datetime.combine(plan.date_end, datetime.min.time())
        date_start = date_finished - timedelta(days=max(self.lead_time_days, 1))

        mo_vals = {
            "product_id": product.id,
            "product_qty": qty,
            "product_uom_id": product.uom_id.id,
            "bom_id": bom.id,
            "date_start": date_start,
            "date_finished": date_finished,
            "origin": f"MPS: {plan.name}",
            "company_id": plan.company_id.id,
        }
        if picking_type:
            mo_vals["picking_type_id"] = picking_type.id

        mo = self.env["mrp.production"].create(mo_vals)
        mo.action_confirm()

        self.write({"generated_mo_ids": [(4, mo.id)]})
        return mo

    # ── Generate POs ────────────────────────────────────────────────

    def _generate_pos(self):
        """Generate one PO for this plan line (route_type=buy). Returns created purchase.order recordset."""
        self.ensure_one()
        if self.route_type != "buy":
            return self.env["purchase.order"]

        product = self.product_id
        seller = product.seller_ids[:1]
        if not seller:
            raise UserError(
                f"No vendor defined for product '{product.display_name}'. "
                f"Please add a vendor in the product's Purchase tab."
            )

        # Use confirmed qty if set, else suggested
        qty = self.confirmed_qty if self.confirmed_qty > 0 else self.suggested_qty
        if qty <= 0:
            return self.env["purchase.order"]

        plan = self.plan_id
        date_planned = datetime.combine(plan.date_end, datetime.min.time())
        date_order = date_planned - timedelta(days=max(self.lead_time_days, 1))

        po = self.env["purchase.order"].create({
            "partner_id": seller.partner_id.id,
            "date_order": date_order,
            "origin": f"MPS: {plan.name}",
            "company_id": plan.company_id.id,
            "order_line": [(0, 0, {
                "product_id": product.id,
                "name": product.display_name,
                "product_qty": qty,
                "product_uom": product.uom_po_id.id or product.uom_id.id,
                "price_unit": seller.price or 0.0,
                "date_planned": date_planned,
            })],
        })

        self.write({"generated_po_ids": [(4, po.id)]})
        return po

    # ── Smart buttons ───────────────────────────────────────────────

    def action_view_mos(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Manufacturing Orders",
            "res_model": "mrp.production",
            "view_mode": "tree,form",
            "domain": [("id", "in", self.generated_mo_ids.ids)],
        }
