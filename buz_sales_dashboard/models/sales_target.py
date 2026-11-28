from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

MAX_AMOUNT = 1e13
MAX_CHANGES = 2000


class SalesTarget(models.Model):
    """Monthly sales target of a salesperson or of a sales team."""

    _name = "buz.sales.target"
    _inherit = "buz.sales.dashboard.viewer"
    _description = "Monthly Sales Target"
    _order = "month desc, level, user_id, team_id"
    _check_company_auto = True

    month = fields.Date(
        "เดือน", required=True, index=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
        help="เลือกวันใดก็ได้ในเดือน ระบบเก็บเป็นวันที่ 1")
    level = fields.Selection(
        [("user", "รายคน"), ("team", "รายทีม")], "ระดับ",
        required=True, default="user")
    user_id = fields.Many2one(
        "res.users", "พนักงานขาย", index=True, ondelete="cascade",
        domain=[("share", "=", False)])
    team_id = fields.Many2one("crm.team", "ทีมขาย", index=True, ondelete="cascade")
    amount = fields.Monetary("เป้ายอดขาย (ก่อน VAT)", required=True)
    company_id = fields.Many2one(
        "res.company", "บริษัท", required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")

    # a person row has no team and a team row no person, so each constraint
    # only ever applies to its own level (empty values never collide)
    _sql_constraints = [
        ("user_month_uniq", "unique(company_id, month, user_id)",
         "พนักงานขายคนนี้มีเป้าของเดือนนี้แล้ว"),
        ("team_month_uniq", "unique(company_id, month, team_id)",
         "ทีมนี้มีเป้าของเดือนนี้แล้ว"),
        ("amount_positive", "CHECK(amount >= 0)", "เป้าต้องไม่ติดลบ"),
    ]

    @api.depends("month", "level", "user_id", "team_id")
    def _compute_display_name(self):
        for target in self:
            owner = target.user_id if target.level == "user" else target.team_id
            target.display_name = "%s %s" % (
                owner.display_name or "-",
                target.month.strftime("%m/%Y") if target.month else "")

    @api.onchange("level")
    def _onchange_level(self):
        if self.level == "user":
            self.team_id = False
        else:
            self.user_id = False

    @api.model
    def _first_of_month(self, vals):
        if vals.get("month"):
            vals = dict(vals, month=fields.Date.to_date(vals["month"]).replace(day=1))
        return vals

    @api.model
    def _editable_owners(self):
        """Whose targets the user may set: None for everybody, otherwise
        {"team": ids, "user": ids} (both empty when not a team leader).

        The record rules enforce the same; this serves the Excel import.
        """
        if self.env.su or self.env.user.has_group(
                "buz_sales_dashboard.group_target_manager"):
            return None
        teams = self.env["crm.team"].sudo().search([("user_id", "=", self.env.uid)])
        members = self.env["crm.team.member"].sudo().search(
            [("crm_team_id", "in", teams.ids)])
        return {"team": set(teams.ids), "user": set(members.user_id.ids)}

    # ------------------------------------------------------------ board
    @api.model
    def get_board(self, month):
        """One month of targets, team by team, with the month before.

        Record rules decide what is read: a salesperson gets the own row only.
        """
        self.check_access_rights("read")
        month = self._parse_board_month(month)
        previous = (month - timedelta(days=1)).replace(day=1)
        Report = self.env["buz.sales.dashboard.report"]
        Report._flush_sources()
        allowed = self._editable_owners()
        sees_all = allowed is None or Report._sees_everything()
        company = [("company_id", "in", self.env.companies.ids)]

        targets = {}
        for target in self.search(company + [("month", "in", [previous, month])]):
            owner = target.user_id if target.level == "user" else target.team_id
            targets[target.month, target.level, owner.id] = target.amount

        sales = {"user": {}, "team": {}}
        sellers = self.env["res.users"]
        for key, user, team, amount in Report._read_group(
                company + [("date", ">=", fields.Date.to_string(previous)),
                           ("date", "<", fields.Date.to_string(
                               (month + timedelta(days=32)).replace(day=1)))],
                groupby=["month", "user_id", "team_id"],
                aggregates=["amount_total:sum"]):
            sellers |= user
            if key == previous.strftime("%Y-%m"):
                for level, owner in (("user", user), ("team", team)):
                    sales[level][owner.id] = sales[level].get(owner.id, 0.0) + (amount or 0.0)

        def row(level, record):
            return {
                "key": "%s:%s" % (level, record.id),
                "level": level,
                "id": record.id,
                "name": record.sudo().display_name,
                "editable": allowed is None or record.id in allowed[level],
                "target": targets.get((month, level, record.id), False),
                "previous_target": targets.get((previous, level, record.id), False),
                "previous_actual": sales[level].get(record.id, 0.0),
            }

        def by_name(rows):
            return sorted(rows, key=lambda r: (not r["editable"], r["name"]))

        groups, others = [], []
        if sees_all:
            teams = self.env["crm.team"].search([])
            members = self.env["crm.team.member"].sudo().search(
                [("crm_team_id", "in", teams.ids), ("user_id.active", "=", True)])
            listed = set()
            people = {}
            for member in members.sorted(lambda m: (m.crm_team_id.id, m.id)):
                # one row per person: a second membership is not repeated
                if member.user_id.id not in listed:
                    listed.add(member.user_id.id)
                    people.setdefault(member.crm_team_id.id, []).append(
                        row("user", member.user_id))
            for team in teams:
                group = row("team", team)
                group["members"] = by_name(people.get(team.id, []))
                groups.append(group)
            # leaders see their editable teams first
            groups.sort(key=lambda g: (
                not (g["editable"] or any(m["editable"] for m in g["members"])),
                g["name"]))
            with_target = {key[2] for key in targets if key[1] == "user"}
            extra = (sellers.sudo() | self.env["res.users"].sudo().browse(
                sorted(with_target))).filtered(
                    lambda u: u.active and u.id not in listed)
            others = by_name([row("user", user) for user in extra])
        else:
            others = [row("user", self.env.user)]
        return {
            "month": fields.Date.to_string(month),
            "previous_month": fields.Date.to_string(previous),
            "can_edit": allowed is None or bool(allowed["team"] or allowed["user"]),
            "teams": groups,
            "others": others,
        }

    @api.model
    def _parse_board_month(self, month):
        try:
            value = fields.Date.to_date(month)
        except (TypeError, ValueError):
            value = None
        if not value or not 2000 <= value.year <= 2100:
            raise UserError(_("เดือนไม่ถูกต้อง"))
        return value.replace(day=1)

    @api.model
    def save_board(self, month, changes):
        """Save the edited cells of one month, all or nothing.

        ``changes``: [{"level", "id", "amount"}]; an amount of False removes the
        target (not set is not zero).
        """
        month = self._parse_board_month(month)
        if not isinstance(changes, list) or len(changes) > MAX_CHANGES:
            raise UserError(_("ข้อมูลที่ส่งมาไม่ถูกต้อง"))
        allowed = self._editable_owners()
        saved = removed = 0
        for change in changes:
            level = change.get("level") if isinstance(change, dict) else None
            owner = change.get("id") if level else None
            amount = change.get("amount") if level else None
            if level not in ("user", "team") or type(owner) is not int or not (
                    0 < owner < 2 ** 31) or not (
                    amount is False or (type(amount) in (int, float)
                                        and 0 <= amount < MAX_AMOUNT)):
                raise UserError(_("ข้อมูลที่ส่งมาไม่ถูกต้อง"))
            if allowed is not None and owner not in allowed[level]:
                raise AccessError(_("คุณไม่มีสิทธิ์ตั้งเป้ารายการนี้"))
            # removing stays possible for somebody who has since left
            if amount is not False and not self._may_have_target(level, owner):
                raise UserError(_("ไม่พบพนักงานขายหรือทีมขายที่จะตั้งเป้า"))
            field = "%s_id" % level
            target = self.search([
                ("company_id", "=", self.env.company.id), ("month", "=", month),
                (field, "=", owner)])
            if amount is False:
                removed += len(target)
                target.unlink()
            else:
                if target:
                    target.amount = amount
                else:
                    self.create({"month": month, "level": level, field: owner,
                                 "amount": amount})
                saved += 1
        return {"saved": saved, "removed": removed}

    @api.model
    def _may_have_target(self, level, owner):
        """An existing, active sales team or internal user."""
        model = "res.users" if level == "user" else "crm.team"
        record = self.env[model].sudo().browse(owner).exists()
        return bool(record and record.active
                    and not (level == "user" and record.share))

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._first_of_month(vals) for vals in vals_list])

    def write(self, vals):
        result = super().write(self._first_of_month(vals))
        if not self.env.su:
            # Odoo checks the rules on the old values only: a leader must not
            # move a target to somebody else's team or salesperson either
            self.flush_recordset()
            self.check_access_rule("write")
        return result

    @api.constrains("level", "user_id", "team_id")
    def _check_owner(self):
        for target in self:
            if target.level == "user" and (not target.user_id or target.team_id):
                raise ValidationError(_("เป้ารายคนต้องระบุพนักงานขาย และไม่ระบุทีม"))
            if target.level == "team" and (not target.team_id or target.user_id):
                raise ValidationError(_("เป้ารายทีมต้องระบุทีมขาย และไม่ระบุพนักงานขาย"))
