# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MonthlyBudgetAmendmentWizard(models.TransientModel):
    """
    Wizard to formally amend a budget plan's total budget.
    Creates an audit trail record in monthly.budget.amendment.
    """
    _name = 'monthly.budget.amendment.wizard'
    _description = 'Budget Amendment Wizard'

    plan_id = fields.Many2one(
        'monthly.budget.plan',
        string='Budget Plan',
        required=True,
    )
    current_budget = fields.Monetary(
        string='Current Budget',
        currency_field='currency_id',
        readonly=True,
    )
    new_total_budget = fields.Monetary(
        string='New Total Budget',
        currency_field='currency_id',
        required=True,
    )
    change_amount = fields.Monetary(
        string='Change Amount',
        currency_field='currency_id',
        compute='_compute_change_amount',
    )
    amendment_type = fields.Selection(
        selection=[
            ('increase', 'Increase'),
            ('decrease', 'Decrease'),
        ],
        string='Type',
        compute='_compute_change_amount',
    )
    currency_id = fields.Many2one(
        related='plan_id.currency_id',
        readonly=True,
    )
    reason = fields.Text(
        string='Reason',
        required=True,
        help='Reason for the budget amendment (mandatory)',
    )

    @api.depends('current_budget', 'new_total_budget')
    def _compute_change_amount(self):
        for rec in self:
            rec.change_amount = rec.new_total_budget - rec.current_budget
            if rec.change_amount >= 0:
                rec.amendment_type = 'increase'
            else:
                rec.amendment_type = 'decrease'

    def action_apply(self):
        """Apply the budget amendment and create audit record."""
        self.ensure_one()
        if not self.reason or not self.reason.strip():
            raise UserError(_('Please provide a reason for the budget amendment.'))

        if self.new_total_budget == self.current_budget:
            raise UserError(_('New budget is the same as current budget. No change to apply.'))

        plan = self.plan_id

        # Create amendment record
        self.env['monthly.budget.amendment'].create({
            'plan_id': plan.id,
            'amendment_type': self.amendment_type,
            'amount_before': self.current_budget,
            'amount_change': self.change_amount,
            'amount_after': self.new_total_budget,
            'reason': self.reason.strip(),
        })

        # Apply the change — use direct SQL to bypass write() override
        # which would create a duplicate amendment record
        plan.with_context(skip_amendment_tracking=True).write({
            'total_budget': self.new_total_budget,
        })

        # Post chatter message
        plan.message_post(
            body=_(
                '<strong>📝 Budget Amended</strong><br/>'
                'Changed by: %s<br/>'
                'Before: %s → After: %s (Change: %s)<br/>'
                'Reason: %s'
            ) % (
                self.env.user.name,
                '{:,.2f}'.format(self.current_budget),
                '{:,.2f}'.format(self.new_total_budget),
                '{:+,.2f}'.format(self.change_amount),
                self.reason.strip(),
            ),
        )

        return {'type': 'ir.actions.act_window_close'}
