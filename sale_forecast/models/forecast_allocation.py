from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ForecastAllocation(models.Model):
    _name = "forecast.allocation"
    _description = "Forecast Allocation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(
        string="Allocation Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("cancel", "Cancelled")],
        default="confirmed",
        tracking=True,
    )

    plan_id = fields.Many2one("forecast.plan", required=True, index=True, ondelete="cascade")
    plan_line_id = fields.Many2one(
        "forecast.line",
        index=True,
        domain="[('plan_id', '=', plan_id)]",
        ondelete="set null",
    )
    product_id = fields.Many2one("product.product", required=True, domain=[("sale_ok", "=", True)], index=True)
    allocated_qty = fields.Float(required=True, digits="Product Unit of Measure")
    is_non_forecast = fields.Boolean(string="Non-Forecast", default=False)

    sale_order_id = fields.Many2one("sale.order", required=True, index=True)
    sale_order_line_id = fields.Many2one("sale.order.line", readonly=True, ondelete="restrict")
    customer_id = fields.Many2one(related="sale_order_id.partner_id", store=True, readonly=True)
    salesperson_id = fields.Many2one(related="sale_order_id.user_id", store=True, readonly=True)
    order_date = fields.Datetime(related="sale_order_id.date_order", store=True, readonly=True)
    company_id = fields.Many2one(related="plan_id.company_id", store=True, index=True)
    month = fields.Date(compute="_compute_month", store=True)

    actual_sold_qty = fields.Float(
        string="Actual Sold Qty",
        compute="_compute_actual_sold_qty",
        store=True,
        digits="Product Unit of Measure",
    )

    @api.depends("order_date")
    def _compute_month(self):
        for rec in self:
            rec.month = fields.Date.start_of(rec.order_date.date(), "month") if rec.order_date else False

    @api.depends(
        "sale_order_line_id.qty_delivered",
        "sale_order_line_id.product_uom_qty",
        "sale_order_id.state",
        "state",
    )
    def _compute_actual_sold_qty(self):
        for rec in self:
            if rec.state == "cancel":
                rec.actual_sold_qty = 0.0
            elif rec.sale_order_id.state in ("sale", "done") and rec.sale_order_line_id:
                rec.actual_sold_qty = rec.sale_order_line_id.qty_delivered or rec.sale_order_line_id.product_uom_qty
            else:
                rec.actual_sold_qty = 0.0

    @api.onchange("plan_line_id")
    def _onchange_plan_line_id(self):
        for rec in self:
            if rec.plan_line_id:
                rec.product_id = rec.plan_line_id.product_id

    @api.constrains("plan_id", "plan_line_id", "product_id", "is_non_forecast")
    def _check_plan_line_consistency(self):
        for rec in self:
            if rec.plan_line_id and rec.plan_id != rec.plan_line_id.plan_id:
                raise ValidationError(_("Selected forecast line does not belong to selected forecast plan."))
            if rec.plan_line_id and rec.product_id != rec.plan_line_id.product_id:
                raise ValidationError(_("Selected forecast line product must match the allocation product."))

    @api.constrains("sale_order_id", "sale_order_line_id")
    def _check_sale_order_line_consistency(self):
        """
        Ensure sale_order_line_id belongs to sale_order_id.

        This constraint ensures data integrity when ondelete="restrict" is used.
        Since sale_order_line_id cannot be deleted while allocations reference it,
        this prevents orphaned allocations if the relationship is manually broken.
        """
        for rec in self:
            if rec.sale_order_line_id and rec.sale_order_line_id.order_id != rec.sale_order_id:
                raise ValidationError(
                    _(
                        "Sale order line '%s' does not belong to sale order '%s'. "
                        "Please ensure the allocation references the correct sale order line."
                    )
                    % (rec.sale_order_line_id.display_name, rec.sale_order_id.name)
                )

    @api.constrains("plan_id", "sale_order_id")
    def _check_cross_user_allocation(self):
        """
        Prevent cross-user allocations.

        Ensure that sale order and forecast plan belong to the same user.
        This prevents users from allocating to other users' forecast plans.

        Business Logic:
        - Salesperson should allocate to their own forecast plan
        - Prevents unauthorized access to other users' forecasts
        - Ensures proper accountability and tracking
        """
        for rec in self:
            if rec.plan_id and rec.sale_order_id:
                so_user = rec.sale_order_id.user_id
                plan_user = rec.plan_id.user_id

                if so_user and plan_user and so_user != plan_user:
                    raise ValidationError(
                        _(
                            "Cannot allocate sale order '%s' (salesperson: %s) "
                            "to forecast plan '%s' (user: %s). "
                            "\n\n"
                            "Sales orders can only be allocated to forecast plans "
                            "that belong to the same user. "
                            "Please select a forecast plan belonging to '%s'."
                        )
                        % (
                            rec.sale_order_id.name,
                            so_user.name,
                            rec.plan_id.name,
                            plan_user.name,
                            so_user.name,
                        )
                    )

    @api.constrains("allocated_qty")
    def _check_allocated_qty_positive(self):
        for rec in self:
            if rec.allocated_qty <= 0:
                raise ValidationError(_("Allocated quantity must be greater than 0."))

    @api.constrains("allocated_qty", "state", "plan_line_id")
    def _check_over_allocation(self):
        for rec in self.filtered(lambda x: x.state != "cancel" and x.plan_line_id and not x.is_non_forecast):
            others = rec.plan_line_id.allocation_ids.filtered(
                lambda a: a.id != rec.id and a.state != "cancel"
            )
            available = rec.plan_line_id.forecast_qty - sum(others.mapped("allocated_qty"))
            if rec.allocated_qty > available:
                raise ValidationError(
                    _(
                        "Cannot allocate %(qty)s for %(product)s. Available quantity is %(available)s."
                    )
                    % {
                        "qty": rec.allocated_qty,
                        "product": rec.product_id.display_name,
                        "available": available,
                    }
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("forecast.allocation") or _("New")
            if vals.get("plan_line_id") and not vals.get("product_id"):
                plan_line = self.env["forecast.line"].browse(vals["plan_line_id"])
                vals["product_id"] = plan_line.product_id.id
            vals.setdefault("is_non_forecast", False)
        allocations = super().create(vals_list)
        for rec in allocations:
            rec._create_or_update_sale_order_line()
        return allocations

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            if rec.state != "cancel":
                rec._create_or_update_sale_order_line(update_existing=True)
        return res

    def _create_or_update_sale_order_line(self, update_existing=False):
        self.ensure_one()
        if self.state == "cancel":
            return

        line_vals = {
            "order_id": self.sale_order_id.id,
            "product_id": self.product_id.id,
            "name": self.product_id.display_name,
            "product_uom_qty": self.allocated_qty,
            "price_unit": self.product_id.lst_price,
            "forecast_allocation_id": self.id,
            "is_forecast_allocation": not self.is_non_forecast,
            "is_non_forecast": self.is_non_forecast,
        }

        if self.sale_order_line_id and update_existing:
            self.sale_order_line_id.write({
                "product_id": self.product_id.id,
                "name": self.product_id.display_name,
                "product_uom_qty": self.allocated_qty,
                "price_unit": self.product_id.lst_price,
                "is_forecast_allocation": not self.is_non_forecast,
                "is_non_forecast": self.is_non_forecast,
            })
        elif not self.sale_order_line_id:
            self.sale_order_line_id = self.env["sale.order.line"].create(line_vals)

    def action_cancel(self):
        for rec in self:
            rec.state = "cancel"

    def action_confirm(self):
        for rec in self:
            rec.state = "confirmed"
