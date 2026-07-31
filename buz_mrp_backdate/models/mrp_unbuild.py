# -*- coding: utf-8 -*-

import logging
from odoo import fields, models, _

_logger = logging.getLogger(__name__)


class MrpUnbuild(models.Model):
    _inherit = 'mrp.unbuild'

    backdate = fields.Datetime(
        string='Backdate',
        help='Force the accounting date for this unbuild order',
        copy=False,
    )
    backdate_remark = fields.Text(
        string='Backdate Remark',
        help='Remark for backdating this unbuild order',
        copy=False,
    )

    def action_open_backdate_wizard(self):
        """Open wizard to set backdate and remark"""
        self.ensure_one()
        return {
            'name': _('Set Backdate'),
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.backdate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_unbuild_id': self.id,
                'default_backdate': self.backdate or fields.Datetime.now(),
                'default_backdate_remark': self.backdate_remark or '',
            }
        }

    def _apply_backdate_to_moves(self):
        """Apply backdate and remark to all related stock moves"""
        for unbuild in self:
            if not unbuild.backdate:
                _logger.warning('No backdate set for Unbuild: %s', unbuild.name)
                continue

            moves = unbuild.consume_line_ids | unbuild.produce_line_ids
            _logger.info('Found %s stock moves to update for Unbuild: %s', len(moves), unbuild.name)
            if moves:
                self.env.cr.execute("""
                    UPDATE stock_move
                    SET date = %s, date_deadline = %s, write_date = NOW(), write_uid = %s
                    WHERE id IN %s
                """, (unbuild.backdate, unbuild.backdate, self.env.uid, tuple(moves.ids)))
                _logger.info('Updated %s stock moves with backdate: %s', len(moves), unbuild.backdate)

                move_lines = moves.mapped('move_line_ids')
                if move_lines:
                    self.env.cr.execute("""
                        UPDATE stock_move_line
                        SET date = %s, write_date = NOW(), write_uid = %s
                        WHERE id IN %s
                    """, (unbuild.backdate, self.env.uid, tuple(move_lines.ids)))
                    _logger.info('Updated %s move lines with backdate', len(move_lines))

                if unbuild.backdate_remark:
                    pickings = moves.mapped('picking_id').filtered(lambda p: p)
                    for picking in pickings:
                        note = picking.note or ''
                        remark_text = f'[Backdate] {unbuild.backdate_remark}'
                        if remark_text not in note:
                            if note:
                                note += '\n'
                            note += remark_text
                            picking.note = note

    def _apply_backdate_to_valuation(self):
        """Apply backdate to stock valuation layers"""
        for unbuild in self:
            if not unbuild.backdate:
                continue

            moves = unbuild.consume_line_ids | unbuild.produce_line_ids
            valuation_layers = self.env['stock.valuation.layer'].search([
                ('stock_move_id', 'in', moves.ids)
            ])

            if valuation_layers:
                self.env.cr.execute("""
                    UPDATE stock_valuation_layer
                    SET create_date = %s
                    WHERE id IN %s
                """, (unbuild.backdate, tuple(valuation_layers.ids)))

                if unbuild.backdate_remark:
                    for layer in valuation_layers:
                        desc = layer.description or ''
                        remark_text = f'Backdate: {unbuild.backdate_remark}'
                        if remark_text not in (desc or ''):
                            if desc:
                                desc += ' | '
                            desc += remark_text
                            layer.description = desc

    def _apply_backdate_to_account_moves(self):
        """Apply backdate to journal entries (account moves)"""
        for unbuild in self:
            if not unbuild.backdate:
                continue

            moves = unbuild.consume_line_ids | unbuild.produce_line_ids
            valuation_layers = self.env['stock.valuation.layer'].search([
                ('stock_move_id', 'in', moves.ids)
            ])

            account_moves = valuation_layers.mapped('account_move_id').filtered(lambda m: m)
            if account_moves:
                backdate_date = unbuild.backdate.date() if unbuild.backdate else fields.Date.today()

                posted_moves = account_moves.filtered(lambda m: m.state == 'posted')
                if posted_moves:
                    posted_moves.button_draft()

                account_moves.write({'date': backdate_date})

                if posted_moves:
                    posted_moves.action_post()

                if unbuild.backdate_remark:
                    for account_move in account_moves:
                        narration = account_move.narration or ''
                        remark_text = f'[Unbuild Backdate] {unbuild.backdate_remark}'
                        if remark_text not in (narration or ''):
                            if narration:
                                narration += '\n'
                            narration += remark_text
                            account_move.narration = narration
