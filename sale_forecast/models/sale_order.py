from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    forecast_allocation_ids = fields.One2many(
        "forecast.allocation", "sale_order_id", string="Forecast Allocations"
    )
    forecast_allocation_count = fields.Integer(compute="_compute_forecast_allocation_count")

    def action_confirm(self):
        """
        Override sale order confirmation to include auto-allocation.

        Auto-allocation is attempted after SO confirmation:
        - If auto-allocation succeeds: allocations are created normally
        - If auto-allocation fails with ValidationError: SO confirmation is rolled back
        - If auto-allocation fails with other errors: error is logged, SO remains confirmed

        This approach prevents data inconsistency while allowing sales to proceed
        when allocation errors are non-critical (e.g., permission issues).
        """
        # Call parent to confirm the sale order
        res = super().action_confirm()

        # Attempt auto-allocation
        for order in self:
            try:
                order._auto_allocate_forecast_from_sale()
            except ValidationError as e:
                # Validation errors are critical - rollback SO confirmation
                # This prevents over-allocation and other business rule violations
                _logger.error(
                    "Auto-allocation failed for SO %s (Validation): %s. Rolling back confirmation.",
                    order.name, str(e)
                )
                # Re-raise to rollback the entire transaction
                raise UserError(_(
                    "Cannot confirm sale order: Auto-allocation validation failed.\n\n"
                    "Reason: %s\n\n"
                    "Please check your forecast plan or contact your manager."
                ) % str(e))
            except UserError as e:
                # User errors (e.g., access denied) - log and allow SO to remain confirmed
                # Users can manually create allocations later
                _logger.warning(
                    "Auto-allocation failed for SO %s (UserError): %s. "
                    "Sale order remains confirmed.",
                    order.name, str(e)
                )
                # Continue without raising - SO remains confirmed
                # User can create allocations manually
            except Exception as e:
                # Unexpected errors - log and allow SO to remain confirmed
                # This prevents blocking sales due to system errors
                _logger.exception(
                    "Auto-allocation failed for SO %s (Unexpected): %s. "
                    "Sale order remains confirmed. Please investigate.",
                    order.name, str(e)
                )
                # Continue without raising - SO remains confirmed
                # Admin can investigate logs and fix allocations manually

        return res

    @api.depends("forecast_allocation_ids")
    def _compute_forecast_allocation_count(self):
        for rec in self:
            rec.forecast_allocation_count = len(rec.forecast_allocation_ids)

    def _auto_allocate_forecast_from_sale(self):
        ForecastPlan = self.env["forecast.plan"]
        ForecastAllocation = self.env["forecast.allocation"]

        # Auto-allocation should only work for confirmed sales orders with a salesperson
        # Access control is enforced by record rules:
        # - Users can only access their own forecast plans (via plan_id.user_id)
        # - Users can only access allocations for their plans or sale orders
        for order in self.filtered(lambda o: o.state in ("sale", "done") and o.user_id):
            month_start = fields.Date.start_of(fields.Date.context_today(order), "month")

            # Search for the user's forecast plan for current month
            # Record rules ensure users only see their own plans
            plan = ForecastPlan.search(
                [
                    ("user_id", "=", order.user_id.id),
                    ("start_date", "=", month_start),
                    ("company_id", "=", order.company_id.id),
                    ("state", "!=", "cancel"),
                ],
                limit=1,
            )

            if not plan:
                # No forecast plan exists for this month, skip allocation
                continue

            # Calculate already allocated quantities per forecast line
            # Record rules ensure we only see relevant allocations
            allocated_totals = defaultdict(float)
            existing_allocs = ForecastAllocation.search(
                [
                    ("plan_line_id", "in", plan.line_ids.ids),
                    ("state", "!=", "cancel"),
                    ("is_non_forecast", "=", False)
                ]
            )
            for existing_alloc in existing_allocs:
                allocated_totals[existing_alloc.plan_line_id.id] += existing_alloc.allocated_qty

            # Process each sale order line
            for line in order.order_line.filtered(
                lambda l: not l.display_type and l.product_id and l.product_uom_qty > 0
            ):
                # Skip lines that are already allocated
                if ForecastAllocation.search(
                    [("sale_order_line_id", "=", line.id), ("state", "!=", "cancel")],
                    limit=1
                ):
                    continue

                remaining_qty = line.product_uom_qty
                first_allocation = False
                line_is_non_forecast = False

                # Find matching forecast lines for current month
                forecast_lines = plan.line_ids.filtered(
                    lambda pl: pl.product_id == line.product_id
                    and pl.arrival_month
                    and fields.Date.start_of(pl.arrival_month, "month") == month_start
                )

                # Allocate to forecast lines
                for forecast_line in forecast_lines:
                    if remaining_qty <= 0:
                        break
                    available_qty = forecast_line.forecast_qty - allocated_totals[forecast_line.id]
                    if available_qty <= 0:
                        continue
                    alloc_qty = min(remaining_qty, available_qty)

                    # Create allocation - record rules will enforce access control
                    allocation = ForecastAllocation.create(
                        {
                            "plan_id": plan.id,
                            "plan_line_id": forecast_line.id,
                            "product_id": line.product_id.id,
                            "allocated_qty": alloc_qty,
                            "sale_order_id": order.id,
                            "sale_order_line_id": line.id,
                            "is_non_forecast": False,
                        }
                    )
                    allocated_totals[forecast_line.id] += alloc_qty
                    remaining_qty -= alloc_qty
                    if not first_allocation:
                        first_allocation = allocation
                    line.is_forecast_allocation = True

                # Handle non-forecast remaining quantity
                if remaining_qty > 0:
                    line_is_non_forecast = True
                    target_line = forecast_lines[:1]
                    allocation_vals = {
                        "plan_id": plan.id,
                        "product_id": line.product_id.id,
                        "allocated_qty": remaining_qty,
                        "sale_order_id": order.id,
                        "sale_order_line_id": line.id,
                        "is_non_forecast": True,
                    }
                    if target_line:
                        allocation_vals["plan_line_id"] = target_line.id
                    allocation = ForecastAllocation.create(allocation_vals)
                    if not first_allocation:
                        first_allocation = allocation

                line.is_non_forecast = line_is_non_forecast
                line.forecast_allocation_id = first_allocation.id if first_allocation else False

    def action_view_forecast_allocations(self):
        self.ensure_one()
        action = self.env.ref("sale_forecast.action_forecast_allocation").read()[0]
        action["domain"] = [("sale_order_id", "=", self.id)]
        action["context"] = {
            "default_sale_order_id": self.id,
            "default_plan_id": self.forecast_allocation_ids[:1].plan_id.id,
        }
        return action


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    forecast_allocation_id = fields.Many2one("forecast.allocation", string="Forecast Allocation", index=True)
    is_forecast_allocation = fields.Boolean(string="From Forecast Allocation", default=False)
    is_non_forecast = fields.Boolean(string="Non-Forecast", default=False)
