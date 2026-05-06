# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .budget_utils import format_missing_budget_line_message

_logger = logging.getLogger(__name__)


class MonthlyBudgetFixedCost(models.Model):
    _name = 'monthly.budget.fixed.cost'
    _description = 'Monthly Fixed Cost'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Description', required=True, tracking=True)

    plan_id = fields.Many2one(
        'monthly.budget.plan', 
        string='Budget Plan', 
        required=True, 
        ondelete='cascade',
        index=True
    )

    analytic_account_id = fields.Many2one(
        'account.analytic.account', 
        string='Analytic Account', 
        required=True,
        tracking=True
    )
    company_id = fields.Many2one(
        'res.company',
        related='plan_id.company_id',
        store=True
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        tracking=True
    )
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        tracking=True
    )

    category = fields.Selection([
        ('capex', 'งบลงทุน (CapEx)'),
        ('opex', 'งบดำเนินงาน (OpEx)'),
    ], string='Category', default='opex', tracking=True)

    amount = fields.Monetary(string='Amount', required=True, tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    currency_id = fields.Many2one(
        'res.currency', 
        related='plan_id.company_id.currency_id', 
        store=True
    )

    def _find_budget_line_for_fixed_cost(self):
        """Find the matching budget line for this fixed cost using the engine's dimension matching."""
        self.ensure_one()
        dims = {
            'analytic_account_id': self.analytic_account_id.id,
            'department_id': self.department_id.id,
            'project_id': self.project_id.id,
            'category': self.category,
        }
        return self.env['monthly.budget.line']._find_budget_line(self.plan_id, dims)

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                continue

            budget_line = rec._find_budget_line_for_fixed_cost()
            if not budget_line:
                raise UserError(
                    format_missing_budget_line_message(rec.analytic_account_id.name, rec.plan_id.name)
                )
            
            # --- Concurrency: acquire row-level lock BEFORE reading budget values ---
            self.env['monthly.budget.line']._lock_budget_lines([rec.analytic_account_id.id], rec.plan_id.id)

            # Re-read the current snapshot AFTER acquiring the lock
            rec.plan_id._refresh_budget_snapshot(refresh_report=False)

            if budget_line.available_amount < rec.amount:
                raise UserError(_("Insufficient budget for fixed cost: %s. Available is %s, required is %s") % (
                    rec.name, 
                    '{:,.2f}'.format(budget_line.available_amount), 
                    '{:,.2f}'.format(rec.amount)
                ))

            # Create audit format reservation via budget.engine
            engine = self.env['budget.engine']
            engine.reserve_budget({
                'budget_source': 'monthly',
                'document_model': self._name,
                'document_id': rec.id,
                'amount': rec.amount,
                'date': rec.plan_id.date_from,
                'company_id': rec.company_id.id,
                'analytic_account_id': rec.analytic_account_id.id,
                'note': _('Fixed Cost Reserved: %s') % rec.name,
            })

            rec.plan_id._refresh_budget_snapshot(refresh_report=True)

            rec.state = 'confirmed'

    def action_cancel(self):
        for rec in self:
            if rec.state != 'confirmed':
                continue

            budget_line = rec._find_budget_line_for_fixed_cost()
            if budget_line:
                # Lock row before canceling
                self.env['monthly.budget.line']._lock_budget_lines([rec.analytic_account_id.id], rec.plan_id.id)

            # Reverse reservation audit
            engine = self.env['budget.engine']
            engine.release_budget({
                'budget_source': 'monthly',
                'document_model': self._name,
                'document_id': rec.id,
                'amount': 0, # Engine uses 0 to mean fully release all connected commitments to this doc
                'company_id': rec.company_id.id,
            })

            rec.plan_id._refresh_budget_snapshot(refresh_report=True)

            rec.state = 'cancelled'

    def unlink(self):
        for rec in self:
            if rec.state == 'confirmed':
                raise UserError(_('You cannot delete a confirmed fixed cost. Please cancel it first.'))
        return super().unlink()
