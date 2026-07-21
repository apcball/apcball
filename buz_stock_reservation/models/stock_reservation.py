import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

ACTIVE_STATES = ("reserved", "partially_released")
FINAL_STATES = ("released", "delivered", "cancel")


class BuzStockReservation(models.Model):
    _name = "buz.stock.reservation"
    _description = "Stock Reservation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "reserved_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        string="Reservation No.",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        required=True,
        check_company=True,
        tracking=True,
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sales Order",
        check_company=True,
        index=True,
        tracking=True,
        domain="[('partner_id', 'child_of', partner_id)]",
    )
    reference = fields.Char(
        string="Reference",
        compute="_compute_reference",
        store=True,
        readonly=False,
        help="Source document (sales order, project code, ...).",
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        required=True,
        check_company=True,
        tracking=True,
        default=lambda self: self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        ),
    )
    reserved_date = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )
    expiry_date = fields.Datetime(
        required=True,
        default=lambda self: self._default_expiry_date(),
        tracking=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Salesperson",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    responsible_id = fields.Many2one(
        "res.users",
        string="Responsible",
        default=lambda self: self.env.user,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("reserved", "Reserved"),
            ("partially_released", "Partially Released"),
            ("released", "Released"),
            ("delivered", "Delivered"),
            ("expired", "Expired"),
            ("cancel", "Cancelled"),
        ],
        required=True,
        default="draft",
        tracking=True,
        copy=False,
        index=True,
    )
    expiring_soon = fields.Boolean(
        compute="_compute_expiring_soon",
        search="_search_expiring_soon",
    )
    days_to_expiry = fields.Integer(compute="_compute_expiring_soon")
    line_ids = fields.One2many(
        "buz.stock.reservation.line",
        "reservation_id",
        string="Reservation Lines",
        copy=True,
    )
    total_reserved_qty = fields.Float(
        string="Reserved Quantity",
        compute="_compute_totals",
        store=True,
    )
    total_released_qty = fields.Float(
        string="Released Quantity",
        compute="_compute_totals",
        store=True,
    )
    remaining_qty = fields.Float(
        string="Remaining Quantity",
        compute="_compute_totals",
        store=True,
    )
    product_count = fields.Integer(
        string="Total Products",
        compute="_compute_totals",
        store=True,
    )
    release_reason_id = fields.Many2one(
        "buz.reservation.release.reason",
        string="Release Reason",
        copy=False,
    )
    picking_ids = fields.One2many(
        "stock.picking",
        "buz_reservation_id",
        string="Deliveries",
        copy=False,
    )
    delivery_count = fields.Integer(compute="_compute_delivery_count")
    note = fields.Html(string="Notes")

    _sql_constraints = [
        ("name_uniq", "UNIQUE(name)", "Reservation number must be unique!"),
    ]

    # ── Defaults / helpers ───────────────────────────────────────

    @api.model
    def _default_expiry_date(self):
        days = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("buz_stock_reservation.default_expiry_days", 7)
        )
        return fields.Datetime.now() + timedelta(days=days)

    @api.model
    def _expiring_soon_days(self):
        return int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("buz_stock_reservation.expiring_soon_days", 2)
        )

    # ── Computes ─────────────────────────────────────────────────

    @api.depends("sale_order_id")
    def _compute_reference(self):
        for rec in self:
            if rec.sale_order_id:
                rec.reference = rec.sale_order_id.name

    @api.depends("expiry_date", "state")
    def _compute_expiring_soon(self):
        now = fields.Datetime.now()
        threshold = now + timedelta(days=self._expiring_soon_days())
        for rec in self:
            rec.days_to_expiry = (
                (rec.expiry_date - now).days if rec.expiry_date else 0
            )
            rec.expiring_soon = bool(
                rec.state in ACTIVE_STATES
                and rec.expiry_date
                and now <= rec.expiry_date <= threshold
            )

    def _search_expiring_soon(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            raise UserError(_("Unsupported search on Expiring Soon."))
        now = fields.Datetime.now()
        threshold = now + timedelta(days=self._expiring_soon_days())
        domain = [
            ("state", "in", ACTIVE_STATES),
            ("expiry_date", ">=", now),
            ("expiry_date", "<=", threshold),
        ]
        if (operator == "=") != value:
            return ["!"] + domain
        return domain

    @api.depends(
        "line_ids.reserved_qty", "line_ids.released_qty", "line_ids.remaining_qty"
    )
    def _compute_totals(self):
        for rec in self:
            rec.total_reserved_qty = sum(rec.line_ids.mapped("reserved_qty"))
            rec.total_released_qty = sum(rec.line_ids.mapped("released_qty"))
            rec.remaining_qty = sum(rec.line_ids.mapped("remaining_qty"))
            rec.product_count = len(rec.line_ids.product_id)

    def _compute_delivery_count(self):
        for rec in self:
            rec.delivery_count = len(rec.picking_ids)

    # ── CRUD ─────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("buz.stock.reservation")
                    or _("New")
                )
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_active(self):
        if any(rec.state not in ("draft", "cancel") for rec in self):
            raise UserError(
                _("Only draft or cancelled reservations can be deleted.")
            )

    def copy(self, default=None):
        default = dict(default or {}, name=_("New"), state="draft")
        return super().copy(default=default)

    # ── Actions ──────────────────────────────────────────────────

    def action_reserve(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft reservations can be reserved."))
            if not rec.line_ids:
                raise UserError(_("Add at least one product line before reserving."))
            rec._check_availability()
            rec.write({"state": "reserved"})
            rec._invalidate_product_availability()
        return True

    def action_open_release_wizard(self):
        self.ensure_one()
        if self.state not in ACTIVE_STATES + ("expired",):
            raise UserError(_("Only active or expired reservations can be released."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Release Reservation"),
            "res_model": "buz.reservation.release.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_reservation_id": self.id},
        }

    def action_open_extend_wizard(self):
        self.ensure_one()
        if self.state not in ACTIVE_STATES + ("expired",):
            raise UserError(_("Only active or expired reservations can be extended."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Extend Expiry Date"),
            "res_model": "buz.reservation.extend.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_reservation_id": self.id},
        }

    def action_cancel(self):
        for rec in self:
            if rec.state in FINAL_STATES:
                raise UserError(_("Reservation is already in a final state."))
            rec.write({"state": "cancel"})
            rec._invalidate_product_availability()
        return True

    def action_draft(self):
        for rec in self:
            if rec.state != "cancel":
                raise UserError(_("Only cancelled reservations can be reset to draft."))
            rec.write({"state": "draft"})
        return True

    def action_create_delivery(self):
        self.ensure_one()
        if self.state not in ACTIVE_STATES:
            raise UserError(_("Only active reservations can be delivered."))
        lines = self.line_ids.filtered(lambda l: l.remaining_qty > 0)
        if not lines:
            raise UserError(_("Nothing left to deliver."))
        picking_type = self.warehouse_id.out_type_id
        picking = self.env["stock.picking"].create(
            {
                "partner_id": self.partner_id.id,
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": self.partner_id.property_stock_customer.id,
                "origin": self.name,
                "company_id": self.company_id.id,
                "buz_reservation_id": self.id,
                "move_ids": [
                    fields.Command.create(
                        {
                            "name": line.product_id.display_name,
                            "product_id": line.product_id.id,
                            "product_uom": line.product_uom_id.id,
                            "product_uom_qty": line.remaining_qty,
                            "location_id": picking_type.default_location_src_id.id,
                            "location_dest_id": self.partner_id.property_stock_customer.id,
                            "company_id": self.company_id.id,
                        }
                    )
                    for line in lines
                ],
            }
        )
        picking.action_confirm()
        self.message_post(
            body=_("Delivery %s created from reservation.", picking.name)
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": picking.id,
            "view_mode": "form",
        }

    def action_view_deliveries(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Deliveries"),
            "res_model": "stock.picking",
            "view_mode": "tree,form",
            "domain": [("id", "in", self.picking_ids.ids)],
        }

    def action_mark_delivered(self):
        for rec in self:
            if rec.state not in ACTIVE_STATES:
                raise UserError(_("Only active reservations can be marked delivered."))
            rec.write({"state": "delivered"})
            rec._invalidate_product_availability()
        return True

    # ── Business logic ───────────────────────────────────────────

    def _check_availability(self):
        """Block over-reservation for non-managers."""
        self.ensure_one()
        if self.env.user.has_group(
            "buz_stock_reservation.group_buz_reservation_manager"
        ):
            return
        for line in self.line_ids:
            if (
                float_compare(
                    line.reserved_qty,
                    line.available_qty,
                    precision_rounding=line.product_uom_id.rounding,
                )
                > 0
            ):
                raise UserError(
                    _(
                        "Insufficient stock for '%(product)s': "
                        "available %(avail).2f, requested %(req).2f. "
                        "A reservation manager can override this check.",
                        product=line.product_id.display_name,
                        avail=line.available_qty,
                        req=line.reserved_qty,
                    )
                )

    def _apply_release(self, reason=None, note=None):
        """Set final state after wizard updated line released quantities."""
        for rec in self:
            if all(line.remaining_qty <= 0 for line in rec.line_ids):
                rec.state = "released"
            else:
                rec.state = "partially_released"
            if reason:
                rec.release_reason_id = reason
            body = _("Reservation released.")
            if reason:
                body += _(" Reason: %s.", reason.name)
            if note:
                body += " %s" % note
            rec.message_post(body=body)
            rec._invalidate_product_availability()

    def _invalidate_product_availability(self):
        products = self.line_ids.product_id
        if products:
            products.invalidate_recordset(
                ["buz_reserved_qty", "buz_available_qty"]
            )

    # ── Crons ────────────────────────────────────────────────────

    @api.model
    def _cron_expire_reservations(self):
        expired = self.search(
            [
                ("state", "in", ACTIVE_STATES),
                ("expiry_date", "<", fields.Datetime.now()),
            ]
        )
        for rec in expired:
            rec.write({"state": "expired"})
            rec._invalidate_product_availability()
            rec.message_post(
                body=_(
                    "Reservation expired on %s. Reserved quantities are "
                    "no longer counted against available stock.",
                    fields.Datetime.to_string(rec.expiry_date),
                ),
                partner_ids=rec.responsible_id.partner_id.ids,
            )
        if expired:
            _logger.info("Expired %d reservation(s).", len(expired))
        return len(expired)

    @api.model
    def _cron_notify_expiring_soon(self):
        soon = self.search([("expiring_soon", "=", True)])
        for rec in soon:
            existing = rec.activity_ids.filtered(
                lambda a: a.activity_type_id
                == self.env.ref("mail.mail_activity_data_todo")
            )
            if existing:
                continue
            rec.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("Reservation %s expiring soon", rec.name),
                user_id=(rec.responsible_id or rec.user_id).id,
                date_deadline=rec.expiry_date.date(),
            )
        return len(soon)


