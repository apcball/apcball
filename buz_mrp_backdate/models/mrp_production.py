# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    backdate = fields.Datetime(
        string='Backdate',
        help='Force the accounting date for this manufacturing order',
        copy=False,
    )
    backdate_remark = fields.Text(
        string='Backdate Remark',
        help='Remark for backdating this manufacturing order',
        copy=False,
    )
    
    @api.depends('move_finished_ids.date_deadline', 'backdate')
    def _compute_date_deadline(self):
        """Override to prevent recomputation when backdate is set"""
        # Skip computation if in backdate update context
        if self.env.context.get('skip_date_deadline_compute'):
            _logger.info('Skipping date_deadline computation (context flag set)')
            return
            
        for production in self:
            # Skip computation if backdate is set (already updated via SQL)
            if production.backdate and production.state == 'done':
                _logger.info('Skipping date_deadline computation for MO %s (backdate set)', production.name)
                continue
            # Otherwise use standard computation
            super(MrpProduction, production)._compute_date_deadline()

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
                'default_production_id': self.id,
                'default_backdate': self.backdate or fields.Datetime.now(),
                'default_backdate_remark': self.backdate_remark or '',
            }
        }

    def _apply_backdate_to_moves(self):
        """Apply backdate and remark to all related stock moves"""
        for production in self:
            if not production.backdate:
                _logger.warning('No backdate set for MO: %s', production.name)
                continue
            
            # Update all stock moves related to this MO
            moves = production.move_raw_ids | production.move_finished_ids
            _logger.info('Found %s stock moves to update for MO: %s', len(moves), production.name)
            if moves:
                # Use SQL to bypass ORM restrictions on done moves
                # Update both date and date_deadline
                self.env.cr.execute("""
                    UPDATE stock_move 
                    SET date = %s, date_deadline = %s, write_date = NOW(), write_uid = %s
                    WHERE id IN %s
                """, (production.backdate, production.backdate, self.env.uid, tuple(moves.ids)))
                _logger.info('Updated %s stock moves with backdate: %s', len(moves), production.backdate)
                
                # Also update move lines
                move_lines = moves.mapped('move_line_ids')
                if move_lines:
                    self.env.cr.execute("""
                        UPDATE stock_move_line 
                        SET date = %s, write_date = NOW(), write_uid = %s
                        WHERE id IN %s
                    """, (production.backdate, self.env.uid, tuple(move_lines.ids)))
                    _logger.info('Updated %s move lines with backdate', len(move_lines))
                
                # Add remark to picking note if exists
                if production.backdate_remark:
                    pickings = moves.mapped('picking_id').filtered(lambda p: p)
                    for picking in pickings:
                        note = picking.note or ''
                        remark_text = f'[Backdate] {production.backdate_remark}'
                        if remark_text not in note:
                            if note:
                                note += '\n'
                            note += remark_text
                            picking.note = note

    def _apply_backdate_to_valuation(self):
        """Apply backdate to stock valuation layers"""
        for production in self:
            if not production.backdate:
                continue
            
            # Get all stock valuation layers related to moves
            moves = production.move_raw_ids | production.move_finished_ids
            valuation_layers = self.env['stock.valuation.layer'].search([
                ('stock_move_id', 'in', moves.ids)
            ])
            
            if valuation_layers:
                # Update using SQL to bypass ORM restrictions on create_date
                self.env.cr.execute("""
                    UPDATE stock_valuation_layer 
                    SET create_date = %s 
                    WHERE id IN %s
                """, (production.backdate, tuple(valuation_layers.ids)))
                
                # Add remark to description
                if production.backdate_remark:
                    for layer in valuation_layers:
                        desc = layer.description or ''
                        remark_text = f'Backdate: {production.backdate_remark}'
                        if remark_text not in (desc or ''):
                            if desc:
                                desc += ' | '
                            desc += remark_text
                            layer.description = desc

    def _apply_backdate_to_account_moves(self):
        """Apply backdate to journal entries (account moves)"""
        for production in self:
            if not production.backdate:
                continue
            
            # Get all account moves related to stock moves
            moves = production.move_raw_ids | production.move_finished_ids
            valuation_layers = self.env['stock.valuation.layer'].search([
                ('stock_move_id', 'in', moves.ids)
            ])
            
            account_moves = valuation_layers.mapped('account_move_id').filtered(lambda m: m)
            if account_moves:
                backdate_date = production.backdate.date() if production.backdate else fields.Date.today()
                
                # Unpost journal entries first if they are posted
                posted_moves = account_moves.filtered(lambda m: m.state == 'posted')
                if posted_moves:
                    posted_moves.button_draft()
                
                # Update date
                account_moves.write({'date': backdate_date})
                
                # Re-post the moves
                if posted_moves:
                    posted_moves.action_post()
                
                # Add remark to narration
                if production.backdate_remark:
                    for account_move in account_moves:
                        narration = account_move.narration or ''
                        remark_text = f'[MO Backdate] {production.backdate_remark}'
                        if remark_text not in (narration or ''):
                            if narration:
                                narration += '\n'
                            narration += remark_text
                            account_move.narration = narration


