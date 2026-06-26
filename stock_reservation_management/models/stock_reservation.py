import logging
from datetime import timedelta, date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class StockReservation(models.Model):
    """Advanced sales reservation model with expiration, approval, and priority."""

    _name = "stock.reservation"
    _description = "Stock Reservation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority_level DESC, create_date DESC"
    _check_company_auto = True

    # ── Basic Fields ──────────────────────────────────────────────
    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    customer_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sales Order",
        domain="[('company_id', '=', company_id)]",
        index=True,
        tracking=True,
    )
    reservation_type = fields.Selection(
        selection=[
            ("sale", "Sale"),
            ("vip", "VIP"),
            ("campaign", "Campaign"),
            ("service", "Service"),
            ("project", "Project"),
        ],
        string="Reservation Type",
        required=True,
        default="sale",
        tracking=True,
    )
    priority = fields.Selection(
        selection=[
            ("critical", "Critical"),
            ("vip", "VIP"),
            ("normal", "Normal"),
            ("low", "Low"),
        ],
        string="Priority",
        required=True,
        default="normal",
        tracking=True,
    )
    priority_level = fields.Integer(
        string="Priority Level",
        compute="_compute_priority_level",
        store=True,
        index=True,
    )
    reserve_date = fields.Date(
        string="Reservation Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    expire_date = fields.Date(
        string="Expiration Date",
        required=True,
        compute="_compute_expire_date",
        store=True,
        readonly=False,
        tracking=True,
    )
    warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse",
        string="Warehouse",
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("waiting_approval", "Waiting Approval"),
            ("reserved", "Reserved"),
            ("allocated", "Allocated"),
            ("delivered", "Delivered"),
            ("expired", "Expired"),
            ("released", "Released"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        required=True,
        default="draft",
        tracking=True,
        copy=False,
    )
    note = fields.Html(string="Notes")

    # ── Line Fields ──────────────────────────────────────────────
    line_ids = fields.One2many(
        comodel_name="stock.reservation.line",
        inverse_name="reservation_id",
        string="Reservation Lines",
        copy=True,
    )
    line_count = fields.Integer(
        string="Line Count",
        compute="_compute_line_count",
        store=True,
    )
    total_reserve_qty = fields.Float(
        string="Total Reserved Qty",
        compute="_compute_total_qty",
        store=True,
        group_operator="sum",
    )
    total_allocated_qty = fields.Float(
        string="Total Allocated Qty",
        compute="_compute_total_qty",
        store=True,
        group_operator="sum",
    )
    total_released_qty = fields.Float(
        string="Total Released Qty",
        compute="_compute_total_qty",
        store=True,
        group_operator="sum",
    )

    # ── Activity / Notification Fields ───────────────────────────
    activity_ids = fields.One2many(
        comodel_name="mail.activity",
        inverse_name="res_id",
        string="Activities",
        domain=lambda self: [("res_model", "=", self._name)],
    )
    activity_state = fields.Selection(
        string="Next Activity State",
        related="activity_ids.state",
        groups="base.group_user",
        store=True,
    )
    activity_summary = fields.Char(
        string="Next Activity Summary",
        related="activity_ids.summary",
        groups="base.group_user",
    )

    # ── Constraints ──────────────────────────────────────────────
    _sql_constraints = [
        (
            "reservation_name_uniq",
            "UNIQUE(name)",
            "Reservation reference must be unique!",
        ),
    ]

    # ── Computed Methods ─────────────────────────────────────────

    @api.depends("priority")
    def _compute_priority_level(self):
        """Map priority selection to numeric level for ordering."""
        priority_map = {
            "critical": 100,
            "vip": 80,
            "normal": 50,
            "low": 20,
        }
        for rec in self:
            rec.priority_level = priority_map.get(rec.priority, 50)

    @api.depends("reservation_type")
    def _compute_expire_date(self):
        """Compute default expiration based on reservation type."""
        now = fields.Date.context_today(self)
        for rec in self:
            if not rec.expire_date:
                if rec.reservation_type == "vip":
                    rec.expire_date = now + relativedelta(days=30)
                elif rec.reservation_type == "campaign":
                    rec.expire_date = now + relativedelta(days=14)
                elif rec.reservation_type == "sale":
                    rec.expire_date = now + relativedelta(days=7)
                elif rec.reservation_type == "service":
                    rec.expire_date = now + relativedelta(days=15)
                elif rec.reservation_type == "project":
                    rec.expire_date = now + relativedelta(days=90)
                else:
                    rec.expire_date = now + relativedelta(days=7)

    @api.depends("line_ids")
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    @api.depends("line_ids.reserve_qty", "line_ids.allocated_qty", "line_ids.released_qty")
    def _compute_total_qty(self):
        for rec in self:
            rec.total_reserve_qty = sum(rec.line_ids.mapped("reserve_qty"))
            rec.total_allocated_qty = sum(rec.line_ids.mapped("allocated_qty"))
            rec.total_released_qty = sum(rec.line_ids.mapped("released_qty"))

    # ── Sequence ────────────────────────────────────────────────

    @api.model
    def create(self, vals):
        if vals.get("name", _("New")) == _("New"):
            vals["name"] = self.env["ir.sequence"].next_by_code("stock.reservation") or _("New")
        return super().create(vals)

    # ── Action Methods ───────────────────────────────────────────

    def action_reserve(self):
        """Transition from draft/waiting_approval to reserved state."""
        self._check_reservation_stock()
        for rec in self:
            if rec.state not in ("draft", "waiting_approval"):
                raise UserError(_("Only draft or waiting approval reservations can be reserved."))
            rec.write({"state": "reserved"})
            rec._update_product_reserved_qty()
        return True

    def action_allocate(self):
        """Mark reservation as allocated (stock physically allocated)."""
        for rec in self:
            if rec.state != "reserved":
                raise UserError(_("Only reserved reservations can be allocated."))
            rec.write({"state": "allocated"})
        return True

    def action_deliver(self):
        """Mark reservation lines as delivered."""
        for rec in self:
            if rec.state != "allocated":
                raise UserError(_("Only allocated reservations can be delivered."))
            rec.write({"state": "delivered"})
            rec.line_ids.write({"released_qty": 0.0})
        return True

    def action_expire(self):
        """Expire reservation manually."""
        for rec in self:
            if rec.state in ("expired", "released", "cancel", "delivered"):
                raise UserError(_("Reservation is already in a final state."))
            rec.write({"state": "expired"})
            rec._release_reserved_qty()
            rec._notify_expiration()
        return True

    def action_release(self):
        """Release the reservation, returning qty to available stock."""
        for rec in self:
            if rec.state in ("released", "cancel", "delivered"):
                raise UserError(_("Reservation is already released or in a final state."))
            if rec.state == "draft":
                rec.write({"state": "cancel"})
            else:
                rec.write({"state": "released"})
                rec._release_reserved_qty()
        return True

    def action_cancel(self):
        """Cancel the reservation."""
        for rec in self:
            if rec.state in ("delivered", "released", "cancel"):
                raise UserError(_("Cannot cancel a reservation in a final state."))
            if rec.state in ("reserved", "allocated"):
                rec._release_reserved_qty()
            rec.write({"state": "cancel"})
        return True

    def action_draft(self):
        """Reset to draft."""
        for rec in self:
            rec.write({"state": "draft"})

    def action_request_approval(self):
        """Request approval when stock is insufficient."""
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft reservations can request approval."))
            rec.write({"state": "waiting_approval"})
            rec._create_approval_activity()
        return True

    def action_approve(self):
        """Approve reservation (manager override for shortages)."""
        for rec in self:
            if rec.state != "waiting_approval":
                raise UserError(_("Only reservations waiting approval can be approved."))
            rec.write({"state": "reserved"})
            rec._update_product_reserved_qty()
        return True

    def action_approve_and_allocate(self):
        """Approve and allocate in one step."""
        self.action_approve()
        self.action_allocate()

    # ── Business Logic ───────────────────────────────────────────

    def _check_reservation_stock(self):
        """Validate that reservation does not exceed available stock (unless manager override)."""
        for rec in self:
            for line in rec.line_ids:
                available = line.available_qty
                if line.reserve_qty > available:
                    # Check if current user is a manager
                    if not self.env.user.has_group(
                        "stock_reservation_management.group_reservation_manager"
                    ):
                        raise UserError(
                            _(
                                "Insufficient stock for product '%(product)s'. "
                                "Available: %(avail).2f, Requested: %(req).2f. "
                                "Contact a manager to approve this reservation."
                            )
                            % {
                                "product": line.product_id.display_name,
                                "avail": available,
                                "req": line.reserve_qty,
                            }
                        )

    def _update_product_reserved_qty(self):
        """Update computed reserved qty on products when reservation is confirmed."""
        products = self.line_ids.product_id
        if products:
            products.invalidate_recordset(["reserved_qty", "available_after_reserve"])
            products._compute_reserved_qty()

    def _release_reserved_qty(self):
        """Release reserved quantities back to available stock."""
        for rec in self:
            for line in rec.line_ids:
                line.write({"released_qty": line.reserve_qty - line.allocated_qty + line.released_qty})
            # Update product computed fields
            products = rec.line_ids.product_id
            if products:
                products.invalidate_recordset(["reserved_qty", "available_after_reserve"])
                products._compute_reserved_qty()

    def _notify_expiration(self):
        """Notify the responsible user about expiration."""
        for rec in self:
            if rec.user_id:
                rec.message_post(
                    body=_(
                        "Reservation %(ref)s has expired. "
                        "Reserved quantities have been released back to stock."
                    )
                    % {"ref": rec.name},
                    partner_ids=[rec.user_id.partner_id.id],
                )

    def _create_approval_activity(self):
        """Create a mail activity for managers to approve."""
        for rec in self:
            manager_group = self.env.ref(
                "stock_reservation_management.group_reservation_manager", raise_if_not_found=False
            )
            if manager_group:
                managers = manager_group.users
                rec.activity_schedule(
                    "mail.mail_activity_data_warning",
                    summary=_("Reservation %s requires approval") % rec.name,
                    user_id=rec.user_id.id if rec.user_id else self.env.user.id,
                    note=_(
                        "Reservation %(ref)s requires approval due to stock constraints.\n"
                        "Customer: %(customer)s\n"
                        "Total Qty: %(qty).2f"
                    )
                    % {
                        "ref": rec.name,
                        "customer": rec.customer_id.name,
                        "qty": rec.total_reserve_qty,
                    },
                    recommended_activity_ids=[(4, manager.id) for manager in managers]
                    if managers
                    else [],
                )

    # ── Cron Jobs ───────────────────────────────────────────────

    @api.model
    def _cron_expire_reservations(self):
        """Daily cron: expire reservations past their expire_date."""
        today = fields.Date.context_today(self)
        domain = [
            ("state", "in", ("draft", "reserved", "allocated")),
            ("expire_date", "<", today),
        ]
        expired = self.search(domain)
        expired_count = len(expired)
        for rec in expired:
            rec.write({"state": "expired"})
            rec._release_reserved_qty()
            rec._notify_expiration()
        if expired_count:
            _logger.info("Expired %d reservation(s) via cron job.", expired_count)
        return expired_count

    @api.model
    def _cron_auto_release_expired(self):
        """Daily cron: auto-release already expired reservations."""
        domain = [
            ("state", "=", "expired"),
        ]
        expired = self.search(domain)
        count = len(expired)
        for rec in expired:
            rec.write({"state": "released"})
            rec._release_reserved_qty()
        if count:
            _logger.info("Auto-released %d expired reservation(s) via cron job.", count)
        return count

    @api.model
    def _cron_notify_near_expiry(self):
        """Daily cron: notify users about reservations expiring soon."""
        today = fields.Date.context_today(self)
        warning_days = 2
        domain = [
            ("state", "in", ("draft", "reserved", "allocated")),
            ("expire_date", ">=", today),
            ("expire_date", "<=", today + timedelta(days=warning_days)),
        ]
        near_expiry = self.search(domain)
        for rec in near_expiry:
            if rec.user_id:
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=_("Reservation %s expiring soon") % rec.name,
                    user_id=rec.user_id.id,
                    date_deadline=rec.expire_date,
                    note=_(
                        "Reservation %(ref)s will expire on %(date)s. "
                        "Please take necessary action."
                    )
                    % {"ref": rec.name, "date": rec.expire_date},
                )
        return len(near_expiry)

    # ── Overrides ───────────────────────────────────────────────

    def unlink(self):
        """Prevent deletion of non-draft reservations."""
        for rec in self:
            if rec.state not in ("draft", "cancel"):
                raise UserError(
                    _("Cannot delete reservation %(ref)s in state '%(state)s'.")
                    % {"ref": rec.name, "state": rec.state}
                )
        return super().unlink()

    def copy(self, default=None):
        default = dict(default or {})
        default.update(
            {
                "state": "draft",
                "name": _("New"),
            }
        )
        return super().copy(default=default)
