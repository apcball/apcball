# -*- coding: utf-8 -*-
"""เครื่องยนต์คำนวณงบทดลอง — แหล่งความจริงเดียวของทั้งหน้าจอ, PDF และ Excel

หน้าจอ OWL / QWeb PDF / xlsxwriter ต้องเรียก ``get_report_data()`` ตัวนี้เท่านั้น
ห้ามมีเส้นทางคำนวณเส้นที่สอง ไม่งั้นตัวเลขบนจอกับตัวเลขในไฟล์ที่ส่งผู้สอบบัญชี
จะเพี้ยนจากกันโดยไม่มีใครรู้
"""

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.tools import float_is_zero

# 5 หมวดบัญชีไทย เรียงตามลำดับที่ใช้ในงบทดลอง (งบดุล 3 หมวดแรก แล้วจึงงบกำไรขาดทุน)
# key = account.account.internal_group ของ Odoo
THAI_GROUPS = [
    ("asset", "สินทรัพย์", "debit", "bs"),
    ("liability", "หนี้สิน", "credit", "bs"),
    ("equity", "ส่วนของเจ้าของ", "credit", "bs"),
    ("income", "รายได้", "credit", "pl"),
    ("expense", "ค่าใช้จ่าย", "debit", "pl"),
]
GROUP_LABEL = {g[0]: g[1] for g in THAI_GROUPS}
GROUP_NORMAL_SIDE = {g[0]: g[2] for g in THAI_GROUPS}
GROUP_STATEMENT = {g[0]: g[3] for g in THAI_GROUPS}
GROUP_ORDER = [g[0] for g in THAI_GROUPS]
PL_GROUPS = ("income", "expense")
BS_GROUPS = ("asset", "liability", "equity")

# คีย์ของค่าตัวเงินทุกชุดที่แถวหนึ่งถือไว้ ใช้ตอนรวมยอดหมวดและยอดรวมทั้งสิ้น
AMOUNT_KEYS = (
    "opening_debit", "opening_credit",
    "period_debit", "period_credit",
    "closing_debit", "closing_credit",
    "compare_debit", "compare_credit",
)


def _zero_amounts():
    return dict.fromkeys(AMOUNT_KEYS, 0.0)


