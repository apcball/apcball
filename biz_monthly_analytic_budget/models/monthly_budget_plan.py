# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MonthlyBudgetPlan(models.Model):
    """Monthly Budget Plan — defines total budget for a calendar month."""
    _name = 'monthly.budget.plan'
    _description = 'Monthly Budget Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        default=lambda self: _('New'),
        tracking=True,
    )
    date_from = fields.Date(
        string='From',
        required=True,
        tracking=True,
    )
    date_to = fields.Date(
        string='To',
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        readonly=True,
        store=True,
    )
    total_budget = fields.Monetary(
        string='Total Budget',
        currency_field='currency_id',
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('closed', 'Closed'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    budget_line_ids = fields.One2many(
        'monthly.budget.line',
        'plan_id',
        string='Budget Lines',
        copy=True,
    )

    # ── computed totals ──────────────────────────────────────────

    allocated_amount = fields.Monetary(
        string='Total Allocated',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    reserved_amount = fields.Monetary(
        string='Total Reserved',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    used_amount = fields.Monetary(
        string='Total Used',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    available_amount = fields.Monetary(
        string='Total Available',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    allocated_percentage = fields.Float(
        string='Allocated (%)',
        compute='_compute_totals',
        store=True,
    )

    @api.depends(
        'budget_line_ids.budget_amount',
        'budget_line_ids.reserved_amount',
        'budget_line_ids.used_amount',
        'total_budget',
    )
    def _compute_totals(self):
        for plan in self:
            lines = plan.budget_line_ids
            plan.allocated_amount = sum(lines.mapped('budget_amount'))
            plan.reserved_amount = sum(lines.mapped('reserved_amount'))
            plan.used_amount = sum(lines.mapped('used_amount'))
            plan.available_amount = (
                plan.total_budget - plan.reserved_amount - plan.used_amount
            )
            plan.allocated_percentage = (
                (plan.allocated_amount / plan.total_budget)
                if plan.total_budget else 0.0
            )

    # ── ORM ──────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'monthly.budget.plan') or _('New')
        return super().create(vals_list)

    # ── Constraints ──────────────────────────────────────────────

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for plan in self:
            if plan.date_from and plan.date_to and plan.date_from > plan.date_to:
                raise ValidationError(_("'From' date must be before 'To' date."))

    @api.constrains('budget_line_ids', 'total_budget')
    def _check_allocation(self):
        for plan in self:
            total_pct = sum(plan.budget_line_ids.mapped('percentage'))
            if total_pct > 100.0001:
                raise ValidationError(
                    _('Total percentage of budget lines (%.2f%%) exceeds 100%%.') % total_pct
                )

    # ── State actions ────────────────────────────────────────────

    def action_confirm(self):
        self.ensure_one()
        if self.state != 'draft':
            raise ValidationError(_('Only draft plans can be confirmed.'))
        self.write({'state': 'confirmed'})

    def action_close(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise ValidationError(_('Only confirmed plans can be closed.'))
        self.write({'state': 'closed'})

    def action_reset_draft(self):
        self.ensure_one()
        self.write({'state': 'draft'})

    def action_recompute_budget(self):
        """Reset and re-calculate reserved and used amounts from scratch based on payment_date."""
        self.ensure_one()
        # Clear existing lines and commitment records for this period/company
        self.budget_line_ids.write({
            'reserved_amount': 0.0,
            'used_amount': 0.0,
        })
        
        # Clear commitment audit records for documents that fall in this plan
        self.env['budget.commitment'].sudo().search([
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
            ('budget_source', '=', 'monthly')
        ]).unlink()

        # Re-scan Employee Purchase Requisitions
        prs = self.env['employee.purchase.requisition'].sudo().search([
            ('payment_date', '>=', self.date_from),
            ('payment_date', '<=', self.date_to),
            ('state', 'not in', ('draft', 'cancelled')),
            ('company_id', '=', self.company_id.id),
        ])
        for pr in prs:
            pr._reserve_monthly_analytic_budget()
            
        # Re-scan Purchase Orders (consume reservations)
        pos = self.env['purchase.order'].sudo().search([
            ('payment_date', '>=', self.date_from),
            ('payment_date', '<=', self.date_to),
            ('state', 'in', ('purchase', 'done')),
            ('company_id', '=', self.company_id.id),
        ])
        for po in pos:
            # Note: _consume_monthly_analytic_budget expects reservations to already exist 
            # if from PR. Since we re-ran _reserve above, they should exist.
            po._consume_monthly_analytic_budget()

        return True
