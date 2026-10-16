import base64
import io
from datetime import timedelta

import xlsxwriter

from odoo import _, fields, models
from odoo.exceptions import UserError


class PickingReturnReportWizard(models.TransientModel):
    _name = "buz.picking.return.report.wizard"
    _description = "Picking Return Report Wizard"

    date_from = fields.Date(
        required=True,
        default=lambda s: fields.Date.context_today(s).replace(day=1),
        string="Source Done From",
    )
    date_to = fields.Date(
        required=True, default=fields.Date.context_today, string="Source Done To"
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda s: s.env.company
    )
    picking_type_ids = fields.Many2many(
        "stock.picking.type", string="Source Operation Types"
    )
    partner_id = fields.Many2one("res.partner", string="Partner")

    def _get_return_moves(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_("Date From must be before Date To."))
        start = fields.Datetime.to_datetime(self.date_from)
        end = fields.Datetime.to_datetime(self.date_to) + timedelta(days=1)
        domain = [
            ("origin_returned_move_id", "!=", False),
            ("picking_id.state", "in", ("assigned", "done")),
            ("origin_returned_move_id.picking_id.state", "=", "done"),
            ("origin_returned_move_id.picking_id.date_done", ">=", start),
            ("origin_returned_move_id.picking_id.date_done", "<", end),
            ("origin_returned_move_id.picking_id.company_id", "=", self.company_id.id),
        ]
        if self.picking_type_ids:
            domain.append(
                (
                    "origin_returned_move_id.picking_id.picking_type_id",
                    "in",
                    self.picking_type_ids.ids,
                )
            )
        if self.partner_id:
            domain.append(
                (
                    "origin_returned_move_id.picking_id.partner_id",
                    "child_of",
                    self.partner_id.id,
                )
            )
        moves = self.env["stock.move"].search(domain)
        return moves.sorted(
            lambda m: (
                m.origin_returned_move_id.picking_id.name,
                m.picking_id.name,
                m.sequence,
                m.id,
            )
        )

    def action_export_xlsx(self):
        self.ensure_one()
        moves = self._get_return_moves()
        if not moves:
            raise UserError(_("No returned pickings found for this period."))
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        ws = wb.add_worksheet("Picking Returns")
        title = wb.add_format({"bold": True, "font_size": 14})
        head = wb.add_format(
            {"bold": True, "bg_color": "#D9E1F2", "border": 1, "text_wrap": True}
        )
        cell = wb.add_format({"border": 1})
        num = wb.add_format({"border": 1, "num_format": "#,##0.00"})
        dt = wb.add_format({"border": 1, "num_format": "yyyy-mm-dd hh:mm"})
        intc = wb.add_format({"border": 1, "num_format": "0"})
        okf = wb.add_format({"border": 1, "bg_color": "#C6EFCE"})
        warnf = wb.add_format({"border": 1, "bg_color": "#FFEB9C"})
        ws.write(0, 0, "Picking Return Report", title)
        ws.write(
            1,
            0,
            "Source done: %s to %s | Company: %s"
            % (self.date_from, self.date_to, self.company_id.name),
        )
        headers = [
            "Source Document", "Source Done Date", "Partner", "Source Operation",
            "Return Document", "Return State", "Return Effect Date",
            "Day Gap (Return - Source)", "Same Day?",
            "Product Code", "Product", "Source Qty", "Return Demand", "Return Done",
            "UoM", "Lot/Serial",
            "Return Source Location", "Return Destination Location",
            "Original Source Location", "Original Destination Location",
        ]
        state_label = dict(self.env["stock.picking"]._fields["state"].selection)
        for col, h in enumerate(headers):
            ws.write(3, col, h, head)
        row = 4
        for mv in moves:
            orig = mv.origin_returned_move_id
            ret = mv.picking_id
            src = orig.picking_id
            lots = ", ".join(mv.move_line_ids.lot_id.mapped("name"))
            src_dt = fields.Datetime.context_timestamp(self, src.date_done)
            rdate = mv.date or ret.date_done or ret.scheduled_date
            ret_dt = fields.Datetime.context_timestamp(self, rdate) if rdate else None
            c = iter(range(len(headers)))
            ws.write(row, next(c), src.name, cell)
            ws.write_datetime(row, next(c), src_dt.replace(tzinfo=None), dt)
            ws.write(row, next(c), src.partner_id.display_name or "", cell)
            ws.write(row, next(c), src.picking_type_id.display_name or "", cell)
            ws.write(row, next(c), ret.name, cell)
            ws.write(row, next(c), state_label.get(ret.state, ret.state), cell)
            if ret_dt:
                ws.write_datetime(row, next(c), ret_dt.replace(tzinfo=None), dt)
                gap = (ret_dt.date() - src_dt.date()).days
                ws.write_number(row, next(c), gap, intc)
                if gap == 0:
                    label, fmt = "Same day", okf
                else:
                    label, fmt = "%+d day(s)" % gap, warnf
                ws.write(row, next(c), label, fmt)
            else:
                for _i in range(3):
                    ws.write(row, next(c), "", cell)
            ws.write(row, next(c), mv.product_id.default_code or "", cell)
            ws.write(row, next(c), mv.product_id.name, cell)
            ws.write_number(row, next(c), orig.quantity, num)
            ws.write_number(row, next(c), mv.product_uom_qty, num)
            ws.write_number(row, next(c), mv.quantity if ret.state == "done" else 0.0, num)
            ws.write(row, next(c), mv.product_uom.name or "", cell)
            ws.write(row, next(c), lots, cell)
            ws.write(row, next(c), mv.location_id.complete_name or "", cell)
            ws.write(row, next(c), mv.location_dest_id.complete_name or "", cell)
            ws.write(row, next(c), orig.location_id.complete_name or "", cell)
            ws.write(row, next(c), orig.location_dest_id.complete_name or "", cell)
            row += 1
        widths = [18, 18, 28, 22, 18, 12, 18, 14, 14, 16, 36, 12, 12, 12, 8, 18, 30, 30, 30, 30]
        for col, w in enumerate(widths):
            ws.set_column(col, col, w)
        ws.freeze_panes(4, 0)
        ws.autofilter(3, 0, row - 1, len(headers) - 1)
        wb.close()
        att = self.env["ir.attachment"].create(
            {
                "name": "picking_return_report_%s_%s.xlsx"
                % (self.date_from, self.date_to),
                "type": "binary",
                "datas": base64.b64encode(buf.getvalue()),
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % att.id,
            "target": "self",
        }
