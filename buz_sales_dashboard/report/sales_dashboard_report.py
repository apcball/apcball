import io
from collections import defaultdict
from datetime import timedelta

import xlsxwriter
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, tools, _
from odoo.exceptions import AccessError

from .report_sql import report_query

# Column order of tables and Excel: by group, the leading figure of each first.
MEASURE_GROUPS = [
    ("sales", [
        ("amount_total", "ยอดขายรวม (SO+POS)"),
        ("amount_total_vat", "ยอดขายรวม รวม VAT"),
        ("amount_so", "SO ยืนยันแล้ว (สุทธิ)"),
        ("amount_delivered", "ส่งแล้ว"),
        ("amount_service", "บริการ"),
        ("amount_adjust", "คืน/ปรับลด"),
        ("amount_so_credit", "ใบลดหนี้ SO"),
        ("amount_quotation", "ใบเสนอราคา"),
    ]),
    ("wait", [
        ("amount_pending", "รอส่ง"),
        ("amount_pending_open", "รอส่ง: มีใบส่งค้าง"),
        ("amount_pending_billed", "รอส่ง: ออกบิลครบ"),
        ("amount_pending_other", "รอส่ง: อื่นๆ"),
    ]),
    ("pos", [
        ("amount_pos", "POS สุทธิ"),
        ("amount_pos_invoice", "POS ใบแจ้งหนี้"),
        ("amount_pos_refund", "POS ใบลดหนี้"),
    ]),
    ("invoice", [
        ("amount_invoiced", "ออกบิลรวม (รวม POS)"),
        ("amount_inv_so", "ออกบิลจาก SO: สุทธิ"),
        ("amount_inv_so_invoice", "ออกบิลจาก SO: ใบแจ้งหนี้"),
        ("amount_inv_so_refund", "ออกบิลจาก SO: ใบลดหนี้"),
        ("amount_inv_other", "บิลไม่ผูก SO: สุทธิ"),
    ]),
]
MEASURES = [measure for _key, measures in MEASURE_GROUPS for measure in measures]
GROUP_OF = {name: key for key, measures in MEASURE_GROUPS for name, _label in measures}
GROUP_COLORS = {"sales": "#1F4E78", "wait": "#B45F06", "pos": "#5B45A8", "invoice": "#04795F"}
# The invoicing group is a separate view of the same business by invoice date:
# never added to the sales columns.
INVOICE_NOTE = ("กลุ่มออกบิล: นับตามวันที่ พนักงานขาย และทีมของใบแจ้งหนี้ "
                "(ตรงกับรายงาน Invoice Analysis) ไม่บวกในยอดขายรวม")
# rows that adjust or bill a sale, not documents of their own
NOT_COUNTED = ("so_credit", "bill_invoice", "bill_refund")
SOURCES = [("so", "Sale Order"), ("pos", "POS")]
STATES = [
    ("quotation", "ใบเสนอราคา"),
    ("sale", "ยืนยันแล้ว"),
    ("invoice", "POS ใบแจ้งหนี้"),
    ("refund", "POS ใบลดหนี้"),
    ("so_credit", "ใบลดหนี้ SO"),
    ("bill_invoice", "ใบแจ้งหนี้"),
    ("bill_refund", "ใบลดหนี้"),
]
DATE_PRESETS = [
    ("this_week", "สัปดาห์นี้"),
    ("this_month", "เดือนนี้"),
    ("last_month", "เดือนก่อน"),
    ("this_quarter", "ไตรมาสนี้"),
    ("last_3_months", "3 เดือนล่าสุด"),
    ("last_6_months", "6 เดือนล่าสุด"),
    ("this_year", "ปีนี้"),
    ("last_year", "ปีก่อน"),
    ("custom", "กำหนดเอง"),
]
UNSPECIFIED = "(ไม่ระบุ)"


