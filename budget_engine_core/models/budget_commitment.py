# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BudgetCommitment(models.Model):
    """
    Records all budget reservations and consumption events.

    This model acts as an audit log / commitment ledger for all
    budget-related actions across multiple budget types (weekly, monthly, etc.)
    """
    _name = 'budget.commitment'
    _description = 'Budget Commitment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        default=lambda self: _('New'),
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        index=True,
    )
    budget_source = fields.Selection(
        selection=[
            ('weekly', 'Weekly Budget'),
            ('monthly', 'Monthly Analytic Budget'),
            ('other', 'Other'),
        ],
        string='Budget Source',
        required=True,
        default='weekly',
        tracking=True,
    )
    document_model = fields.Char(
        string='Source Document Model',
        required=True,
    )
    document_id = fields.Integer(
        string='Source Document ID',
        required=True,
        index=True,
    )
    document_ref = fields.Char(
        string='Source Document Reference',
        compute='_compute_document_ref',
        store=True,
    )
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        required=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    state = fields.Selection(
        selection=[
            ('reserved', 'Reserved'),
            ('used', 'Used'),
            ('released', 'Released'),
        ],
        string='State',
        required=True,
        default='reserved',
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    note = fields.Text(string='Notes')

    # ── computed ────────────────────────────────────────────────

    @api.depends('document_model', 'document_id')
    def _compute_document_ref(self):
        for rec in self:
            if rec.document_model and rec.document_id:
                try:
                    doc = self.env[rec.document_model].browse(rec.document_id)
                    rec.document_ref = doc.display_name if doc.exists() else ''
                except Exception:
                    rec.document_ref = ''
            else:
                rec.document_ref = ''

    # ── ORM ──────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'budget.commitment') or _('New')
        return super().create(vals_list)

    # ── State transitions ────────────────────────────────────────

    def action_mark_used(self):
        """Move reserved commitments to used."""
        self.filtered(lambda r: r.state == 'reserved').write({'state': 'used'})

    def action_release(self):
        """Release a reservation (undo reservation without consuming)."""
        self.filtered(lambda r: r.state == 'reserved').write({'state': 'released'})
