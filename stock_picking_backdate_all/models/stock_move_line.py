# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import UserError
from odoo.tools import float_repr

from ..wizard.stock_timeline import find_negative_balance


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _check_backdate_negative_stock(self, new_date):
        """Block ``new_date`` if re-dating these lines makes stock negative.

        All lines in ``self`` are evaluated together, per product and internal
        or transit location, and also per lot/serial. Must run before anything
        is written. Pass exactly the lines that are about to be re-dated.
        """
        if not new_date:
            raise UserError(_("Please select a date."))

        # sudo: a balance filtered by record rules would be wrong.
        MoveLine = self.env['stock.move.line'].sudo()
        moved_lines = self.sudo().filtered(
            lambda l: l.state == 'done' and l.product_id.type == 'product')
        moved_ids = set(moved_lines.ids)

        # (product, location) -> the selected lines touching it, with sign
        affected = {}
        for line in moved_lines:
            if line.location_id == line.location_dest_id:
                continue
            for location, sign in ((line.location_id, -1),
                                   (line.location_dest_id, 1)):
                if location.usage in ('internal', 'transit'):
                    affected.setdefault((line.product_id, location), []).append(
                        (line, sign * line.quantity_product_uom))

        problems = []
        for (product, location), moved in affected.items():
            low = min([new_date] + [line.date for line, _qty in moved])
            history = MoveLine.search_read([
                ('product_id', '=', product.id),
                ('state', '=', 'done'),
                ('date', '>=', low),
                '|', ('location_id', '=', location.id),
                ('location_dest_id', '=', location.id),
            ], ['date', 'quantity_product_uom', 'location_id',
                'location_dest_id', 'lot_id'], load=False)
            others = []
            for row in history:
                if row['id'] in moved_ids:
                    continue
                sign = ((row['location_dest_id'] == location.id)
                        - (row['location_id'] == location.id))
                others.append(
                    (row['date'], sign * row['quantity_product_uom'], row['lot_id']))
            quants = self.env['stock.quant'].sudo().search([
                ('product_id', '=', product.id),
                ('location_id', '=', location.id),
            ])

            # False = the product as a whole, then each lot being re-dated.
            lots = [False] + list({line.lot_id for line, _qty in moved if line.lot_id})
            for lot in lots:
                result = find_negative_balance(
                    sum(quants.filtered(
                        lambda q: not lot or q.lot_id == lot).mapped('quantity')),
                    [(date, qty) for date, qty, lot_id in others
                     if not lot or lot_id == lot.id],
                    [(line.date, qty) for line, qty in moved
                     if not lot or line.lot_id == lot],
                    new_date,
                    product.uom_id.rounding,
                )
                if result:
                    problems.append((product, location, lot, result))

        if problems:
            raise UserError(self._format_negative_stock_message(problems, new_date))

    def _format_negative_stock_message(self, problems, new_date, limit=10):
        digits = self.env['decimal.precision'].precision_get(
            'Product Unit of Measure')

        def local(value):
            return fields.Datetime.context_timestamp(self, value).strftime(
                '%d/%m/%Y %H:%M')

        lines = [_(
            "ไม่สามารถเปลี่ยนวันที่เป็น %s ได้ เพราะยอดสต็อกจะติดลบ",
            local(new_date))]
        for product, location, lot, (date, after, before) in problems[:limit]:
            name = product.display_name
            if lot:
                name = _("%s (Lot/Serial: %s)", name, lot.name)
            lines.append(_(
                "• %s\n   ตำแหน่ง: %s\n   ยอด ณ %s จะเป็น %s %s (ก่อนเปลี่ยนวันที่: %s)",
                name, location.complete_name, local(date),
                float_repr(after, digits), product.uom_id.name,
                float_repr(before, digits)))
        if len(problems) > limit:
            lines.append(_("... และอีก %s รายการ", len(problems) - limit))
        lines.append(_(
            "กรุณาเลือกวันที่อื่น หรือปรับวันที่ของรายการรับเข้าที่เกี่ยวข้องก่อน"))
        return "\n".join(lines)
