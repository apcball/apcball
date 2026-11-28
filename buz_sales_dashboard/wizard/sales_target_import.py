import base64
import io
import re
from datetime import date

import openpyxl
import xlsxwriter

from odoo import api, fields, models, _
from odoo.exceptions import UserError

COLUMNS = ["เดือน", "ระดับ", "พนักงานขาย", "ทีมขาย", "เป้ายอดขาย"]
LEVELS = {"คน": "user", "รายคน": "user", "user": "user",
          "ทีม": "team", "รายทีม": "team", "team": "team"}
MAX_ROWS = 5000
MAX_ERRORS = 100
MAX_BYTES = 5 * 1024 * 1024


class SalesTargetImport(models.TransientModel):
    _name = "buz.sales.target.import"
    _description = "Import Sales Targets from Excel"

    @api.model
    def _check_may_set_targets(self):
        allowed = self.env["buz.sales.target"]._editable_owners()
        if allowed is not None and not (allowed["team"] or allowed["user"]):
            raise UserError(_(
                "คุณไม่มีสิทธิ์ตั้งเป้า (เฉพาะหัวหน้าทีมขายและผู้ที่ได้สิทธิ์ตั้งเป้ายอดขาย)"))
        return allowed

    @api.model
    def _template_xlsx(self):
        """An empty form, plus the names that the user may set targets for."""
        allowed = self._check_may_set_targets()
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {
            "in_memory": True, "strings_to_formulas": False,
            "strings_to_urls": False})
        header = book.add_format({"bold": True, "bg_color": "#1F4E78",
                                  "font_color": "white"})
        text = book.add_format({"num_format": "@"})
        sheet = book.add_worksheet("เป้า")
        sheet.write_row(0, 0, COLUMNS, header)
        sheet.set_column(0, 0, 14, text)
        sheet.set_column(1, 1, 10)
        sheet.set_column(2, 3, 34)
        sheet.set_column(4, 4, 18)
        sheet.data_validation(1, 1, MAX_ROWS, 1, {
            "validate": "list", "source": ["คน", "ทีม"]})
        help_sheet = book.add_worksheet("วิธีกรอก")
        help_sheet.set_column(0, 0, 100)
        for row, line in enumerate([
                "เดือน: ปี ค.ศ. รูปแบบ 2026-12 หรือ 12/2026",
                "ระดับ: คน หรือ ทีม",
                "พนักงานขาย: กรอกเฉพาะระดับคน ใช้อีเมลเข้าระบบ (แนะนำ) หรือชื่อตามชีตรายชื่อ",
                "ทีมขาย: กรอกเฉพาะระดับทีม ใช้ชื่อตามชีตรายชื่อ",
                "เป้ายอดขาย: บาท ก่อน VAT เทียบกับยอดขายรวม SO+POS",
                "รายการที่มีเป้าอยู่แล้วในเดือนเดียวกันจะถูกแทนด้วยค่าใหม่",
        ]):
            help_sheet.write_string(row, 0, line)
        names = book.add_worksheet("รายชื่อ")
        names.write_row(0, 0, ["ชื่อพนักงานขาย", "อีเมลเข้าระบบ", "", "ทีมขาย"], header)
        names.set_column(0, 1, 34)
        names.set_column(3, 3, 34)
        domain = [("share", "=", False),
                  ("company_ids", "in", self.env.companies.ids)]
        if allowed is None:
            domain.append(
                ("groups_id", "in", self.env.ref("sales_team.group_sale_salesman").id))
            teams = self.env["crm.team"].search([], order="name")
        else:
            domain.append(("id", "in", list(allowed["user"])))
            teams = self.env["crm.team"].search(
                [("id", "in", list(allowed["team"]))], order="name")
        users = self.env["res.users"].sudo().search(domain, order="login")
        for row, user in enumerate(users, start=1):
            names.write_string(row, 0, user.name or "")
            names.write_string(row, 1, user.login)
        for row, team in enumerate(teams, start=1):
            names.write_string(row, 3, team.name or "")
        book.close()
        return output.getvalue()

    # ------------------------------------------------------------ reading
    @api.model
    def _parse_month(self, value):
        if isinstance(value, date):
            year, month = value.year, value.month
        else:
            value = str(value or "").strip()
            found = re.fullmatch(r"(\d{4})-(\d{1,2})", value)
            if found:
                year, month = int(found[1]), int(found[2])
            else:
                found = re.fullmatch(r"(\d{1,2})/(\d{4})", value)
                if not found:
                    return None
                month, year = int(found[1]), int(found[2])
        # a Buddhist year (25xx) is refused rather than guessed
        if not (2000 <= year <= 2100 and 1 <= month <= 12):
            return None
        return date(year, month, 1)

    @api.model
    def _find_user(self, value):
        users = self.env["res.users"].search(
            [("share", "=", False), ("login", "=ilike", self._escape(value))])
        if not users:
            users = self.env["res.users"].search(
                [("share", "=", False), ("name", "=", value)])
        return users

    @api.model
    def _escape(self, value):
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    @api.model
    def _find_team(self, value):
        teams = self.env["crm.team"].search([("name", "=", value)])
        if not teams:
            teams = self.env["crm.team"].with_context(lang="en_US").search(
                [("name", "=", value)])
        return teams

    @api.model
    def _read_rows(self, data):
        """``data``: the uploaded file in base64."""
        if not data or not isinstance(data, str):
            raise UserError(_("กรุณาเลือกไฟล์ Excel ก่อน"))
        if len(data) > MAX_BYTES * 4 // 3 + 4:
            raise UserError(_("ไฟล์ใหญ่เกิน 5 MB"))
        try:
            book = openpyxl.load_workbook(
                io.BytesIO(base64.b64decode(data, validate=True)),
                read_only=True, data_only=True)
            rows = list(book.worksheets[0].iter_rows(
                max_row=MAX_ROWS + 2, values_only=True))
        except Exception as error:
            raise UserError(_("อ่านไฟล์ไม่ได้ ต้องเป็นไฟล์ .xlsx")) from error
        header = [str(v or "").strip() for v in rows[0]] if rows else []
        missing = [name for name in COLUMNS if name not in header]
        if missing:
            raise UserError(_(
                "หัวตารางในแถวแรกของชีตแรกไม่ครบ ขาด: %s", ", ".join(missing)))
        if len(rows) > MAX_ROWS + 1:
            raise UserError(_("นำเข้าได้ครั้งละไม่เกิน %s แถว", MAX_ROWS))
        index = [header.index(name) for name in COLUMNS]
        for number, row in enumerate(rows[1:], start=2):
            values = [row[i] if i < len(row) else None for i in index]
            if any(v not in (None, "") for v in values):
                yield number, values

    @api.model
    def _parse(self, data):
        """(rows that can be saved, [(row number, problem)] of the others)."""
        self.env["buz.sales.target"].check_access_rights("create")
        allowed = self._check_may_set_targets()
        parsed, errors, seen = [], [], {}
        for number, (month, level, user, team, amount) in self._read_rows(data):
            problems = []
            month_value = self._parse_month(month)
            if not month_value:
                problems.append(_("เดือนไม่ถูกต้อง (ใช้ 2026-12 หรือ 12/2026)"))
            level_value = LEVELS.get(str(level or "").strip().lower())
            if not level_value:
                problems.append(_("ระดับต้องเป็น คน หรือ ทีม"))
            user, team = str(user or "").strip(), str(team or "").strip()
            owner = None
            if level_value:
                name, other = (user, team) if level_value == "user" else (team, user)
                label = _("พนักงานขาย") if level_value == "user" else _("ทีมขาย")
                if other:
                    problems.append(_("กรอกได้เฉพาะพนักงานขายหรือทีมตามระดับ"))
                if not name:
                    problems.append(_("ไม่ได้กรอก%s", label))
                else:
                    owner = (self._find_user(name) if level_value == "user"
                             else self._find_team(name))
                    if len(owner) != 1:
                        problems.append(
                            _("ไม่พบ%s \"%s\"", label, name) if not owner else
                            _("%s \"%s\" ซ้ำกันหลายรายการ", label, name))
                        owner = None
                    elif allowed is not None and owner.id not in allowed[level_value]:
                        problems.append(_(
                            "ไม่มีสิทธิ์ตั้งเป้าให้%s \"%s\"", label, name))
            try:
                if isinstance(amount, bool) or amount in (None, ""):
                    raise ValueError
                amount_value = float(str(amount).replace(",", "").strip())
                if not 0 <= amount_value < 1e13:
                    raise ValueError
            except ValueError:
                problems.append(_("เป้าต้องเป็นตัวเลขตั้งแต่ 0"))
                amount_value = None
            if not problems:
                key = (month_value, level_value, owner.id)
                if key in seen:
                    problems.append(_("ซ้ำกับแถว %s", seen[key]))
                else:
                    seen[key] = number
                    parsed.append((month_value, level_value, owner.id, amount_value))
            errors += [(number, problem) for problem in problems]
        if not parsed and not errors:
            raise UserError(_("ไม่พบข้อมูลในไฟล์"))
        return parsed, errors

    @api.model
    def _existing(self, month, level, owner_id):
        return self.env["buz.sales.target"].search([
            ("company_id", "=", self.env.company.id), ("month", "=", month),
            ("%s_id" % level, "=", owner_id)])

    @api.model
    def preview(self, data):
        """What importing the file would do. Nothing is written."""
        parsed, errors = self._parse(data)
        updated = sum(1 for month, level, owner, _amount in parsed
                      if self._existing(month, level, owner))
        return {
            "ready": len(parsed),
            "new": len(parsed) - updated,
            "update": updated,
            "bad_rows": len({number for number, _problem in errors}),
            "errors": [{"row": number, "problem": problem}
                       for number, problem in errors[:MAX_ERRORS]],
            "more_errors": max(len(errors) - MAX_ERRORS, 0),
        }

    @api.model
    def apply(self, data):
        """Save the rows that passed the check; the others are left out."""
        parsed, errors = self._parse(data)
        if not parsed:
            raise UserError(_("ไม่มีแถวที่นำเข้าได้ กรุณาแก้ไฟล์"))
        Target = self.env["buz.sales.target"]
        created = updated = 0
        for month, level, owner_id, amount in parsed:
            target = self._existing(month, level, owner_id)
            if target:
                target.amount = amount
                updated += 1
            else:
                Target.create({"month": month, "level": level,
                               "%s_id" % level: owner_id, "amount": amount})
                created += 1
        return {"created": created, "updated": updated,
                "skipped": len({number for number, _problem in errors})}
