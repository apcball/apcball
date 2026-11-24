import base64
import io
from collections import defaultdict
from datetime import timedelta

import xlsxwriter

from odoo import _, fields, models
from odoo.exceptions import UserError

LC_CODES = ("expense", "labor", "tax", "transit")


class PoReceiptReportWizard(models.TransientModel):
    _name = "buz.po.receipt.report.wizard"
    _description = "PO Receipt Report Wizard"

    receipt_type = fields.Selection(
        [("foreign", "Foreign"), ("domestic", "Domestic"), ("all", "All")],
        required=True,
        default="foreign",
    )
    date_from = fields.Date(
        required=True,
        default=lambda s: fields.Date.context_today(s).replace(day=1),
        string="Effective Date From",
    )
    date_to = fields.Date(
        required=True, default=fields.Date.context_today, string="Effective Date To"
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda s: s.env.company
    )
    warehouse_ids = fields.Many2many("stock.warehouse", string="Warehouses")
    partner_id = fields.Many2one("res.partner", string="Vendor")

    def _get_moves(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_("Date From must be before Date To."))
        start = fields.Datetime.to_datetime(self.date_from)
        end = fields.Datetime.to_datetime(self.date_to) + timedelta(days=1)
        cur = self.company_id.currency_id.id
        domain = [
            ("state", "=", "done"),
            ("picking_id.picking_type_id.code", "=", "incoming"),
            ("date", ">=", start),
            ("date", "<", end),
            ("picking_id.company_id", "=", self.company_id.id),
            ("purchase_line_id", "!=", False),
        ]
        if self.receipt_type == "foreign":
            domain.append(("purchase_line_id.order_id.currency_id", "!=", cur))
        elif self.receipt_type == "domestic":
            domain.append(("purchase_line_id.order_id.currency_id", "=", cur))
        if self.warehouse_ids:
            domain.append(
                ("picking_id.picking_type_id.warehouse_id", "in", self.warehouse_ids.ids)
            )
        if self.partner_id:
            domain.append(("picking_id.partner_id", "child_of", self.partner_id.id))
        moves = self.env["stock.move"].search(domain)
        return moves.sorted(lambda m: (m.picking_id.name, m.sequence, m.id))

    def _get_landed_costs(self, moves):
        """{move_id: {code: amount}} of landed cost actually booked in SVL.

        Amount per (move, landed cost) = sum of the landed-cost valuation
        layers. A layer does not say which cost line it came from, so the
        amount is split across cost types in proportion to the landed cost
        allocation (stock.valuation.adjustment.lines) of that move and cost.
        """
        res = defaultdict(lambda: dict.fromkeys(LC_CODES, 0.0))
        if not moves:
            return res
        layers = self.env["stock.valuation.layer"].search(
            [
                ("stock_move_id", "in", moves.ids),
                ("stock_landed_cost_id", "!=", False),
                ("stock_landed_cost_id.state", "=", "done"),
            ]
        )
        booked = defaultdict(float)  # (move, landed cost) -> SVL value
        for lay in layers:
            booked[(lay.stock_move_id.id, lay.stock_landed_cost_id.id)] += lay.value
        shares = defaultdict(lambda: defaultdict(float))  # key -> code -> allocation
        adj_lines = self.env["stock.valuation.adjustment.lines"].search(
            [("move_id", "in", moves.ids), ("cost_id", "in", layers.stock_landed_cost_id.ids)]
        )
        for ln in adj_lines:
            code = (ln.cost_line_id.cost_type_id.code or "").strip().lower()
            if code not in LC_CODES:
                code = "expense"
            shares[(ln.move_id.id, ln.cost_id.id)][code] += ln.additional_landed_cost
        for key, value in booked.items():
            parts = shares.get(key)
            total = sum(parts.values()) if parts else 0.0
            if not total:
                res[key[0]]["expense"] += value
                continue
            for code, amount in parts.items():
                res[key[0]][code] += value * amount / total
        return res

    def _get_lc_not_in_stock(self, moves):
        """{move_id: allocated landed cost - landed cost booked in SVL}.

        Odoo only books landed cost in SVL for the quantity still on hand when
        the landed cost is validated; the rest has no valuation layer.
        """
        res = defaultdict(float)
        if not moves:
            return res
        adj_lines = self.env["stock.valuation.adjustment.lines"].search(
            [("move_id", "in", moves.ids), ("cost_id.state", "=", "done")]
        )
        for ln in adj_lines:
            res[ln.move_id.id] += ln.additional_landed_cost
        layers = self.env["stock.valuation.layer"].search(
            [
                ("stock_move_id", "in", moves.ids),
                ("stock_landed_cost_id", "!=", False),
                ("stock_landed_cost_id.state", "=", "done"),
            ]
        )
        for lay in layers:
            res[lay.stock_move_id.id] -= lay.value
        return res

    def _get_base_values(self, moves):
        """{move_id: receipt value booked in SVL (landed cost excluded)}."""
        res = defaultdict(float)
        if not moves:
            return res
        layers = self.env["stock.valuation.layer"].search(
            [("stock_move_id", "in", moves.ids), ("stock_landed_cost_id", "=", False)]
        )
        for lay in layers:
            res[lay.stock_move_id.id] += lay.value
        return res

    def _get_rate(self, move, foreign):
        if not foreign:
            return 1.0
        picking = move.picking_id
        if picking.exchange_rate:
            return picking.exchange_rate
        order = move.purchase_line_id.order_id
        return order.currency_id._get_conversion_rate(
            order.currency_id,
            self.company_id.currency_id,
            self.company_id,
            move.date or picking.date_done or fields.Date.context_today(self),
        )

    def _prepare_rows(self):
        moves = self._get_moves()
        lcs = self._get_landed_costs(moves)
        not_in_stock = self._get_lc_not_in_stock(moves)
        base_values = self._get_base_values(moves)
        rows = []
        for mv in moves:
            pol = mv.purchase_line_id
            order = pol.order_id
            foreign = order.currency_id != self.company_id.currency_id
            rate = self._get_rate(mv, foreign)
            qty = mv.quantity
            cost = qty * pol.price_unit
            base_thb = cost * rate
            if foreign and cost and base_values.get(mv.id):
                # Use the rate the valuation layer really used, so CostBath
                # matches Stock Valuation total value.
                base_thb = base_values[mv.id]
                rate = base_thb / cost
            lc = lcs.get(mv.id) or dict.fromkeys(LC_CODES, 0.0)
            rows.append(
                {
                    "doc_no": mv.picking_id.name,
                    "batch_no": mv.picking_id.batch_id.name or "",
                    "date": mv.date or mv.picking_id.date_done,
                    "ref_no": order.partner_ref or order.name,
                    "po": order.name,
                    "prd_id": mv.product_id.default_code or "",
                    "prd_name": mv.product_id.name,
                    "qty": qty,
                    "price": pol.price_unit,
                    "cost": cost,
                    "rate": rate,
                    "discount": pol["discount"] if "discount" in pol._fields else 0.0,
                    "currency": order.currency_id.name,
                    "foreign": foreign,
                    "exp": lc["expense"],
                    "labor": lc["labor"],
                    "tax": lc["tax"],
                    "transit": lc["transit"],
                    "lc_not_stock": not_in_stock.get(mv.id, 0.0),
                    "cost_baht": base_thb + (sum(lc.values()) if foreign else 0.0),
                    "invt_name": mv.picking_id.picking_type_id.warehouse_id.name or "",
                }
            )
        return rows

    def action_export_xlsx(self):
        self.ensure_one()
        rows = self._prepare_rows()
        if not rows:
            raise UserError(_("No PO receipts found for this period."))
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        ws = wb.add_worksheet("PO Receipts")
        title = wb.add_format({"bold": True, "font_size": 14})
        head = wb.add_format(
            {"bold": True, "bg_color": "#D9E1F2", "border": 1, "text_wrap": True}
        )
        cell = wb.add_format({"border": 1})
        num = wb.add_format({"border": 1, "num_format": "#,##0.00"})
        rate_f = wb.add_format({"border": 1, "num_format": "#,##0.0000"})
        dt = wb.add_format({"border": 1, "num_format": "d/m/yyyy"})
        label = dict(self._fields["receipt_type"].selection)[self.receipt_type]
        ws.write(0, 0, "PO Receipt Report - %s" % label, title)
        ws.write(
            1,
            0,
            "Effective date: %s to %s | Company: %s"
            % (self.date_from, self.date_to, self.company_id.name),
        )
        # (header, row key, format, width); None key = date column
        columns = [
            ("DocNo", "doc_no", cell, 16),
            ("BatchNo", "batch_no", cell, 16),
            ("Date", "date", dt, 11),
            ("RefNo", "ref_no", cell, 16),
            ("PO", "po", cell, 14),
            ("PrdID", "prd_id", cell, 18),
            ("PrdName", "prd_name", cell, 40),
            ("QT", "qty", num, 10),
            ("PricePerUnit", "price", num, 13),
            ("Cost", "cost", num, 13),
            ("Rate", "rate", rate_f, 11),
            ("Discount", "discount", num, 10),
            ("Currency", "currency", cell, 9),
            ("Exp", "exp", num, 13),
            ("Labor", "labor", num, 13),
            ("Tax", "tax", num, 13),
            ("Transit", "transit", num, 13),
            ("LC NotInStock", "lc_not_stock", num, 15),
            ("CostBath", "cost_baht", num, 15),
            ("InvtName", "invt_name", cell, 18),
        ]
        if self.receipt_type == "domestic":
            hidden = {"rate", "exp", "labor", "tax", "transit", "lc_not_stock"}
            columns = [col for col in columns if col[1] not in hidden]
        for idx, (h, _key, _fmt, width) in enumerate(columns):
            ws.write(3, idx, h, head)
            ws.set_column(idx, idx, width)
        row = 4
        for r in rows:
            for idx, (_h, key, fmt, _w) in enumerate(columns):
                val = r[key]
                if key == "date":
                    val = fields.Datetime.context_timestamp(self, val).replace(tzinfo=None)
                    ws.write_datetime(row, idx, val, fmt)
                elif fmt in (num, rate_f):
                    ws.write_number(row, idx, val, fmt)
                else:
                    ws.write(row, idx, val, fmt)
            row += 1
        ws.freeze_panes(4, 0)
        ws.autofilter(3, 0, row - 1, len(columns) - 1)
        wb.close()
        att = self.env["ir.attachment"].create(
            {
                "name": "po_receipt_report_%s_%s_%s.xlsx"
                % (self.receipt_type, self.date_from, self.date_to),
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
