# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_repr
from datetime import date, datetime
from .stock_timeline import find_negative_balance
import logging
_logger = logging.getLogger(__name__)

class StockPickingInherit(models.Model):
    _inherit = 'stock.picking'

    def _set_scheduled_date(self):
        for picking in self:
            picking.move_ids.write({'date': picking.scheduled_date})


class PickingBackDate(models.TransientModel):
    _name = 'stock.picking.backdate.wiz'
    _description = "Picking Backdate Wizard"

    date = fields.Datetime('Date', default=fields.Datetime.now)
    picking_ids = fields.Many2many('stock.picking')

    def change_to_backdate_wizard(self):
        active_ids = self.env.context.get('active_ids')
        active_record = self.env[self.env.context.get('active_model')].browse(self.env.context.get('active_id'))

        return{
                'name': 'Backdate Transfer',
                'res_model': 'stock.picking.backdate.wiz',
                'view_mode': 'form',
                'view_id': self.env.ref('stock_picking_backdate_all.stock_picking_backdate_wiz_view_form').id,
                'context': {
                    'default_picking_ids': [(6, 0, active_ids)],
                },
                'target': 'new',
                'type': 'ir.actions.act_window'
            }
    
    def _check_backdate_allowed(self):
        """Future-only users cannot move a picking to a day before today."""
        self.ensure_one()
        if self.env.user.has_group(
                'stock_picking_backdate_all.stock_picking_backdate_assign_group'):
            return
        if not self.date:
            raise UserError(_("Please select a date."))
        target_day = fields.Datetime.context_timestamp(self, self.date).date()
        if target_day < fields.Date.context_today(self):
            raise UserError(_(
                "You can only backdate to today or a future date. "
                "Backdating to the past requires the 'Backdate: Past & Future' group."))

    def _check_backdate_negative_stock(self):
        """Block the new date if it makes stock negative at any point in time.

        All selected pickings are evaluated together, per product and internal
        or transit location, and also per lot/serial. Must run before anything
        is written.
        """
        self.ensure_one()
        if not self.date:
            raise UserError(_("Please select a date."))

        # sudo: a balance filtered by record rules would be wrong.
        MoveLine = self.env['stock.move.line'].sudo()
        moved_lines = MoveLine.search([
            ('move_id.picking_id', 'in', self.picking_ids.ids),
            ('state', '=', 'done'),
            ('product_id.type', '=', 'product'),
        ])
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
            low = min([self.date] + [line.date for line, _qty in moved])
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
                    self.date,
                    product.uom_id.rounding,
                )
                if result:
                    problems.append((product, location, lot, result))

        if problems:
            raise UserError(self._format_negative_stock_message(problems))

    def _format_negative_stock_message(self, problems, limit=10):
        digits = self.env['decimal.precision'].precision_get(
            'Product Unit of Measure')

        def local(value):
            return fields.Datetime.context_timestamp(self, value).strftime(
                '%d/%m/%Y %H:%M')

        lines = [_(
            "ไม่สามารถเปลี่ยนวันที่เป็น %s ได้ เพราะยอดสต็อกจะติดลบ",
            local(self.date))]
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

    def change_to_backdate(self):
        self._check_backdate_allowed()
        self._check_backdate_negative_stock()

        for picking in self.picking_ids:
            
            moveObj = self.env['stock.move'].search([('picking_id','=',picking.id)])
            accmoveObj = self.env['account.move'].search([('stock_move_id','in',moveObj.ids)])
            for acc_mv in accmoveObj:
                # Keep the entry's number. Clearing `name` before re-posting
                # makes Odoo allocate a fresh one from the sequence, so the
                # document silently changes number every time it is backdated.
                acc_mv.button_draft()
                acc_mv.date = self.date
                acc_mv.action_post()

            for move in moveObj:
                move.update({
                    'date':self.date,
                })
                # stock_valuation_layer.create_date is deliberately NOT touched
                # here. It is the key stock.valuation.layer._run_fifo() orders
                # its candidate queue by, so rewriting it silently reorders the
                # FIFO queue after the fact - layers that were already consumed
                # at their original cost end up behind a receipt that did not
                # exist when they were consumed. 11,286 layers on production
                # have an id order that disagrees with their create_date order
                # because of this.
                #
                # The valuation reports bucket by accounting date, which is
                # derived from move.date (set just above), so backdating still
                # lands the transaction in the right period. See
                # ACCOUNTING_DATE_CTE in
                # stock_fifo_valuation_report/reports/stock_fifo_valuation_report.py.

                # accounting_date is the period-facing date on the layer; it is
                # what the Stock Valuation list and the FIFO valuation reports
                # read, and it is safe to move because the FIFO queue does not
                # order by it. See stock_fifo_by_location/models/
                # stock_valuation_layer.py.
                # sudo: backdate users hold the wizard's own group, not
                # necessarily read or write access on stock.valuation.layer.
                layers = self.env['stock.valuation.layer'].sudo().search(
                    [('stock_move_id', '=', move.id)])
                if layers:
                    layers.write({'accounting_date': self.date})

                movelineObj = self.env['stock.move.line'].search([('move_id','=',move.id)])

                for move_line in movelineObj:
                  move_line.update({
                    'date':self.date,
                })  
            picking.update({
                'scheduled_date':self.date,
            })
            picking.write({
                'date_done':self.date,
            })
                