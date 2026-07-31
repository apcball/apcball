# -*- coding: utf-8 -*-

import logging
from odoo import fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpBackdateWizard(models.TransientModel):
    _name = 'mrp.backdate.wizard'
    _description = 'MRP Backdate Wizard'

    production_id = fields.Many2one(
        'mrp.production',
        string='Manufacturing Order',
        ondelete='cascade',
    )
    unbuild_id = fields.Many2one(
        'mrp.unbuild',
        string='Unbuild Order',
        ondelete='cascade',
    )
    backdate = fields.Datetime(
        string='Backdate',
        required=True,
        default=fields.Datetime.now,
        help='The date to use for stock moves, valuation, and journal entries',
    )
    backdate_remark = fields.Text(
        string='Remark',
        required=True,
        help='Reason for backdating this manufacturing order',
    )

    def action_apply_backdate(self):
        """Apply backdate to stock moves, valuation, and journal entries"""
        self.ensure_one()

        if not self.backdate:
            raise UserError(_('Please specify a backdate.'))

        if not self.backdate_remark:
            raise UserError(_('Please provide a remark for backdating.'))

        if not self.production_id and not self.unbuild_id:
            raise UserError(_('No Manufacturing Order or Unbuild Order set on this wizard.'))

        if self.production_id:
            return self._apply_backdate_production()
        return self._apply_backdate_unbuild()

    def _apply_backdate_production(self):
        production = self.production_id
        if production.state != 'done':
            raise UserError(_('Manufacturing Order must be in Done state to apply backdate.'))

        _logger.info('=== Starting Backdate Process for MO: %s ===', production.name)
        _logger.info('Backdate: %s, Remark: %s', self.backdate, self.backdate_remark)

        # Update production with backdate info
        production.write({
            'backdate': self.backdate,
            'backdate_remark': self.backdate_remark,
        })
        _logger.info('Updated MO with backdate fields')

        # Apply backdate immediately
        _logger.info('Applying backdate to moves...')
        production._apply_backdate_to_moves()

        _logger.info('Applying backdate to valuation...')
        production._apply_backdate_to_valuation()

        _logger.info('Applying backdate to account moves...')
        production._apply_backdate_to_account_moves()

        # Final step: Force update MO dates directly in database
        _logger.info('Final force update of MO dates...')
        # Flush all pending operations first
        self.env.flush_all()

        # Use context to prevent recompute during and after update
        production_with_context = production.with_context(skip_date_deadline_compute=True)

        # Direct SQL update to bypass all ORM restrictions and computed fields
        # Update date_deadline and date_finished only (not date_start)
        self.env.cr.execute("""
            UPDATE mrp_production
            SET date_deadline = %s,
                date_finished = %s,
                write_date = NOW(),
                write_uid = %s
            WHERE id = %s
        """, (self.backdate, self.backdate, self.env.uid, production.id))

        # Invalidate cache to force reload
        production_with_context.invalidate_recordset(['date_deadline', 'date_finished'])
        _logger.info('Force updated MO dates: deadline=%s, finished=%s', self.backdate, self.backdate)

        _logger.info('=== Backdate Process Completed ===')

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def _apply_backdate_unbuild(self):
        unbuild = self.unbuild_id
        if unbuild.state != 'done':
            raise UserError(_('Unbuild Order must be in Done state to apply backdate.'))

        _logger.info('=== Starting Backdate Process for Unbuild: %s ===', unbuild.name)
        _logger.info('Backdate: %s, Remark: %s', self.backdate, self.backdate_remark)

        unbuild.write({
            'backdate': self.backdate,
            'backdate_remark': self.backdate_remark,
        })
        _logger.info('Updated Unbuild with backdate fields')

        _logger.info('Applying backdate to moves...')
        unbuild._apply_backdate_to_moves()

        _logger.info('Applying backdate to valuation...')
        unbuild._apply_backdate_to_valuation()

        _logger.info('Applying backdate to account moves...')
        unbuild._apply_backdate_to_account_moves()

        self.env.flush_all()

        _logger.info('=== Backdate Process Completed ===')

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