class TrialBalanceReport(models.AbstractModel):
    _name = "biz.trial.balance.report"
    _description = "Trial Balance Engine (งบทดลอง)"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @api.model
    def get_report_data(self, options=None):
        """คืนข้อมูลงบทดลองทั้งชุดสำหรับ options ที่ให้มา

        :return: dict {options, company, lines, totals, checks, labels}
        """
        if not self.env.user.has_group("account.group_account_readonly"):
            raise AccessError(_("คุณไม่มีสิทธิ์ดูรายงานทางบัญชี"))

        opt = self._normalize_options(options)
        companies = self.env["res.company"].browse(opt["company_ids"])
        company = self.env["res.company"].browse(opt["company_id"])
        currency = company.currency_id

        accounts = self._get_accounts(opt)
        own, unallocated = self._compute_own_amounts(accounts, opt)
        lines, totals = self._build_lines(accounts, own, opt, currency, unallocated)
        checks = self._build_checks(totals, opt, currency, companies)

        return {
            "options": opt,
            "company": {
                "id": company.id,
                "name": company.name,
                # ชื่อที่เอาไปขึ้นหัวรายงาน — งบรวมหลายบริษัทต้องเห็นครบทุกชื่อ
                "names": " + ".join(companies.mapped("name")),
                "count": len(companies),
                "currency_id": currency.id,
                "currency_symbol": currency.symbol,
                "decimal_places": currency.decimal_places,
            },
            "companies": [{"id": c.id, "name": c.name} for c in companies],
            # รายชื่อบริษัทที่ผู้ใช้เลือกได้ — ให้ช่องเลือกบริษัทบนแถบตัวกรองใช้
            # ไม่ต้องให้หน้าจอไปถาม res.company เองอีกรอบ
            "allowed_companies": [
                {"id": c.id, "name": c.name} for c in self.env.user.company_ids
            ],
            "lines": lines,
            "totals": totals,
            "checks": checks,
            "labels": self._build_labels(opt),
        }

    @api.model
    def action_open_journal_items(self, account_id, options=None):
        """Drill-down จากแถวบัญชีไปยังรายการสมุดรายวันที่ประกอบเป็นยอดนั้น

        โหมดงบรวมหนึ่งแถวมาจากบัญชีรหัสเดียวกันของหลายบริษัท จึงรับได้ทั้ง id เดี่ยว
        และลิสต์ของ id
        """
        opt = self._normalize_options(options)
        if isinstance(account_id, (list, tuple)):
            account_ids = [int(a) for a in account_id if a]
        else:
            account_ids = [int(account_id)] if account_id else []
        domain = self._base_domain(opt) + [
            ("account_id", "in", account_ids),
            ("date", ">=", opt["date_from"]),
            ("date", "<=", opt["date_to"]),
        ]
        accounts = self.env["account.account"].browse(account_ids)
        name = accounts[:1].display_name if accounts else _("รายการบัญชี")
        if len(accounts) > 1:
            name = _("%s (รวม %s บริษัท)") % (name, len(accounts))
        return {
            "type": "ir.actions.act_window",
            "name": _("รายการบัญชี %s") % name,
            "res_model": "account.move.line",
            "view_mode": "list,form",
            "views": [(False, "list"), (False, "form")],
            "domain": domain,
            "context": {"search_default_group_by_move": 1, "create": False},
        }

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------
    @api.model
    def _normalize_options(self, options):
        opt = dict(options or {})
        company_ids = self._resolve_company_ids(opt)
        # บริษัท "หลัก" ใช้กำหนดสกุลเงินและปีบัญชีที่ขึ้นหัวรายงาน — เลือกบริษัทปัจจุบัน
        # ถ้าอยู่ในชุดที่เลือก ไม่งั้นใช้ตัวแรก
        main_id = self.env.company.id if self.env.company.id in company_ids else company_ids[0]
        company = self.env["res.company"].browse(main_id)

        today = fields.Date.context_today(self)
        date_from = self._to_date(opt.get("date_from")) or today.replace(day=1)
        date_to = self._to_date(opt.get("date_to")) or (
            date_from + relativedelta(months=1, days=-1)
        )
        if date_to < date_from:
            date_from, date_to = date_to, date_from

        opening_basis = opt.get("opening_basis") or "fiscalyear"
        fy_from, fy_to = self._fiscalyear_dates(company, date_from)

        normalized = {
            "company_id": company.id,
            "company_ids": company_ids,
            "company_mode": opt.get("company_mode") or "consolidated",
            "date_from": fields.Date.to_string(date_from),
            "date_to": fields.Date.to_string(date_to),
            "fy_date_from": fields.Date.to_string(fy_from),
            "fy_date_to": fields.Date.to_string(fy_to),
            "journal_ids": [int(j) for j in (opt.get("journal_ids") or [])],
            "analytic_account_ids": [int(a) for a in (opt.get("analytic_account_ids") or [])],
            "partner_ids": [int(p) for p in (opt.get("partner_ids") or [])],
            "target_move": opt.get("target_move") or "posted",
            "closing_mode": opt.get("closing_mode") or "before",
            "opening_basis": opening_basis,
            "display_account": opt.get("display_account") or "movement",
            "group_by_type": bool(opt.get("group_by_type", True)),
            "compare": opt.get("compare") or "none",
            "date_format": opt.get("date_format") or "be",
        }
        if normalized["target_move"] not in ("posted", "all"):
            normalized["target_move"] = "posted"
        if normalized["display_account"] not in ("all", "movement", "not_zero"):
            normalized["display_account"] = "movement"
        if normalized["compare"] not in ("none", "previous_period", "previous_year"):
            normalized["compare"] = "none"
        if normalized["opening_basis"] not in ("fiscalyear", "inception"):
            normalized["opening_basis"] = "fiscalyear"
        if normalized["closing_mode"] not in ("before", "after"):
            normalized["closing_mode"] = "before"
        if normalized["company_mode"] not in ("consolidated", "split"):
            normalized["company_mode"] = "consolidated"

        cmp_from, cmp_to = self._compare_dates(normalized)
        normalized["compare_date_from"] = fields.Date.to_string(cmp_from) if cmp_from else False
        normalized["compare_date_to"] = fields.Date.to_string(cmp_to) if cmp_to else False
        return normalized

    @api.model
    def _resolve_company_ids(self, opt):
        """บริษัทที่รายงานจะครอบคลุม — ค่าตั้งต้นคือชุดที่เลือกอยู่ใน company switcher

        ตรวจสิทธิ์กับ ``user.company_ids`` (บริษัททั้งหมดที่ผู้ใช้เข้าถึงได้) ไม่ใช่
        ``env.companies`` (ชุดที่ติ๊กอยู่ตอนนี้) — wizard ที่บันทึกตัวกรองไว้ก่อนแล้ว
        ผู้ใช้สลับ switcher จึงยังสั่งพิมพ์ได้ โดยที่บริษัทนอกสิทธิ์ยังถูกปฏิเสธเสมอ
        """
        requested = opt.get("company_ids")
        if not requested:
            single = opt.get("company_id")
            requested = [single] if single else self.env.companies.ids
        requested = [int(c) for c in requested if c]
        if not requested:
            requested = self.env.companies.ids

        allowed = set(self.env.user.company_ids.ids)
        denied = [c for c in requested if c not in allowed]
        if denied:
            names = self.env["res.company"].sudo().browse(denied).mapped("name")
            raise AccessError(
                _("คุณไม่มีสิทธิ์ดูข้อมูลของบริษัท: %s") % ", ".join(names)
            )
        # ลบตัวซ้ำโดยคงลำดับที่ส่งมา
        seen = {}
        for company_id in requested:
            seen.setdefault(company_id, True)
        return list(seen)

    @api.model
    def _fiscalyear_groups(self, opt):
        """จับกลุ่มบริษัทตามวันต้นปีบัญชี — กลุ่มบริษัทไทยมักตรงกันจึงได้กลุ่มเดียว

        :return: {วันต้นปีบัญชี (str): [company_id, ...]}
        """
        date_from = self._to_date(opt["date_from"])
        groups = {}
        for company in self.env["res.company"].browse(opt["company_ids"]):
            fy_from, _fy_to = self._fiscalyear_dates(company, date_from)
            groups.setdefault(fields.Date.to_string(fy_from), []).append(company.id)
        return groups

    @api.model
    def _to_date(self, value):
        if not value:
            return False
        if isinstance(value, str):
            return fields.Date.to_date(value)
        return value

    @api.model
    def _fiscalyear_dates(self, company, date):
        """ต้น/ปลายปีบัญชีที่ครอบวันที่ที่ให้มา

        ใช้เรคคอร์ด account.fiscal.year (จาก om_fiscal_year) ก่อน เพราะกิจการไทย
        หลายรายมีปีบัญชีไม่ตรงปีปฏิทินและตั้งค่าไว้ตรงนั้น ถ้าไม่มีจึงถอยไปใช้
        compute_fiscalyear_dates() ของ core ที่อ่านจาก fiscalyear_last_day/month
        """
        if "account.fiscal.year" in self.env:
            fy = self.env["account.fiscal.year"].sudo().search(
                [
                    ("company_id", "=", company.id),
                    ("date_from", "<=", date),
                    ("date_to", ">=", date),
                ],
                limit=1,
            )
            if fy:
                return fy.date_from, fy.date_to
        dates = company.compute_fiscalyear_dates(date)
        return dates["date_from"], dates["date_to"]

    @api.model
    def _compare_dates(self, opt):
        if opt["compare"] == "none":
            return False, False
        date_from = fields.Date.to_date(opt["date_from"])
        date_to = fields.Date.to_date(opt["date_to"])
        if opt["compare"] == "previous_year":
            return date_from - relativedelta(years=1), date_to - relativedelta(years=1)
        # previous_period: หน้าต่างยาวเท่ากันที่ต่อท้ายกันพอดีก่อนงวดปัจจุบัน
        span = (date_to - date_from).days + 1
        cmp_to = date_from - relativedelta(days=1)
        return cmp_to - relativedelta(days=span - 1), cmp_to

    # ------------------------------------------------------------------
    # Domain / aggregation
    # ------------------------------------------------------------------
    @api.model
    def _base_domain(self, opt):
        """เงื่อนไขที่ใช้ร่วมกันทุกช่วงเวลา (ยังไม่รวมเงื่อนไขวันที่)"""
        domain = [
            ("company_id", "in", opt["company_ids"]),
            ("account_id", "!=", False),
            ("display_type", "not in", ("line_section", "line_note")),
            ("parent_state", "!=", "cancel"),
        ]
        if opt["target_move"] == "posted":
            domain.append(("parent_state", "=", "posted"))
        if opt["journal_ids"]:
            domain.append(("journal_id", "in", opt["journal_ids"]))
        if opt["partner_ids"]:
            domain.append(("partner_id", "in", opt["partner_ids"]))
        if opt["analytic_account_ids"]:
            domain.append(("analytic_distribution", "in", opt["analytic_account_ids"]))
        # "ก่อนปิดบัญชี" = ไม่นับรายการปิดบัญชีสิ้นปี ตรวจฟิลด์แบบ soft เพราะโมดูล
        # biz_year_end_closing เป็นตัวเลือก ไม่ได้ประกาศไว้ใน depends
        if opt["closing_mode"] == "before" and self._has_closing_flag():
            domain.append(("move_id.is_year_end_closing", "=", False))
        return domain

    @api.model
    def _has_closing_flag(self):
        return "is_year_end_closing" in self.env["account.move"]._fields

    @api.model
    def _read_balances(self, domain):
        """{account_id: (debit, credit)} — ผ่าน ORM เพื่อให้ record rule ทำงานตามปกติ"""
        groups = self.env["account.move.line"]._read_group(
            domain, groupby=["account_id"], aggregates=["debit:sum", "credit:sum"]
        )
        return {acc.id: (debit or 0.0, credit or 0.0) for acc, debit, credit in groups}

    @api.model
    def _get_accounts(self, opt):
        return self.env["account.account"].search(
            [("company_id", "in", opt["company_ids"])], order="code"
        )

    @api.model
    def _compute_own_amounts(self, accounts, opt):
        """ยอดของแต่ละบัญชี — งบทดลองแสดงทุกบัญชีเป็นแถวเดี่ยว ไม่มีการโรลอัพ"""
        base = self._base_domain(opt)
        date_from = opt["date_from"]
        date_to = opt["date_to"]
        rounding = self.env["res.company"].browse(opt["company_id"]).currency_id.rounding
        unallocated = 0.0

        # --- ยอดยกมา -------------------------------------------------
        opening = {}
        if opt["opening_basis"] == "inception":
            opening = self._read_balances(base + [("date", "<", date_from)])
        else:
            # บัญชีงบดุลสะสมข้ามปี ส่วนบัญชีรายได้/ค่าใช้จ่ายเริ่มนับใหม่ทุกปีบัญชี
            opening = self._read_balances(
                base
                + [
                    ("date", "<", date_from),
                    ("account_id.internal_group", "in", list(BS_GROUPS)),
                ]
            )
            # แต่ละบริษัทอาจมีปีบัญชีคนละวัน จึงยิงทีละกลุ่มที่ต้นปีบัญชีตรงกัน
            for fy_from, company_ids in self._fiscalyear_groups(opt).items():
                if fy_from >= date_from:
                    continue
                opening.update(
                    self._read_balances(
                        base
                        + [
                            ("company_id", "in", company_ids),
                            ("date", ">=", fy_from),
                            ("date", "<", date_from),
                            ("account_id.internal_group", "in", list(PL_GROUPS)),
                        ]
                    )
                )
            unallocated = self._carry_prior_earnings(base, opt, accounts, opening, rounding)

        # --- เคลื่อนไหวในงวด ----------------------------------------
        period = self._read_balances(
            base + [("date", ">=", date_from), ("date", "<=", date_to)]
        )

        # --- งวดเปรียบเทียบ -----------------------------------------
        compare = {}
        if opt["compare"] != "none":
            compare = self._read_balances(
                base
                + [
                    ("date", ">=", opt["compare_date_from"]),
                    ("date", "<=", opt["compare_date_to"]),
                ]
            )

        result = {}
        for account in accounts:
            vals = _zero_amounts()
            o_dr, o_cr = opening.get(account.id, (0.0, 0.0))
            p_dr, p_cr = period.get(account.id, (0.0, 0.0))
            c_dr, c_cr = compare.get(account.id, (0.0, 0.0))
            # ยอดยกมาและยอดคงเหลือแสดงเป็น "ยอดสุทธิข้างเดียว" ตามหลักงบทดลองไทย
            # ส่วนคอลัมน์เคลื่อนไหวคงเดบิต/เครดิตดิบไว้ เพราะนักบัญชีต้องเห็นทั้งสองขา
            self._set_net(vals, "opening", o_dr - o_cr, rounding)
            vals["period_debit"] = p_dr
            vals["period_credit"] = p_cr
            self._set_net(vals, "closing", (o_dr - o_cr) + (p_dr - p_cr), rounding)
            self._set_net(vals, "compare", c_dr - c_cr, rounding)
            vals["has_move"] = bool(
                not float_is_zero(p_dr, precision_rounding=rounding)
                or not float_is_zero(p_cr, precision_rounding=rounding)
            )
            result[account.id] = vals
        return result, unallocated

    @api.model
    def _carry_prior_earnings(self, base, opt, accounts, opening, rounding):
        """ยกกำไร(ขาดทุน)ของปีบัญชีก่อน ๆ ไปไว้ฝั่งส่วนของเจ้าของ

        เมื่อคิดยอดยกมาแบบ "ต้นปีบัญชี" บัญชีรายได้/ค่าใช้จ่ายเริ่มนับใหม่ทุกปี ผลของ
        ปีก่อน ๆ จึงหายไปข้างเดียว งบทดลองจะไม่ดุลทันทีถ้าไม่ยกไปเข้ากำไรสะสม —
        Odoo Community ไม่สร้างรายการปิดบัญชีให้เอง งบดุลของ core ก็คำนวณส่วนนี้แบบ
        เดียวกัน ถ้าผังบัญชีไม่มีบัญชีกำไรสะสมยังไม่จัดสรร จะคืนยอดออกไปให้
        _build_lines แสดงเป็นบรรทัดเสมือนแทน

        ทำ **ทีละบริษัท** เพราะบัญชีกำไรสะสมยังไม่จัดสรรเป็นของแต่ละบริษัท และปีบัญชี
        ก็อาจไม่ตรงกัน ถ้ารวมยอดข้ามบริษัทแล้วลงบัญชีเดียว งบของบริษัทนั้นจะเพี้ยน

        :return: ยอดที่ยังไม่มีบัญชีรองรับ รวมทุกบริษัท (0.0 ถ้าลงเข้าบัญชีได้หมด)
        """
        unallocated = 0.0
        account_ids = set(accounts.ids)
        date_from = self._to_date(opt["date_from"])
        for company in self.env["res.company"].browse(opt["company_ids"]):
            fy_from, _fy_to = self._fiscalyear_dates(company, date_from)
            prior = self._read_balances(
                base
                + [
                    ("company_id", "=", company.id),
                    ("date", "<", fields.Date.to_string(fy_from)),
                    ("account_id.internal_group", "in", list(PL_GROUPS)),
                ]
            )
            prior_net = sum(debit - credit for debit, credit in prior.values())
            if float_is_zero(prior_net, precision_rounding=rounding):
                continue
            target = self.env["account.account"].search(
                [
                    ("company_id", "=", company.id),
                    ("account_type", "=", "equity_unaffected"),
                ],
                limit=1,
            )
            if target and target.id in account_ids:
                debit, credit = opening.get(target.id, (0.0, 0.0))
                opening[target.id] = (
                    debit + max(prior_net, 0.0),
                    credit + max(-prior_net, 0.0),
                )
            else:
                unallocated += prior_net
        return unallocated

    @api.model
    def _set_net(self, vals, prefix, net, rounding):
        """ลงยอดสุทธิข้างเดียว — งบทดลองไทยไม่แสดงเลขติดลบ"""
        if float_is_zero(net, precision_rounding=rounding):
            vals[prefix + "_debit"] = 0.0
            vals[prefix + "_credit"] = 0.0
        elif net > 0:
            vals[prefix + "_debit"] = net
            vals[prefix + "_credit"] = 0.0
        else:
            vals[prefix + "_debit"] = 0.0
            vals[prefix + "_credit"] = -net

    # ------------------------------------------------------------------
    # Line building
    # ------------------------------------------------------------------
    @api.model
    def _account_rows(self, accounts, own, opt, rounding):
        """ยุบบัญชีให้เป็น "แถวรายงาน" ตามโหมดหลายบริษัทที่เลือก

        * ``consolidated`` — บัญชีรหัสเดียวกันของทุกบริษัทรวมเป็นแถวเดียว ยอดบวกกัน
        * ``split`` — 1 บัญชี 1 แถว พร้อมชื่อบริษัทกำกับ

        คีย์ที่ใช้รวมคือ (หมวดบัญชี, รหัสบัญชี) ไม่ใช่รหัสอย่างเดียว — ถ้าคนละบริษัท
        ใช้รหัสเดียวกันแต่คนละหมวด จะได้แยกแถวแทนที่จะถูกยัดรวมผิดหมวด
        """
        split = opt["company_mode"] == "split"
        rows = {}
        for account in accounts:
            vals = own[account.id]
            if split:
                key = ("split", account.id)
            else:
                key = (account.internal_group, account.code or account.display_name)
            row = rows.get(key)
            if row is None:
                row = rows[key] = {
                    "code": account.code or "",
                    "name": (
                        account.display_name.split(" ", 1)[-1]
                        if account.code
                        else account.display_name
                    ),
                    "group": account.internal_group,
                    "company_name": account.company_id.name if split else "",
                    "account_ids": [],
                    "amounts": _zero_amounts(),
                    "has_move": False,
                }
            row["account_ids"].append(account.id)
            for key_amount in AMOUNT_KEYS:
                row["amounts"][key_amount] += vals[key_amount]
            row["has_move"] = row["has_move"] or vals["has_move"]

        # ยอดของหลายบริษัทที่บวกกันอาจมีทั้งเดบิตและเครดิตปนกัน ต้องยุบกลับเป็นข้างเดียว
        # ตามหลักงบทดลองไทย (คอลัมน์ "เปลี่ยนแปลง" คงสองขาไว้ตามเดิม)
        for row in rows.values():
            if len(row["account_ids"]) > 1:
                for prefix in ("opening", "closing", "compare"):
                    net = row["amounts"][prefix + "_debit"] - row["amounts"][prefix + "_credit"]
                    self._set_net(row["amounts"], prefix, net, rounding)

        return sorted(rows.values(), key=lambda r: (r["code"] or "", r["company_name"]))

    @api.model
    def _build_lines(self, accounts, own, opt, currency, unallocated=0.0):
        """แถวรายงาน = 1 บัญชี 1 แถว (แบน) จัดกลุ่มตามหมวดบัญชีไทยเท่านั้น"""
        rounding = currency.rounding
        rows = self._account_rows(accounts, own, opt, rounding)

        lines = []
        totals = _zero_amounts()
        totals["net_profit"] = 0.0
        pl_net = 0.0

        def keep(row):
            vals = row["amounts"]
            if opt["display_account"] == "all":
                return True
            if opt["display_account"] == "movement":
                return row["has_move"] or not self._is_zero_row(vals, rounding)
            return not self._is_zero_row(vals, rounding)

        def emit(row, level):
            line = self._make_account_line(row, level, opt, rounding)
            # ทุกแถวบัญชีนับเข้ายอดรวมหนึ่งครั้ง — แถวหัวหมวด/รวมหมวดไม่นับ
            line["counts_to_total"] = True
            lines.append(line)

        def accumulate(row):
            for key in AMOUNT_KEYS:
                totals[key] += row["amounts"][key]

        if opt["group_by_type"]:
            for group in GROUP_ORDER:
                members = [r for r in rows if r["group"] == group and keep(r)]
                if not members:
                    continue
                section_start = len(lines)
                lines.append(
                    {
                        "kind": "section",
                        "id": "section_%s" % group,
                        "group": group,
                        "code": "",
                        "name": GROUP_LABEL[group],
                        "company_name": "",
                        "level": 0,
                        "flag": "ok",
                        "counts_to_total": False,
                        **_zero_amounts(),
                    }
                )
                subtotal = _zero_amounts()
                for row in members:
                    emit(row, 1)
                    for key in AMOUNT_KEYS:
                        subtotal[key] += row["amounts"][key]
                    accumulate(row)
                if group in PL_GROUPS:
                    pl_net += subtotal["closing_debit"] - subtotal["closing_credit"]
                total_line = {
                    "kind": "section_total",
                    "id": "section_total_%s" % group,
                    "group": group,
                    "code": "",
                    "name": _("รวม%s") % GROUP_LABEL[group],
                    "company_name": "",
                    "level": 0,
                    "flag": "ok",
                    "counts_to_total": False,
                    **subtotal,
                }
                total_line["change_pct"] = self._change_pct(total_line, rounding)
                lines.append(total_line)
                lines[section_start]["statement"] = GROUP_STATEMENT[group]
        else:
            for row in [r for r in rows if keep(r)]:
                emit(row, 0)
                accumulate(row)
                if row["group"] in PL_GROUPS:
                    pl_net += (
                        row["amounts"]["closing_debit"] - row["amounts"]["closing_credit"]
                    )

        if not float_is_zero(unallocated, precision_rounding=rounding):
            lines, totals = self._apply_unallocated_earnings(
                lines, totals, unallocated, rounding
            )

        if opt["closing_mode"] == "after":
            lines, totals, closed = self._apply_virtual_closing(
                lines, totals, pl_net, opt, rounding
            )
            totals["net_profit"] = -closed
        else:
            totals["net_profit"] = -pl_net

        totals["change_pct"] = None
        totals["kind"] = "grand_total"
        totals["name"] = _("รวม")
        return lines, totals

    @api.model
    def _make_account_line(self, row, level, opt, rounding):
        vals = row["amounts"]
        line = {
            "kind": "account",
            # id ใช้เป็น key ของแถวบนหน้าจอ — id ของบัญชีแรกในแถวไม่ซ้ำกับแถวอื่นแน่นอน
            "id": row["account_ids"][0],
            "account_id": row["account_ids"][0],
            "account_ids": row["account_ids"],
            "code": row["code"],
            "name": row["name"],
            "company_name": row["company_name"],
            "level": level,
            "group": row["group"],
            "statement": GROUP_STATEMENT.get(row["group"], "bs"),
        }
        line.update({k: vals[k] for k in AMOUNT_KEYS})
        line["change_pct"] = self._change_pct(vals, rounding)
        line["flag"] = self._flag(row["group"], vals, rounding)
        return line

    @api.model
    def _change_pct(self, vals, rounding):
        """% เปลี่ยนแปลงจากยอดยกมาไปยอดคงเหลือ — คอลัมน์ขวาสุดของงบทดลอง"""
        opening = vals["opening_debit"] - vals["opening_credit"]
        closing = vals["closing_debit"] - vals["closing_credit"]
        if float_is_zero(opening, precision_rounding=rounding):
            # ไม่มียอดยกมาแล้วมียอดคงเหลือ = คิด % ไม่ได้ (หารด้วยศูนย์) คืน None ให้
            # ทุกหน้าออกแสดงเป็นช่องว่าง ดีกว่าโชว์ 100% ซึ่งอ่านแล้วเข้าใจผิด
            return 0.0 if float_is_zero(closing, precision_rounding=rounding) else None
        return (closing - opening) / abs(opening) * 100.0

    @api.model
    def _flag(self, group, vals, rounding):
        """ธงเตือนยอดผิดด้าน — สินทรัพย์/ค่าใช้จ่ายไม่ควรมียอดเครดิต และกลับกัน"""
        side = GROUP_NORMAL_SIDE.get(group)
        if not side:
            return "ok"
        wrong = vals["closing_credit"] if side == "debit" else vals["closing_debit"]
        if float_is_zero(wrong, precision_rounding=rounding):
            return "ok"
        return "abnormal"

    @api.model
    def _is_zero_row(self, vals, rounding):
        return all(
            float_is_zero(vals[key], precision_rounding=rounding) for key in AMOUNT_KEYS
        )

    @api.model
    def _apply_unallocated_earnings(self, lines, totals, net, rounding):
        """บรรทัดเสมือน "กำไร(ขาดทุน)สะสมยกมา" สำหรับผังบัญชีที่ไม่มีบัญชีกำไรสะสม"""
        row = _zero_amounts()
        self._set_net(row, "opening", net, rounding)
        self._set_net(row, "closing", net, rounding)
        for key in ("opening_debit", "opening_credit", "closing_debit", "closing_credit"):
            totals[key] += row[key]

        virtual = {
            "kind": "account",
            "id": "virtual_prior_earnings",
            "account_id": False,
            "code": "",
            "name": _("กำไร(ขาดทุน)สะสมยกมา"),
            "company_name": "",
            "level": 1,
            "group": "equity",
            "statement": "bs",
            "virtual_opening": True,
            "flag": "ok",
            "counts_to_total": True,
            **row,
        }
        virtual["change_pct"] = self._change_pct(virtual, rounding)

        insert_at = len(lines)
        for index, line in enumerate(lines):
            if line["kind"] == "section_total" and line.get("group") == "equity":
                for key in ("opening_debit", "opening_credit", "closing_debit", "closing_credit"):
                    line[key] += row[key]
                line["change_pct"] = self._change_pct(line, rounding)
                insert_at = index
                break
        lines.insert(insert_at, virtual)
        return lines, totals

    @api.model
    def _apply_virtual_closing(self, lines, totals, pl_net, opt, rounding):
        """งบทดลอง "หลังปิดบัญชี" — ยุบยอดรายได้/ค่าใช้จ่ายคงเหลือเข้ากำไรสะสม

        ถ้ามีรายการปิดบัญชีจริงจาก biz_year_end_closing อยู่ในช่วงเวลาแล้ว pl_net
        จะเป็นศูนย์อยู่แล้วและเมธอดนี้จะไม่ทำอะไร — จึงใช้ได้ทั้งสองกรณีโดยไม่ต้องแยก
        """
        if float_is_zero(pl_net, precision_rounding=rounding):
            return lines, totals, 0.0

        for line in lines:
            if line.get("group") in PL_GROUPS and line["kind"] in ("account", "section_total"):
                # หักออกจากยอดรวมเฉพาะแถวบัญชีที่นับเข้ายอดรวมจริง ๆ แถวรวมหมวด
                # ถือยอดชุดเดียวกันซ้ำอยู่ ถ้าหักด้วยจะหักเกินและงบไม่ดุล
                if line.get("counts_to_total"):
                    totals["closing_debit"] -= line["closing_debit"]
                    totals["closing_credit"] -= line["closing_credit"]
                line["closing_debit"] = 0.0
                line["closing_credit"] = 0.0
                line["change_pct"] = self._change_pct(line, rounding)
                line["flag"] = "ok"

        # กำไรสุทธิ (pl_net < 0 คือรายได้มากกว่าค่าใช้จ่าย) เข้าฝั่งเครดิตของทุน
        equity_line = _zero_amounts()
        self._set_net(equity_line, "closing", pl_net, rounding)
        totals["closing_debit"] += equity_line["closing_debit"]
        totals["closing_credit"] += equity_line["closing_credit"]

        virtual = {
            "kind": "account",
            "id": "virtual_closing",
            "account_id": False,
            "code": "",
            "name": _("กำไร(ขาดทุน)สุทธิยกไปกำไรสะสม"),
            "company_name": "",
            "level": 1,
            "group": "equity",
            "statement": "bs",
            "virtual": True,
            "flag": "ok",
            "counts_to_total": True,
            **equity_line,
        }
        virtual["change_pct"] = self._change_pct(virtual, rounding)

        # แทรกไว้ท้ายหมวดส่วนของเจ้าของ แล้วบวกเข้ายอดรวมหมวดนั้นด้วย
        insert_at = len(lines)
        for index, line in enumerate(lines):
            if line["kind"] == "section_total" and line.get("group") == "equity":
                for key in ("closing_debit", "closing_credit"):
                    line[key] += equity_line[key]
                line["change_pct"] = self._change_pct(line, rounding)
                insert_at = index
                break
        lines.insert(insert_at, virtual)
        return lines, totals, pl_net

    # ------------------------------------------------------------------
    # Checks & labels
    # ------------------------------------------------------------------
    @api.model
    def _build_checks(self, totals, opt, currency, companies=None):
        rounding = currency.rounding
        diff = totals["closing_debit"] - totals["closing_credit"]
        if companies is None:
            companies = self.env["res.company"].browse(opt["company_ids"])
        # กลุ่มบริษัทที่ใช้คนละสกุลเงินบวกกันตรง ๆ ไม่ได้ รายงานยังออกให้แต่ต้องเตือน
        other = companies.filtered(lambda c: c.currency_id.id != currency.id)
        checks = {
            "is_balanced": float_is_zero(diff, precision_rounding=rounding),
            "difference": diff,
            "include_draft": opt["target_move"] == "all",
            "unbalanced_moves": self._unbalanced_moves(opt, rounding),
            "closing_flag_available": self._has_closing_flag(),
            "mixed_currency": [
                {"id": c.id, "name": c.name, "currency": c.currency_id.name}
                for c in other
            ],
        }
        return checks

    @api.model
    def _unbalanced_moves(self, opt, rounding):
        """รายการที่เดบิตไม่เท่าเครดิตในตัวมันเอง — ไม่ควรมี แต่ถ้ามีต้องชี้ตัวได้"""
        domain = self._base_domain(opt) + [
            ("date", ">=", opt["date_from"]),
            ("date", "<=", opt["date_to"]),
        ]
        groups = self.env["account.move.line"]._read_group(
            domain,
            groupby=["move_id"],
            aggregates=["balance:sum"],
            having=[("balance:sum", "!=", 0)],
            limit=20,
        )
        return [
            {"id": move.id, "name": move.name, "difference": balance}
            for move, balance in groups
            if not float_is_zero(balance or 0.0, precision_rounding=rounding)
        ]

    @api.model
    def _build_labels(self, opt):
        """ข้อความบรรยายตัวกรอง ใช้ซ้ำได้ทั้งบนจอ, หัว PDF และบล็อกหัวของ Excel"""
        companies = self.env["res.company"].browse(opt["company_ids"])
        return {
            "title": _("งบทดลอง"),
            "companies": ", ".join(companies.mapped("name")),
            "company_mode": (
                ""
                if len(companies) < 2
                else {
                    "consolidated": _("รวมทุกบริษัทเป็นงบเดียว"),
                    "split": _("แยกแถวตามบริษัท"),
                }[opt["company_mode"]]
            ),
            "period": "%s - %s" % (
                self.format_report_date(opt["date_from"], opt["date_format"]),
                self.format_report_date(opt["date_to"], opt["date_format"]),
            ),
            "closing_mode": {
                "before": _("ก่อนปิดบัญชีรายได้-ค่าใช้จ่าย"),
                "after": _("หลังปิดบัญชีรายได้-ค่าใช้จ่าย"),
            }[opt["closing_mode"]],
            "opening_basis": {
                "fiscalyear": _("ยอดยกมาต้นปีบัญชี (%s)")
                % self.format_report_date(opt["fy_date_from"], opt["date_format"]),
                "inception": _("ยอดยกมาสะสมทุกรายการก่อนวันเริ่มงวด"),
            }[opt["opening_basis"]],
            "target_move": {
                "posted": _("เฉพาะรายการที่ผ่านรายการแล้ว"),
                "all": _("รวมรายการที่ยังไม่ผ่านรายการ (Draft)"),
            }[opt["target_move"]],
            "display_account": {
                "all": _("ทุกบัญชี"),
                "movement": _("เฉพาะบัญชีที่มีความเคลื่อนไหว"),
                "not_zero": _("เฉพาะบัญชีที่ยอดไม่เป็นศูนย์"),
            }[opt["display_account"]],
            "compare": {
                "none": "",
                "previous_period": _("เทียบงวดก่อน (%s - %s)")
                % (
                    self.format_report_date(opt["compare_date_from"], opt["date_format"]),
                    self.format_report_date(opt["compare_date_to"], opt["date_format"]),
                ) if opt["compare_date_from"] else "",
                "previous_year": _("เทียบปีก่อน (%s - %s)")
                % (
                    self.format_report_date(opt["compare_date_from"], opt["date_format"]),
                    self.format_report_date(opt["compare_date_to"], opt["date_format"]),
                ) if opt["compare_date_from"] else "",
            }[opt["compare"]],
        }

    @api.model
    def format_report_date(self, value, date_format="be"):
        """dd/mm/yyyy โดย 'be' แปลงปีเป็น พ.ศ. ตามที่งบการเงินไทยใช้"""
        date = self._to_date(value)
        if not date:
            return ""
        year = date.year + 543 if date_format == "be" else date.year
        return "%02d/%02d/%d" % (date.day, date.month, year)
