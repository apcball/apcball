import base64
import datetime
import io
import re

import xlsxwriter

from odoo import _, fields, models
from odoo.exceptions import UserError

HEADERS = [
    "เลขที่ JOB", "วันที่ JOB", "วันที่ต้องการของ", "วันเริ่มผลิต", "ประเภท JOB", "แผนกที่เปิด JOB",
    "รหัสสินค้า", "ชื่อสินค้า", "จำนวน", "หน่วย",
    "แผนกที่เบิก", "วันที่เบิก", "เลขที่ใบเบิก", "คลังสินค้า",
    "รหัสสินค้าเบิก", "ชื่อสินค้าเบิก", "จำนวนเบิก", "หน่วยเบิก", "เลขที่ Stock Request",
    "แผนกที่ปิด JOB", "วันที่ปิด JOB", "เลขที่ใบปิด JOB", "คลังสินค้าที่ผลิตได้",
    "รหัสสินค้า", "ชื่อสินค้า", "จำนวน", "หน่วย",
    "คลังสินค้าที่คืน", "รหัสสินค้า", "ชื่อสินค้า", "จำนวน", "หน่วย",
    "ชื่อพนักงาน", "เวลาทำ", "เวลา  OT",
]
NCOLS = len(HEADERS)


class MrpJobReportWizard(models.TransientModel):
    _name = "buz.mrp.job.report.wizard"
    _description = "MRP Job Close Report Wizard"

    date_from = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    date_basis = fields.Selection(
        [("create", "MO Created"), ("start", "MO Start"), ("finished", "MO Finished")],
        string="Date Basis", default="create", required=True,
    )
    state_filter = fields.Selection(
        [("done", "Done Only"), ("all", "All (except cancelled)"), ("all_cancel", "All (including cancelled)")],
        string="Status", default="done", required=True,
    )
    picking_type_ids = fields.Many2many("stock.picking.type", string="Operation Types")
    product_ids = fields.Many2many("product.product", string="Finished Product")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company,
    )

    # ------------------------------------------------------------------
    def _mo_domain(self):
        self.ensure_one()
        field = {"create": "create_date", "start": "date_start", "finished": "date_finished"}[self.date_basis]
        domain = [
            ("company_id", "=", self.company_id.id),
            (field, ">=", fields.Datetime.to_datetime(self.date_from)),
            (field, "<", fields.Datetime.to_datetime(self.date_to) + datetime.timedelta(days=1)),
        ]
        if self.state_filter == "done":
            domain.append(("state", "=", "done"))
        elif self.state_filter == "all":
            domain.append(("state", "!=", "cancel"))
        if self.picking_type_ids:
            domain.append(("picking_type_id", "in", self.picking_type_ids.ids))
        if self.product_ids:
            domain.append(("product_id", "in", self.product_ids.ids))
        return domain

    @staticmethod
    def _split_name(name):
        """Legacy migrated MOs are named '<JOB>/<CLOSE-DOC>'."""
        m = re.match(r"^\s*(B?LOJ\d+)\s*/\s*(B?OJ\S*)", name or "")
        return (m.group(1), m.group(2)) if m else (name or "", name or "")

    def _issue_lines(self, mo, raw_moves):
        """Issued materials (ใบเบิก) from buz_mrp_stock_request; raw moves as fallback."""
        out = []
        pooled_done = False
        for req in mo.stock_request_ids.filtered(lambda q: q.state != "cancel"):
            doc = ", ".join(req.picking_ids.mapped("name")) or req.name
            loc = req.location_id
            common = {
                "doc": doc,
                "srq": req.name,
                "date": req.request_date,
                "warehouse": loc.warehouse_id.name or loc.complete_name or "",
                "dept": req.requested_by.employee_id.department_id.name or "",
            }
            allocs = self.env["mrp.stock.request.allocation"].search(
                [("request_id", "=", req.id), ("mo_id", "=", mo.id)])
            if len(req.mo_ids) > 1 and allocs:
                for al in allocs:
                    out.append(dict(common, product=al.product_id, qty=al.qty_consumed, uom=al.uom_id))
            elif len(req.mo_ids) > 1:
                # pooled request shared by several MOs and no per-MO allocation:
                # this MO's own share is what it consumed, never the whole request
                if pooled_done:
                    continue
                pooled_done = True
                for mv in raw_moves:
                    out.append(dict(
                        common, product=mv.product_id, qty=mv.quantity, uom=mv.product_uom,
                    ))
            else:
                for line in req.line_ids:
                    pickings = line.move_ids.filtered(lambda m: m.state != "cancel").mapped("picking_id")
                    if not pickings:
                        out.append(dict(common, product=line.product_id, qty=line.qty_issued, uom=line.uom_id))
                        continue
                    for pick in pickings:
                        mvs = line.move_ids.filtered(lambda m, pick=pick: m.picking_id == pick and m.state != "cancel")
                        out.append(dict(
                            common, doc=pick.name, date=pick.date_done or pick.scheduled_date,
                            product=line.product_id, qty=sum(mvs.mapped("quantity")), uom=line.uom_id,
                        ))
        if out:
            return out
        for mv in raw_moves:
            has_dept = "department_id" in mv.picking_id._fields
            out.append({
                "doc": mv.picking_id.name or "",
                "srq": "",
                "date": mv.date,
                "warehouse": mv.location_id.warehouse_id.name or mv.location_id.complete_name or "",
                "dept": mv.picking_id.department_id.name if has_dept else "",
                "product": mv.product_id, "qty": mv.quantity, "uom": mv.product_uom,
            })
        return out

    def _return_lines(self, mo, raw_moves):
        """Leftover raw material: issued by the stock request but not consumed by the MO."""
        issued, uoms, loc = {}, {}, {}
        for req in mo.stock_request_ids.filtered(lambda q: q.state != "cancel" and len(q.mo_ids) == 1):
            for line in req.line_ids:
                issued[line.product_id] = issued.get(line.product_id, 0.0) + line.qty_issued
                uoms[line.product_id] = line.uom_id
                loc[line.product_id] = req.location_id
        used = {}
        for mv in raw_moves:
            used[mv.product_id] = used.get(mv.product_id, 0.0) + mv.quantity
        out = []
        for product, qty in issued.items():
            left = qty - used.get(product, 0.0)
            if left > 1e-6:
                src = loc[product]
                out.append({
                    "product": product, "qty": left, "uom": uoms[product],
                    "warehouse": src.warehouse_id.name or src.complete_name or "",
                })
        return out

    def _get_rows(self):
        """Return list of 34-col rows, grouped per MO in sample order."""
        self.ensure_one()
        MO = self.env["mrp.production"]
        mos = MO.search(self._mo_domain(), order="name, id")
        if not mos:
            return []
        # cancelled duplicates (e.g. "<JOB>/<DOC> ยกเลิก") must not repeat a live job
        live_jobs = {self._split_name(m.name)[0] for m in mos if m.state != "cancel"}
        mos = mos.filtered(lambda m: m.state != "cancel" or self._split_name(m.name)[0] not in live_jobs)
        moves = self.env["stock.move"].search([
            "|", ("raw_material_production_id", "in", mos.ids), ("production_id", "in", mos.ids),
            ("state", "=", "done"),
        ])
        raw_by_mo, fin_by_mo = {}, {}
        for mv in moves:
            if mv.raw_material_production_id:
                raw_by_mo.setdefault(mv.raw_material_production_id.id, []).append(mv)
            else:
                fin_by_mo.setdefault(mv.production_id.id, []).append(mv)
        prods = self.env["mrp.workcenter.productivity"].search([("workorder_id.production_id", "in", mos.ids)])
        time_by_mo = {}
        for pr in prods:
            key = (pr.workorder_id.production_id.id, pr.user_id.name or "")
            time_by_mo[key] = time_by_mo.get(key, 0.0) + pr.duration

        def blank():
            return [""] * NCOLS

        def d(val):
            if not val:
                return ""
            if isinstance(val, datetime.datetime):
                return fields.Datetime.context_timestamp(self, val).date()
            return val

        rows = []
        for mo in mos:
            job, close = self._split_name(mo.name)
            dept = mo.user_id.employee_id.department_id.name or ""
            r = blank()
            r[0], r[1], r[2], r[3] = job, d(mo.create_date), d(mo.date_deadline), d(mo.date_start)
            r[4], r[5] = mo.picking_type_id.name, dept
            rows.append(r)
            r = blank()
            r[0], r[6], r[7] = job, mo.product_id.default_code or "", mo.product_id.display_name
            r[8], r[9] = mo.product_qty, mo.product_uom_id.name
            rows.append(r)
            for iss in self._issue_lines(mo, raw_by_mo.get(mo.id, [])):
                if abs(iss["qty"]) < 1e-9:
                    continue  # requested but never issued
                r = blank()
                r[0] = job
                r[10] = iss["dept"] or dept
                r[11] = d(iss["date"])
                r[12] = iss["doc"]
                r[13] = iss["warehouse"]
                r[14], r[15] = iss["product"].default_code or "", iss["product"].display_name
                r[16], r[17] = iss["qty"], iss["uom"].name
                r[18] = iss["srq"]
                rows.append(r)
            for mv in fin_by_mo.get(mo.id, []):
                r = blank()
                r[0], r[19], r[20], r[21] = job, dept, d(mo.date_finished or mv.date), close
                r[22] = mv.location_dest_id.warehouse_id.name or mv.location_dest_id.complete_name
                r[23], r[24] = mv.product_id.default_code or "", mv.product_id.display_name
                r[25], r[26] = mv.quantity, mv.product_uom.name
                rows.append(r)
            if mo.state == "done":
                for ret in self._return_lines(mo, raw_by_mo.get(mo.id, [])):
                    r = blank()
                    r[0], r[20], r[21] = job, d(mo.date_finished), close
                    r[27] = ret["warehouse"]
                    r[28], r[29] = ret["product"].default_code or "", ret["product"].display_name
                    r[30], r[31] = ret["qty"], ret["uom"].name
                    rows.append(r)
            for (mo_id, user), minutes in time_by_mo.items():
                if mo_id == mo.id:
                    r = blank()
                    r[0], r[32], r[33], r[34] = job, user, minutes, ""
                    rows.append(r)
        return rows

    # (title, first col, last col, header colour, row-tint colour)
    _SECTIONS = [
        ("ข้อมูล JOB", 0, 5, "#1F4E78", "#DDEBF7"),
        ("สินค้าที่ผลิต", 6, 9, "#2E75B6", "#EAF1FB"),
        ("การเบิกวัตถุดิบ", 10, 18, "#C55A11", "#FCE4D6"),
        ("การปิด JOB / ผลผลิต", 19, 26, "#548235", "#E2EFDA"),
        ("คืนวัตถุดิบ", 27, 31, "#7030A0", "#EADCF4"),
        ("พนักงาน", 32, 34, "#595959", "#EDEDED"),
    ]
    _WIDTHS = [
        16, 12, 14, 12, 18, 16, 18, 42, 9, 8, 16, 12, 16, 22, 20, 42, 10, 8, 20,
        16, 12, 16, 22, 18, 42, 9, 8, 22, 18, 42, 9, 8, 22, 10, 10,
    ]
    _DATE_COLS = {1, 2, 3, 11, 20}
    _QTY_COLS = {8, 16, 25, 30, 33, 34}

    @staticmethod
    def _row_section(row):
        """Which section a ledger row belongs to (for tinting)."""
        if row[1] != "" or row[4] != "":
            return 0
        if row[6] != "":
            return 1
        if row[10] != "" or row[12] != "":
            return 2
        if row[23] != "":
            return 3
        if row[27] != "" or row[28] != "":
            return 4
        return 5

    def _write_sheet(self, wb, rows):
        font = {"font_name": "Sarabun", "font_size": 10, "valign": "vcenter"}
        fmt = lambda **kw: wb.add_format(dict(font, **kw))  # noqa: E731
        title = fmt(bold=True, font_size=16, font_color="#1F4E78")
        sub = fmt(font_color="#595959", italic=True)
        ws = wb.add_worksheet("ใบปิด JOB")
        ws.hide_gridlines(2)
        ws.set_zoom(90)
        for c, w in enumerate(self._WIDTHS):
            ws.set_column(c, c, w)
        ws.set_row(0, 26)
        ws.write(0, 0, "รายงานใบปิด JOB (Manufacturing Job Close Report)", title)
        ws.write(1, 0, "ช่วงวันที่ %s ถึง %s  |  บริษัท %s  |  %d แถว" % (
            self.date_from.strftime("%d/%m/%Y"), self.date_to.strftime("%d/%m/%Y"),
            self.company_id.name, len(rows)), sub)
        band_row, head_row, first = 3, 4, 5
        ws.set_row(band_row, 20)
        ws.set_row(head_row, 32)
        for name, c0, c1, color, _tint in self._SECTIONS:
            band = fmt(bold=True, font_color="#FFFFFF", bg_color=color, align="center", border=1, border_color="#FFFFFF")
            head = fmt(bold=True, font_color="#FFFFFF", bg_color=color, align="center", text_wrap=True,
                       border=1, border_color="#FFFFFF")
            if c1 > c0:
                ws.merge_range(band_row, c0, band_row, c1, name, band)
            else:
                ws.write(band_row, c0, name, band)
            for c in range(c0, c1 + 1):
                ws.write(head_row, c, HEADERS[c], head)
        cache = {}

        def cell_fmt(sec, col):
            key = (sec, col)
            if key not in cache:
                props = {"bg_color": self._SECTIONS[sec][4], "bottom": 1, "bottom_color": "#D9D9D9"}
                if col in self._DATE_COLS:
                    props.update(num_format="dd/mm/yyyy", align="center")
                elif col in self._QTY_COLS:
                    props.update(num_format="#,##0.00", align="right")
                elif col == 0:
                    props.update(bold=True)
                cache[key] = fmt(**props)
            return cache[key]

        for i, row in enumerate(rows, start=first):
            sec = self._row_section(row)
            for c, v in enumerate(row):
                f = cell_fmt(sec, c)
                if v == "":
                    ws.write_blank(i, c, None, f)
                elif isinstance(v, datetime.date):
                    ws.write_datetime(i, c, datetime.datetime.combine(v, datetime.time()), f)
                else:
                    ws.write(i, c, v, f)
        last = first + len(rows) - 1
        ws.autofilter(head_row, 0, last, NCOLS - 1)
        ws.freeze_panes(first, 1)
        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        ws.repeat_rows(band_row, head_row)
        ws.set_footer("&L&8%s&R&8หน้า &P / &N" % self.company_id.name)

    def action_export_xlsx(self):
        self.ensure_one()
        rows = self._get_rows()
        if not rows:
            raise UserError(_("No manufacturing orders found for the selected filters."))
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        self._write_sheet(wb, rows)
        wb.close()
        att = self.env["ir.attachment"].create({
            "name": "ใบปิด JOB %s-%s.xlsx" % (self.date_from, self.date_to),
            "type": "binary",
            "datas": base64.b64encode(buf.getvalue()),
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % att.id, "target": "self"}