class BuzStockReservationLine(models.Model):
    _name = "buz.stock.reservation.line"
    _description = "Stock Reservation Line"
    _check_company_auto = True

    reservation_id = fields.Many2one(
        "buz.stock.reservation",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        related="reservation_id.company_id", store=True, index=True
    )
    partner_id = fields.Many2one(
        related="reservation_id.partner_id", store=True, string="Customer"
    )
    warehouse_id = fields.Many2one(
        related="reservation_id.warehouse_id", store=True
    )
    state = fields.Selection(
        related="reservation_id.state", store=True, string="Status"
    )
    expiry_date = fields.Datetime(
        related="reservation_id.expiry_date", store=True
    )
    reserved_date = fields.Datetime(
        related="reservation_id.reserved_date", store=True
    )
    product_id = fields.Many2one(
        "product.product",
        required=True,
        check_company=True,
        domain="[('type', 'in', ('product', 'consu'))]",
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        compute="_compute_product_uom_id",
        store=True,
        readonly=False,
        required=True,
        precompute=True,
    )
    reserved_qty = fields.Float(
        string="Reserved Qty", required=True, default=1.0
    )
    released_qty = fields.Float(string="Released Qty", copy=False)
    remaining_qty = fields.Float(
        string="Remaining Qty", compute="_compute_remaining_qty", store=True
    )
    available_qty = fields.Float(
        string="Available Qty", compute="_compute_available_qty"
    )

    @api.depends("product_id")
    def _compute_product_uom_id(self):
        for line in self:
            line.product_uom_id = line.product_id.uom_id

    @api.depends("reserved_qty", "released_qty")
    def _compute_remaining_qty(self):
        for line in self:
            line.remaining_qty = line.reserved_qty - line.released_qty

    @api.depends("product_id", "warehouse_id")
    def _compute_available_qty(self):
        for line in self:
            if not line.product_id:
                line.available_qty = 0.0
                continue
            product = line.product_id.with_context(
                warehouse=line.warehouse_id.id
            )
            line.available_qty = product.free_qty

    @api.constrains("reserved_qty", "released_qty")
    def _check_quantities(self):
        for line in self:
            if line.reserved_qty <= 0:
                raise UserError(_("Reserved quantity must be positive."))
            if line.released_qty < 0 or line.released_qty > line.reserved_qty:
                raise UserError(
                    _("Released quantity must be between 0 and the reserved quantity.")
                )


class StockPicking(models.Model):
    _inherit = "stock.picking"

    buz_reservation_id = fields.Many2one(
        "buz.stock.reservation", string="Reservation", copy=False, index=True
    )

    def _action_done(self):
        res = super()._action_done()
        for picking in self:
            reservation = picking.buz_reservation_id
            if reservation and reservation.state in ACTIVE_STATES:
                pending = reservation.picking_ids.filtered(
                    lambda p: p.state not in ("done", "cancel")
                )
                if not pending:
                    reservation.action_mark_delivered()
        return res
