# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BudgetAdjustmentWizard(models.TransientModel):
    _name = 'budget.adjustment.wizard'
    _description = 'Budget Adjustment Wizard'

    line_id = fields.Many2one(
        'weekly.budget.line',
        string='Budget Line',
        required=True,
        readonly=True,
    )
    current_amount = fields.Float(
        string='Current Budget',
        readonly=True,
    )
    new_amount = fields.Float(
        string='New Budget',
        required=True,
    )
    reason = fields.Text(
        string='Reason',
        required=True,
    )

    def action_confirm(self):
        """Apply the budget adjustment."""
        self.ensure_one()
        if not self.reason:
            raise UserError(_('Please provide a reason for the adjustment.'))

        line = self.line_id
        old_amount = line.amount_limit

        # Create history record
        self.env['weekly.budget.line.history'].create({
            'line_id': line.id,
            'user_id': self.env.uid,
            'old_amount': old_amount,
            'new_amount': self.new_amount,
            'reason': self.reason,
        })

        # Update the budget line
        line.amount_limit = self.new_amount

        # Post message on the plan's chatter
        line.plan_id.message_post(
            body=_(
                '<strong>Budget Adjusted</strong><br/>'
                'Week: %s<br/>'
                'Previous: %s<br/>'
                'New: %s<br/>'
                'By: %s<br/>'
                'Reason: %s'
            ) % (
                line.name,
                '{:,.2f}'.format(old_amount),
                '{:,.2f}'.format(self.new_amount),
                self.env.user.name,
                self.reason,
            ),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

        return {'type': 'ir.actions.act_window_close'}
