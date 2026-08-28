# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import date, datetime
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
    
    def change_to_backdate(self):
            
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
                