class SalesDashboardReport(models.Model):
    _name = "buz.sales.dashboard.report"
    _inherit = "buz.sales.dashboard.viewer"
    _description = "Sales Dashboard Document"
    _auto = False
    _order = "date desc, id desc"

    name = fields.Char("เลขที่", readonly=True)
    source = fields.Selection(SOURCES, "แหล่ง", readonly=True)
    state = fields.Selection(STATES, "สถานะ", readonly=True)
    date = fields.Date("วันที่", readonly=True)
    month = fields.Char("เดือน", readonly=True)
    week = fields.Char("สัปดาห์", readonly=True)
    user_id = fields.Many2one("res.users", "พนักงานขาย", readonly=True)
    team_id = fields.Many2one("crm.team", "ทีมขาย", readonly=True)
    company_id = fields.Many2one("res.company", "บริษัท", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    order_id = fields.Many2one("sale.order", "Sale Order", readonly=True)
    move_id = fields.Many2one("account.move", "ใบแจ้งหนี้", readonly=True)
    amount_quotation = fields.Monetary("ใบเสนอราคา", readonly=True)
    amount_so = fields.Monetary("SO ยืนยันแล้ว (สุทธิ)", readonly=True)
    amount_delivered = fields.Monetary("ส่งแล้ว", readonly=True)
    amount_pending = fields.Monetary("รอส่ง", readonly=True)
    amount_pending_open = fields.Monetary("รอส่ง: มีใบส่งค้าง", readonly=True)
    amount_pending_billed = fields.Monetary("รอส่ง: ออกบิลครบ", readonly=True)
    amount_pending_other = fields.Monetary("รอส่ง: อื่นๆ", readonly=True)
    amount_service = fields.Monetary("บริการ", readonly=True)
    amount_adjust = fields.Monetary("คืน/ปรับลด", readonly=True)
    amount_so_credit = fields.Monetary("ใบลดหนี้ SO", readonly=True)
    amount_pos_invoice = fields.Monetary("POS ใบแจ้งหนี้", readonly=True)
    amount_pos_refund = fields.Monetary("POS ใบลดหนี้", readonly=True)
    amount_pos = fields.Monetary("POS สุทธิ", readonly=True)
    amount_total = fields.Monetary("ยอดขายรวม (SO+POS)", readonly=True)
    amount_total_vat = fields.Monetary("ยอดขายรวม รวม VAT", readonly=True)
    amount_inv_so_invoice = fields.Monetary(
        "ออกบิลจาก SO: ใบแจ้งหนี้", readonly=True)
    amount_inv_so_refund = fields.Monetary(
        "ออกบิลจาก SO: ใบลดหนี้", readonly=True)
    amount_inv_so = fields.Monetary("ออกบิลจาก SO: สุทธิ", readonly=True)
    amount_inv_other = fields.Monetary("บิลไม่ผูก SO: สุทธิ", readonly=True)
    amount_invoiced = fields.Monetary("ออกบิลรวม (รวม POS)", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            "CREATE VIEW %s AS (%s)" % (self._table, report_query()))

    @api.model
    def _flush_sources(self):
        """The view reads these tables behind the ORM's back."""
        self.env.flush_all()

    # ------------------------------------------------------------ filters
    @api.model
    def _sanitize_filters(self, filters):
        filters = filters if isinstance(filters, dict) else {}

        def ids(key):
            values = filters.get(key)
            if not isinstance(values, list):
                return []
            return sorted({v for v in values if type(v) is int and v >= 0})

        def day(key):
            try:
                value = fields.Date.to_date(filters.get(key) or False)
            except (TypeError, ValueError):
                return False
            return fields.Date.to_string(value) if value else False

        preset = filters.get("date_preset")
        if preset not in dict(DATE_PRESETS):
            preset = "this_month"
        sources = filters.get("sources")
        sources = [s for s, _label in SOURCES
                   if isinstance(sources, list) and s in sources]
        return {
            "date_preset": preset,
            "date_from": day("date_from"),
            "date_to": day("date_to"),
            # False: weeks for a single month, months for a longer range
            "granularity": filters.get("granularity")
            if filters.get("granularity") in ("week", "month") else False,
            "user_ids": ids("user_ids"),
            "team_ids": ids("team_ids"),
            # nothing ticked means no restriction
            "sources": sources or [s for s, _label in SOURCES],
        }

    @api.model
    def _resolve_dates(self, filters):
        """Return (date_from, date_to) of a sanitized filter set.

        Presets are relative to today, so a saved "this month" keeps rolling.
        They cover the whole period, like the date filter of the analysis view,
        so that both pages add up the same documents.
        """
        today = fields.Date.context_today(self)
        preset = filters["date_preset"]
        if preset == "custom":
            # never open-ended on both sides: that would read every year
            date_to = fields.Date.to_date(filters["date_to"]) or today
            date_from = (fields.Date.to_date(filters["date_from"])
                         or date_to.replace(month=1, day=1))
            return min(date_from, date_to), max(date_from, date_to)
        month_start = today.replace(day=1)
        one_day = timedelta(days=1)
        if preset == "this_week":
            monday = today - timedelta(days=today.weekday())
            return monday, monday + timedelta(days=6)
        if preset == "this_month":
            return month_start, month_start + relativedelta(months=1) - one_day
        if preset == "last_month":
            return month_start - relativedelta(months=1), month_start - one_day
        if preset in ("last_3_months", "last_6_months"):
            # the current month and the ones before it
            months = 3 if preset == "last_3_months" else 6
            return (month_start - relativedelta(months=months - 1),
                    month_start + relativedelta(months=1) - one_day)
        if preset == "this_quarter":
            start = today.replace(month=(today.month - 1) // 3 * 3 + 1, day=1)
            return start, start + relativedelta(months=3) - one_day
        year_start = today.replace(month=1, day=1)
        if preset == "last_year":
            return year_start - relativedelta(years=1), year_start - one_day
        return year_start, year_start + relativedelta(years=1) - one_day

    @api.model
    def _filter_domain(self, filters):
        date_from, date_to = self._resolve_dates(filters)
        domain = [("company_id", "in", self.env.companies.ids),
                  ("source", "in", filters["sources"])]
        domain += [("date", ">=", fields.Date.to_string(date_from)),
                   ("date", "<=", fields.Date.to_string(date_to))]
        for key, field in (("user_ids", "user_id"), ("team_ids", "team_id")):
            selected = filters[key]
            if not selected:
                continue
            real = [i for i in selected if i]
            leaf = [(field, "in", real)]
            if 0 in selected:  # 0 stands for "not set"
                leaf = (["|", (field, "=", False)] + leaf) if real else [
                    (field, "=", False)]
            domain += leaf
        return domain

    # ------------------------------------------------------------ dashboard
    @api.model
    def get_dashboard_options(self):
        """Choices of the filter bar, limited to what the user may see."""
        self.check_access_rights("read")
        self._flush_sources()
        users, teams = {}, {}
        domain = [("company_id", "in", self.env.companies.ids)]
        for user, team in self._read_group(domain, ["user_id", "team_id"]):
            users[user.id or 0] = user.sudo().display_name if user else UNSPECIFIED
            teams[team.id or 0] = team.sudo().display_name if team else UNSPECIFIED

        def choices(values):
            return [{"id": key, "name": name} for key, name in sorted(
                values.items(), key=lambda kv: (kv[0] == 0, kv[1]))]

        saved = self.env["buz.sales.dashboard.filter"].search(
            [("user_id", "=", self.env.uid)])
        return {
            "users": choices(users),
            "teams": choices(teams),
            "presets": [{"id": k, "name": v} for k, v in DATE_PRESETS],
            "sources": [{"id": k, "name": v} for k, v in SOURCES],
            "measures": [{"id": k, "name": v, "group": GROUP_OF[k]} for k, v in MEASURES],
            "can_set_targets": self._can_set_targets(),
            "invoice_note": INVOICE_NOTE,
            "saved_filters": [{
                "id": f.id, "name": f.name, "is_default": f.is_default,
                "filters": self._sanitize_filters(f.filters),
            } for f in saved],
            "default_filters": self._sanitize_filters({}),
        }

    @api.model
    def _summaries(self, filters):
        """Totals and breakdowns of a sanitized filter set, from one query.

        Record rules apply, so every user only adds up what they may read.
        """
        self.check_access_rights("read")
        self._flush_sources()
        names = [name for name, _label in MEASURES]
        groups = self._read_group(
            self._filter_domain(filters),
            groupby=["month", "week", "user_id", "team_id", "state"],
            aggregates=["__count"] + ["%s:sum" % name for name in names],
        )

        def empty():
            return dict.fromkeys(names, 0.0) | {"count": 0}

        total = empty()
        tables = {key: defaultdict(empty) for key in ("month", "week", "user", "team")}
        labels = {"user": {}, "team": {}}
        for month, week, user, team, state, count, *amounts in groups:
            if state in NOT_COUNTED:
                count = 0
            keys = {"month": month, "week": week,
                    "user": user.id or 0, "team": team.id or 0}
            labels["user"][keys["user"]] = (
                user.sudo().display_name if user else UNSPECIFIED)
            labels["team"][keys["team"]] = (
                team.sudo().display_name if team else UNSPECIFIED)
            for row in [total] + [tables[dim][key] for dim, key in keys.items()]:
                row["count"] += count
                for name, amount in zip(names, amounts):
                    row[name] += amount or 0.0

        result = {"total": total}
        for dim in ("month", "week"):
            result[dim] = [dict(values, key=key, label=key)
                           for key, values in sorted(tables[dim].items())]
        for dim in ("user", "team"):
            result[dim] = sorted(
                (dict(values, key=key, label=labels[dim][key])
                 for key, values in tables[dim].items()),
                key=lambda r: (-r["amount_total"], -r["amount_quotation"], r["label"]))
        return result

    @api.model
    def get_dashboard_data(self, filters):
        filters = self._sanitize_filters(filters)
        date_from, date_to = self._resolve_dates(filters)
        data = self._summaries(filters)
        single_month = (date_from.year, date_from.month) == (date_to.year, date_to.month)
        data.update(
            granularity=filters["granularity"] or ("week" if single_month else "month"),
            target=self._target_progress(filters),
            members=self._member_progress(filters),
            filters=filters,
            domain=self._filter_domain(filters),
            date_from=fields.Date.to_string(date_from),
            date_to=fields.Date.to_string(date_to),
        )
        return data

    # ------------------------------------------------------------ targets
    @api.model
    def _sees_everything(self):
        return (self.env.user.has_group("buz_sales_dashboard.group_all")
                or self._leads_sales_team())

    @api.model
    def _can_set_targets(self):
        allowed = self.env["buz.sales.target"]._editable_owners()
        return allowed is None or bool(allowed["team"] or allowed["user"])

    @api.model
    def _filter_months(self, filters):
        date_from, date_to = self._resolve_dates(filters)
        months, month = [], date_from.replace(day=1)
        while month <= date_to:
            months.append(month)
            month += relativedelta(months=1)
        return date_from, date_to, months

    @api.model
    def _pace(self, months):
        """(share of the months' days already over in %, days left or False)."""
        today = fields.Date.context_today(self)
        end = months[-1] + relativedelta(months=1)
        days = (end - months[0]).days
        passed = min(max((today - months[0]).days, 0), days)
        if today >= end:
            days_left = 0
        elif months == [today.replace(day=1)]:
            days_left = (end - today).days  # calendar days, today included
        else:
            days_left = False
        return passed / days * 100, days_left

    @api.model
    def _target_status(self, percent, pace):
        if percent is False:
            return "set"
        if percent >= 100:
            return "done"
        if pace >= 100:
            return "missed"
        return "behind" if percent < pace else "ahead"

    @api.model
    def _member_progress(self, filters):
        """Each member of the chosen (or led) teams against the personal target.

        Only for who sees everything, and only without a salesperson filter.
        A person's sales count in every team, as on that person's own page.
        """
        if filters["user_ids"] or not self._sees_everything():
            return False
        Team = self.env["crm.team"].sudo()
        chosen = [i for i in filters["team_ids"] if i]
        teams = Team.browse(chosen).exists() if chosen else (
            Team if filters["team_ids"] else Team.search([("user_id", "=", self.env.uid)]))
        if not teams:
            return False
        date_from, date_to, months = self._filter_months(filters)
        company = [("company_id", "in", self.env.companies.ids)]
        period = company + [("date", ">=", fields.Date.to_string(date_from)),
                            ("date", "<=", fields.Date.to_string(date_to))]
        users = self.env["crm.team.member"].sudo().search(
            [("crm_team_id", "in", teams.ids)]).user_id
        unassigned = False
        for user, amount in self._read_group(
                period + [("team_id", "in", teams.ids)],
                groupby=["user_id"], aggregates=["amount_total:sum"]):
            if user:
                users |= user.sudo()
            elif amount:
                unassigned = amount
        sales = defaultdict(float)
        for month, user, amount in self._read_group(
                period + [("user_id", "in", users.ids)],
                groupby=["month", "user_id"], aggregates=["amount_total:sum"]):
            sales[month, user.id] += amount or 0.0
        Target = self.env["buz.sales.target"]
        by_month = company + [("month", "in", months)]
        targets = defaultdict(dict)
        for target in Target.search(
                by_month + [("level", "=", "user"), ("user_id", "in", users.ids)]):
            targets[target.user_id.id][target.month.strftime("%Y-%m")] = target.amount
        pace, days_left = self._pace(months)
        rows = []
        for user in users.sudo():
            own = targets.get(user.id)
            if own:
                # as on the card: a month without a target stays out
                target = sum(own.values())
                actual = sum(sales[month, user.id] for month in own)
                percent = actual / target * 100 if target else False
                remaining = max(target - actual, 0.0)
                rows.append({
                    "id": user.id, "name": user.display_name, "target": target,
                    "actual": actual, "percent": percent, "remaining": remaining,
                    "over": max(actual - target, 0.0),
                    "per_day": remaining / days_left if days_left else False,
                    "status": self._target_status(percent, pace),
                })
            else:
                rows.append({
                    "id": user.id, "name": user.display_name, "target": False,
                    "actual": sum(v for (_m, uid), v in sales.items() if uid == user.id),
                    "status": "none",
                })
        rows.sort(key=lambda r: (
            r["target"] is False, -(r.get("percent") or 0), -r["actual"], r["name"]))
        without = sum(1 for r in rows if r["target"] is False)
        if unassigned:
            rows.append({"id": 0, "name": UNSPECIFIED, "target": False,
                         "actual": unassigned, "status": "none"})
        team_targets = Target.search(
            by_month + [("level", "=", "team"), ("team_id", "in", teams.ids)])
        return {
            "teams": ", ".join(teams.mapped("display_name")),
            "rows": rows,
            "pace": pace,
            "without_target": without,
            "team_target": sum(team_targets.mapped("amount")) if team_targets else False,
            "member_target": sum(r["target"] for r in rows if r["target"] is not False),
        }

    @api.model
    def _target_progress(self, filters):
        """Sales against target for a sanitized filter set.

        The target and the sales it is compared with always cover the same
        salespeople or teams and the same months: a month without a target adds
        nothing to either side. Sales are SO + POS (amount_total) whatever the
        source filter says.
        """
        user = self.env.user
        date_from, date_to, months = self._filter_months(filters)
        see_all = self._sees_everything()
        notes = []

        if filters["user_ids"]:
            level, ids = "user", [i for i in filters["user_ids"] if i]
            scope = _("พนักงานขายที่เลือก")
            if filters["team_ids"]:
                notes.append(_("คิดตามพนักงานขายที่เลือก ไม่ใช้ตัวกรองทีม"))
        elif filters["team_ids"]:
            level, ids = "team", [i for i in filters["team_ids"] if i]
            scope = _("ทีมที่เลือก")
        elif see_all:
            level, ids = "team", None
            scope = _("ทุกทีมที่ตั้งเป้า")
        else:
            level, ids = "user", [user.id]
            scope = _("ของฉัน")
        field = "%s_id" % level

        domain = [("company_id", "in", self.env.companies.ids),
                  ("level", "=", level), ("month", "in", months)]
        if ids is not None:
            domain.append((field, "in", ids))
        targets = self.env["buz.sales.target"].search(domain)
        result = {
            "level": level, "scope": scope, "status": "ok" if targets else "none",
            "period": ", ".join(m.strftime("%m/%Y") for m in months)
            if len(months) <= 3 else "%s - %s" % (
                months[0].strftime("%m/%Y"), months[-1].strftime("%m/%Y")),
            "notes": notes,
            # sales of the scope even without a target, for the empty card
            "actual": False,
        }
        if ids is not None:
            entities = self.env[
                "res.users" if level == "user" else "crm.team"
            ].sudo().with_context(active_test=False).browse(ids).exists()
            if len(entities) == 1 and ids != [user.id]:
                result["scope"] = entities.display_name
        if not targets:
            notes.append(_("ยังไม่ได้ตั้งเป้า หรือคุณไม่มีสิทธิ์เห็นเป้านี้"))
            domain = [("company_id", "in", self.env.companies.ids),
                      ("date", ">=", fields.Date.to_string(date_from)),
                      ("date", "<=", fields.Date.to_string(date_to))]
            if ids is not None:
                domain.append((field, "in", ids))
            [(amount,)] = self._read_group(domain, aggregates=["amount_total:sum"])
            result["actual"] = amount or 0.0
            return result

        pairs = {(t.month.strftime("%Y-%m"), t[field].id) for t in targets}
        if ids is None:
            notes.append(_("ทำได้ นับเฉพาะทีมและเดือนที่ตั้งเป้าไว้"))
        else:
            missing = len(months) * len(ids) - len(pairs)
            if missing:
                notes.append(_(
                    "ไม่มีเป้า %s รายการ (%s x เดือน) ยอดส่วนนั้นไม่นำมาคิด",
                    missing, _("พนักงานขาย") if level == "user" else _("ทีม")))
        entity_ids = list({entity for _month, entity in pairs})
        actual = 0.0
        for key, entity, amount in self._read_group(
                [("company_id", "in", self.env.companies.ids),
                 ("date", ">=", fields.Date.to_string(date_from)),
                 ("date", "<=", fields.Date.to_string(date_to)),
                 (field, "in", entity_ids)],
                groupby=["month", field], aggregates=["amount_total:sum"]):
            if (key, entity.id) in pairs:
                actual += amount or 0.0

        target = sum(targets.mapped("amount"))
        last_day = months[-1] + relativedelta(months=1) - timedelta(days=1)
        if date_from != months[0] or date_to != last_day:
            notes.append(_("ช่วงที่เลือกไม่เต็มเดือน ใช้เป้าเต็มเดือน"))
        if not see_all and not (level == "user" and entity_ids == [user.id]):
            notes.append(_("ทำได้ รวมเฉพาะเอกสารที่คุณมีสิทธิ์เห็น"))
        percent = actual / target * 100 if target else False
        remaining = max(target - actual, 0.0)
        pace, days_left = self._pace(months)
        if days_left and not (date_from == months[0] and date_to == last_day):
            days_left = False
        result.update(
            target=target,
            actual=actual,
            remaining=remaining,
            over=max(actual - target, 0.0),
            percent=percent,
            pace=pace,
            state=self._target_status(percent, pace),
            days_left=days_left,
            per_day=remaining / days_left if days_left else False,
        )
        return result

    def action_open_document(self):
        self.ensure_one()
        # credit note and invoice rows open the account move, not an order
        record = (self.move_id if self.state in NOT_COUNTED
                  else self.order_id or self.move_id)
        # The dashboard also shows a team leader the team's figures, while the
        # standard rules may keep the document itself closed to them.
        try:
            record.check_access_rights("read")
            record.check_access_rule("read")
        except AccessError:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "warning",
                    "message": _(
                        "คุณเห็นยอดของเอกสาร %s ได้ แต่ไม่มีสิทธิ์เปิดตัวเอกสาร",
                        self.name),
                },
            }
        return {
            "type": "ir.actions.act_window",
            "res_model": record._name,
            "res_id": record.id,
            "views": [[False, "form"]],
            "target": "current",
        }

    # ------------------------------------------------------------ export
    @api.model
    def _export_xlsx(self, filters):
        """The Excel file of a filter set: summaries and one row per document."""
        filters = self._sanitize_filters(filters)
        summaries = self._summaries(filters)
        documents = self.search_read(
            self._filter_domain(filters),
            ["source", "name", "date", "month", "week", "user_id", "team_id",
             "state"] + [name for name, _label in MEASURES],
            order="date, name, id")

        output = io.BytesIO()
        # strings_to_formulas off: a name starting with "=" stays text
        book = xlsxwriter.Workbook(output, {
            "in_memory": True, "strings_to_formulas": False,
            "strings_to_urls": False})
        header = book.add_format({
            "bold": True, "bg_color": "#1F4E78", "font_color": "white",
            "border": 1, "text_wrap": True, "valign": "vcenter"})
        number = book.add_format({"num_format": "#,##0.00;[Red]-#,##0.00"})
        total_number = book.add_format({
            "num_format": "#,##0.00;[Red]-#,##0.00", "bold": True, "top": 1})
        bold = book.add_format({"bold": True, "top": 1})
        date_format = book.add_format({"num_format": "dd/mm/yyyy"})
        measure_labels = [label for _name, label in MEASURES]
        group_header = {key: book.add_format({
            "bold": True, "bg_color": color, "font_color": "white",
            "border": 1, "text_wrap": True, "valign": "vcenter"})
            for key, color in GROUP_COLORS.items()}

        def write_measure_headers(sheet, first_column):
            for offset, (name, label) in enumerate(MEASURES):
                sheet.write_string(
                    0, first_column + offset, label, group_header[GROUP_OF[name]])

        for title, dim, label in (
                ("รายเดือน", "month", "เดือน"),
                ("รายสัปดาห์", "week", "สัปดาห์ (จ.-อา.)"),
                ("พนักงานขาย", "user", "พนักงานขาย"),
                ("ทีมขาย", "team", "ทีมขาย")):
            sheet = book.add_worksheet(title)
            sheet.write_row(0, 0, [label, "จำนวนเอกสาร"], header)
            write_measure_headers(sheet, 2)
            sheet.set_row(0, 30)
            sheet.set_column(0, 0, 34)
            sheet.set_column(1, len(MEASURES) + 1, 17)
            sheet.freeze_panes(1, 1)
            rows = summaries[dim]
            for index, row in enumerate(rows, start=1):
                sheet.write_string(index, 0, row["label"])
                sheet.write_number(index, 1, row["count"])
                for column, (name, _label) in enumerate(MEASURES, start=2):
                    sheet.write_number(index, column, round(row[name], 2), number)
            last = len(rows) + 1
            sheet.write_string(last, 0, "รวม", bold)
            sheet.write_number(last, 1, summaries["total"]["count"], bold)
            for column, (name, _label) in enumerate(MEASURES, start=2):
                sheet.write_number(
                    last, column, round(summaries["total"][name], 2), total_number)

        sheet = book.add_worksheet("ข้อมูลรายใบ")
        columns = ["แหล่ง", "เลขที่", "วันที่", "เดือน", "สัปดาห์",
                   "พนักงานขาย", "ทีมขาย", "สถานะ"] + measure_labels
        sheet.write_row(0, 0, columns[:8], header)
        write_measure_headers(sheet, 8)
        sheet.set_row(0, 30)
        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 3, 15)
        sheet.set_column(4, 7, 24)
        sheet.set_column(8, len(columns) - 1, 17)
        sheet.freeze_panes(1, 2)
        sources, states = dict(SOURCES), dict(STATES)
        for index, doc in enumerate(documents, start=1):
            for column, text in ((0, sources[doc["source"]]), (1, doc["name"]),
                                 (3, doc["month"]), (4, doc["week"]),
                                 (5, doc["user_id"] and doc["user_id"][1]),
                                 (6, doc["team_id"] and doc["team_id"][1]),
                                 (7, states[doc["state"]])):
                sheet.write_string(index, column, text or (
                    UNSPECIFIED if column in (5, 6) else ""))
            if doc["date"]:
                sheet.write_datetime(index, 2, doc["date"], date_format)
            for column, (name, _label) in enumerate(MEASURES, start=8):
                sheet.write_number(index, column, round(doc[name], 2), number)
        sheet.autofilter(0, 0, max(len(documents), 1), len(columns) - 1)

        date_from, date_to = self._resolve_dates(filters)
        sheet = book.add_worksheet("เงื่อนไข")
        sheet.set_column(0, 0, 22)
        sheet.set_column(1, 1, 90)

        def selected(key, model):
            if not filters[key]:
                return "ทั้งหมด"
            records = self.env[model].sudo().with_context(active_test=False).browse(
                [i for i in filters[key] if i]).exists()
            return ", ".join(records.mapped("display_name")
                             + ([UNSPECIFIED] if 0 in filters[key] else []))

        for index, (key, value) in enumerate((
                ("ช่วงวันที่", "%s - %s" % (
                    date_from.strftime("%d/%m/%Y"),
                    date_to.strftime("%d/%m/%Y"))),
                ("แหล่ง", ", ".join(sources[s] for s in filters["sources"])),
                ("พนักงานขาย", selected("user_ids", "res.users")),
                ("ทีมขาย", selected("team_ids", "crm.team")),
                ("ผู้ส่งออก", self.env.user.display_name),
                ("หน่วย", _("บาท ก่อน VAT ยกเว้นคอลัมน์ 'ยอดขายรวม รวม VAT'")),
                ("ยอดออกบิล", INVOICE_NOTE),
        )):
            sheet.write_string(index, 0, key)
            sheet.write_string(index, 1, value)
        progress = self._target_progress(filters)
        first = 8
        sheet.write_string(first, 0, "เป้ายอดขาย (SO+POS)")
        sheet.write_string(first, 1, "%s · %s" % (progress["scope"], progress["period"]))
        if progress["status"] == "none":
            sheet.write_string(first + 1, 0, "เป้า")
            sheet.write_string(first + 1, 1, "ยังไม่ตั้งเป้า")
            first += 2
        else:
            for label, key in (("เป้า", "target"), ("ทำได้", "actual"),
                               ("คงเหลือต้องทำ", "remaining"), ("เกินเป้า", "over")):
                first += 1
                sheet.write_string(first, 0, label)
                sheet.write_number(first, 1, round(progress[key], 2), number)
            first += 1
        for offset, note in enumerate(progress["notes"]):
            sheet.write_string(first + offset, 0, "หมายเหตุ")
            sheet.write_string(first + offset, 1, note)
        book.close()
        return output.getvalue()
