from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

ACTIVE_LIKE_STATES = ("draft", "active")


class StockFreezePeriod(models.Model):
    _name = "stock.freeze.period"
    _description = "Stock Freeze Period"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    freeze_all_warehouses = fields.Boolean(
        string="Freeze All Warehouses",
        tracking=True,
        help="Freeze every internal location of every warehouse in the company.",
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Warehouse",
        check_company=True,
        tracking=True,
    )
    location_ids = fields.Many2many(
        "stock.location",
        "stock_freeze_period_location_rel",
        "period_id",
        "location_id",
        string="Locations",
        check_company=True,
        domain="[('usage', '=', 'internal')]",
    )
    date_start = fields.Datetime(required=True, tracking=True)
    date_end = fields.Datetime(required=True, tracking=True)
    reason = fields.Text()
    allow_inventory_adjustment = fields.Boolean(
        string="Allow Inventory Adjustment",
        default=True,
        tracking=True,
    )
    allow_manager_override = fields.Boolean(
        string="Allow Manager Override",
        default=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("done", "Ended"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    started_by_id = fields.Many2one("res.users", string="Started By", readonly=True)
    started_at = fields.Datetime(string="Started At", readonly=True)
    ended_by_id = fields.Many2one("res.users", string="Ended By", readonly=True)
    ended_at = fields.Datetime(string="Ended At", readonly=True)

    location_summary = fields.Char(
        string="Frozen Scope",
        compute="_compute_location_summary",
    )

    # ------------------------------------------------------------------
    # Compute / helpers
    # ------------------------------------------------------------------
    @api.depends("warehouse_id", "location_ids", "freeze_all_warehouses")
    def _compute_location_summary(self):
        for period in self:
            if period.location_ids:
                period.location_summary = ", ".join(
                    period.location_ids.mapped("display_name")
                )
            elif period.freeze_all_warehouses:
                period.location_summary = _("ทุกคลังสินค้า")
            elif period.warehouse_id:
                period.location_summary = period.warehouse_id.display_name
            else:
                period.location_summary = ""

    def _get_frozen_location_ids(self):
        """Resolve the set of internal location ids frozen by this period.

        Resolved fresh on every call (never cached / stored) so that child
        locations created after the period was saved are still covered.
        """
        self.ensure_one()
        if self.freeze_all_warehouses:
            base = self.env["stock.warehouse"].search(
                [("company_id", "=", self.company_id.id)]
            ).view_location_id
        elif self.location_ids:
            base = self.location_ids
        elif self.warehouse_id:
            base = self.warehouse_id.view_location_id
        else:
            return []
        if not base:
            return []
        locations = self.env["stock.location"].search(
            [("id", "child_of", base.ids), ("usage", "=", "internal")]
        )
        return locations.ids

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for period in self:
            if period.date_start and period.date_end and period.date_end <= period.date_start:
                raise ValidationError(
                    _("End Date/Time must be later than Start Date/Time.")
                )

    @api.constrains("warehouse_id", "location_ids", "freeze_all_warehouses")
    def _check_scope_defined(self):
        for period in self:
            if (
                not period.freeze_all_warehouses
                and not period.warehouse_id
                and not period.location_ids
            ):
                raise ValidationError(
                    _(
                        "Define a warehouse, at least one location, or tick "
                        "Freeze All Warehouses."
                    )
                )

    @api.constrains(
        "date_start",
        "date_end",
        "warehouse_id",
        "location_ids",
        "freeze_all_warehouses",
        "state",
        "company_id",
    )
    def _check_overlap(self):
        for period in self:
            if period.state not in ACTIVE_LIKE_STATES:
                continue
            if not period.date_start or not period.date_end:
                continue
            others = self.search(
                [
                    ("id", "!=", period.id),
                    ("company_id", "=", period.company_id.id),
                    ("state", "in", list(ACTIVE_LIKE_STATES)),
                    ("date_start", "<", period.date_end),
                    ("date_end", ">", period.date_start),
                ]
            )
            if not others:
                continue
            frozen = set(period._get_frozen_location_ids())
            if not frozen:
                continue
            for other in others:
                if frozen & set(other._get_frozen_location_ids()):
                    raise ValidationError(
                        _(
                            "Another stock freeze period overlaps with this "
                            "location and time period."
                        )
                    )

    # ------------------------------------------------------------------
    # Write / unlink guards
    # ------------------------------------------------------------------
    _LOCKED_FIELDS_WHEN_ACTIVE = (
        "company_id",
        "warehouse_id",
        "location_ids",
        "freeze_all_warehouses",
        "date_start",
    )

    def write(self, vals):
        locked = set(self._LOCKED_FIELDS_WHEN_ACTIVE) & set(vals)
        if locked:
            for period in self:
                if period.state == "active":
                    raise UserError(
                        _(
                            "Cannot change company, warehouse, locations or "
                            "start date while the freeze is active."
                        )
                    )
        if "date_end" in vals and vals["date_end"]:
            new_end = fields.Datetime.to_datetime(vals["date_end"])
            for period in self:
                if period.state == "active" and new_end <= fields.Datetime.now():
                    raise UserError(
                        _("The new end date must be later than the current time.")
                    )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft_or_cancel(self):
        for period in self:
            if period.state not in ("draft", "cancel"):
                raise UserError(
                    _(
                        "Only Draft or Cancelled stock freeze periods can be "
                        "deleted."
                    )
                )

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------
    def action_start_freeze(self):
        for period in self:
            if period.state != "draft":
                raise UserError(_("Only draft freeze periods can be started."))
            period._check_dates()
            period._check_scope_defined()
            period.write(
                {
                    "state": "active",
                    "started_by_id": self.env.user.id,
                    "started_at": fields.Datetime.now(),
                }
            )
            period.message_post(
                body=_("Stock Freeze started by %s", self.env.user.display_name)
            )
        return True

    def action_end_freeze(self):
        for period in self:
            if period.state != "active":
                raise UserError(_("Only active freeze periods can be ended."))
            period.write(
                {
                    "state": "done",
                    "ended_by_id": self.env.user.id,
                    "ended_at": fields.Datetime.now(),
                }
            )
            period.message_post(
                body=_("Stock Freeze ended by %s", self.env.user.display_name)
            )
        return True

    def action_cancel(self):
        for period in self:
            if period.state not in ("draft", "active"):
                raise UserError(
                    _("Only draft or active freeze periods can be cancelled.")
                )
            was_active = period.state == "active"
            period.write({"state": "cancel"})
            if was_active:
                period.message_post(
                    body=_(
                        "Stock Freeze cancelled by %s",
                        self.env.user.display_name,
                    )
                )
        return True

    def action_reset_to_draft(self):
        for period in self:
            if period.state != "cancel":
                raise UserError(
                    _("Only cancelled freeze periods can be reset to draft.")
                )
            period.write(
                {
                    "state": "draft",
                    "started_by_id": False,
                    "started_at": False,
                    "ended_by_id": False,
                    "ended_at": False,
                }
            )
        return True

    # ------------------------------------------------------------------
    # Cron
    # ------------------------------------------------------------------
    @api.model
    def _cron_update_status(self):
        now = fields.Datetime.now()
        to_start = self.search(
            [
                ("state", "=", "draft"),
                ("date_start", "<=", now),
                ("date_end", ">", now),
            ]
        )
        for period in to_start:
            period.write(
                {
                    "state": "active",
                    "started_by_id": self.env.user.id,
                    "started_at": now,
                }
            )
            period.message_post(body=_("Stock Freeze auto-started by scheduler"))

        to_end = self.search(
            [
                ("state", "=", "active"),
                ("date_end", "<", now),
            ]
        )
        for period in to_end:
            period.write(
                {
                    "state": "done",
                    "ended_by_id": self.env.user.id,
                    "ended_at": now,
                }
            )
            period.message_post(body=_("Stock Freeze auto-ended by scheduler"))
        return True

    # ------------------------------------------------------------------
    # Enforcement (called from stock.move._action_done)
    # ------------------------------------------------------------------
    @staticmethod
    def _move_is_inventory_adjustment(move):
        """A genuine Inventory Adjustment move always has one leg on an
        ``inventory`` usage location (``property_stock_inventory``).  Package
        relocations / unpack also set ``is_inventory`` but move internal ->
        internal, so they are *not* treated as adjustments here.
        """
        return move.is_inventory and "inventory" in (
            move.location_id.usage,
            move.location_dest_id.usage,
        )

    def _check_moves(self, moves):
        """Raise :class:`UserError` for any move that would change on-hand
        quantity inside a frozen location without entitlement.

        :return: dict ``{period_id: set(move_ids)}`` for moves that were only
            allowed through an override - to be logged after ``super()``.
        """
        relevant = moves.filtered(
            lambda m: m.state not in ("done", "cancel")
            and (m.quantity > 0 or m.is_inventory)
        )
        if not relevant:
            return {}
        company_ids = relevant.company_id.ids
        if not company_ids:
            return {}

        # ``self`` may be sudo-ed (called as ``sudo()._check_moves``) so we
        # evaluate entitlement against the *real* caller carried by ``moves``.
        # No blanket superuser / sudo exemption: scheduled actions, imports and
        # RPC-created moves must be blocked too (spec sections 32 & 33).
        caller_env = moves.env
        caller_user = caller_env.user

        now = fields.Datetime.now()
        periods = self.search(
            [
                ("state", "=", "active"),
                ("date_start", "<=", now),
                ("date_end", ">=", now),
                ("company_id", "in", company_ids),
            ]
        )
        if not periods:
            return {}

        is_override_user = caller_user.has_group(
            "buz_stock_freeze.group_stock_freeze_override"
        )
        blocked = defaultdict(lambda: self.env["stock.move"])
        override_map = defaultdict(set)

        for period in periods:
            frozen = set(period._get_frozen_location_ids())
            if not frozen:
                continue
            for move in relevant:
                if move.company_id != period.company_id:
                    continue
                if not ({move.location_id.id, move.location_dest_id.id} & frozen):
                    continue
                if (
                    period.allow_inventory_adjustment
                    and self._move_is_inventory_adjustment(move)
                ):
                    continue
                if period.allow_manager_override and is_override_user:
                    override_map[period.id].add(move.id)
                    continue
                blocked[period.id] |= move

        if blocked:
            period = self.browse(next(iter(blocked)))
            moves_blocked = blocked[period.id]
            tz_start = fields.Datetime.context_timestamp(period, period.date_start)
            tz_end = fields.Datetime.context_timestamp(period, period.date_end)
            locations = (
                moves_blocked.location_id | moves_blocked.location_dest_id
            ).filtered(lambda loc: loc.id in set(period._get_frozen_location_ids()))
            raise UserError(
                _(
                    "ขณะนี้ระบบล็อกความเคลื่อนไหวของสต๊อกไว้ "
                    "เนื่องจากอยู่ระหว่างการตรวจนับสินค้าคงคลัง\n\n"
                    "รายการล็อกสต๊อก: %(freeze)s\n"
                    "สถานที่: %(location)s\n"
                    "ช่วงเวลา: %(start)s - %(end)s\n\n"
                    "หากจำเป็นต้องทำรายการนี้ กรุณาติดต่อแผนกบัญชี Stock"
                )
                % {
                    "freeze": period.name,
                    "location": ", ".join(locations.mapped("display_name"))
                    or period.location_summary,
                    "start": fields.Datetime.to_string(tz_start),
                    "end": fields.Datetime.to_string(tz_end),
                }
            )
        return {pid: mids for pid, mids in override_map.items()}

    def _log_overrides(self, override_map, done_moves):
        if not override_map:
            return
        actor = done_moves.env.user if done_moves else self.env.user
        done_by_id = {m.id: m for m in done_moves}
        for period_id, move_ids in override_map.items():
            period = self.browse(period_id)
            moves = self.env["stock.move"].browse(
                [mid for mid in move_ids if mid in done_by_id]
            )
            if not moves:
                # split move - report the originally requested moves instead
                moves = self.env["stock.move"].browse(list(move_ids)).exists()
            if not moves:
                continue
            docs = defaultdict(lambda: self.env["stock.move"])
            for move in moves:
                doc = (
                    move.picking_id
                    or move.raw_material_production_id
                    or move.production_id
                    or move
                )
                docs[doc] |= move
            for doc, doc_moves in docs.items():
                lines = []
                for move in doc_moves:
                    lines.append(
                        _(
                            "Product: %(product)s | Source: %(src)s | "
                            "Destination: %(dest)s | Quantity: %(qty)s %(uom)s"
                        )
                        % {
                            "product": move.product_id.display_name,
                            "src": move.location_id.display_name,
                            "dest": move.location_dest_id.display_name,
                            "qty": move.quantity,
                            "uom": move.product_uom.name or "",
                        }
                    )
                ref = doc.display_name if doc._name != "stock.move" else _("Direct move")
                period.message_post(
                    body=_(
                        "Stock Freeze overridden by %(user)s\n\n"
                        "Operation: %(ref)s\n%(lines)s"
                    )
                    % {
                        "user": actor.display_name,
                        "ref": ref,
                        "lines": "\n".join(lines),
                    }
                )

    @api.model
    def _get_active_periods_for_locations(self, company, location_ids):
        """Helper for the picking warning banner."""
        now = fields.Datetime.now()
        periods = self.search(
            [
                ("state", "=", "active"),
                ("date_start", "<=", now),
                ("date_end", ">=", now),
                ("company_id", "=", company.id),
            ]
        )
        target = set(location_ids)
        return periods.filtered(
            lambda p: target & set(p._get_frozen_location_ids())
        )
