# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class BuzClearingPaymentLine(models.TransientModel):
    _name = 'buz.clearing.payment.line'
    _description = 'Clearing Payment Allocation Line'
    
    wizard_id = fields.Many2one(
        'buz.clearing.payment.wizard', string='Wizard', required=True, ondelete='cascade'
    )
    invoice_id = fields.Many2one(
        'account.move', string='Invoice', required=True,
        domain=[('state', '=', 'posted'), ('move_type', '=', 'out_invoice'), 
                ('payment_state', 'in', ['not_paid', 'partial'])]
    )
    invoice_partner_id = fields.Many2one(
        'res.partner', string='Customer', related='invoice_id.partner_id', readonly=True
    )
    partner_tax_id = fields.Char(
        string='Tax ID', related='invoice_partner_id.vat', readonly=True,
        help='Tax ID of the invoice customer'
    )
    branch_id = fields.Many2one(
        'account.analytic.account', string='Branch',
        readonly=True,
        help='Branch/Analytic Account from the invoice',
        compute='_compute_branch_id', store=False
    )

    @api.depends('invoice_id')
    def _compute_branch_id(self):
        """Extract analytic account from invoice lines"""
        for line in self:
            branch = False
            if line.invoice_id and line.invoice_id.line_ids:
                # Get the first analytic account from invoice lines
                for inv_line in line.invoice_id.line_ids:
                    if inv_line.analytic_distribution and inv_line.analytic_distribution:
                        # Try to get analytic account from distribution
                        for account_id in inv_line.analytic_distribution.keys():
                            try:
                                branch = int(account_id)
                                break
                            except (ValueError, TypeError):
                                continue
                    if branch:
                        break
            line.branch_id = branch
    invoice_date = fields.Date(
        string='Invoice Date', related='invoice_id.invoice_date', readonly=True
    )
    invoice_number = fields.Char(
        string='Invoice Number', related='invoice_id.name', readonly=True
    )
    residual_amount = fields.Monetary(
        string='Residual Amount', related='invoice_id.amount_residual', readonly=True,
        currency_field='currency_id'
    )
    allocate_amount = fields.Monetary(
        string='Allocation Amount', currency_field='currency_id'
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency', related='invoice_id.currency_id', readonly=True
    )
    selected = fields.Boolean(
        string='Selected', default=False
    )
    
    @api.onchange('selected')
    def onchange_selected(self):
        """Set allocate_amount when selected"""
        for line in self:
            if line.selected and not line.allocate_amount:
                line.allocate_amount = line.residual_amount
            elif not line.selected:
                line.allocate_amount = 0.0
    
    @api.constrains('allocate_amount')
    def _check_allocate_amount(self):
        """Validate allocation amount"""
        for line in self:
            if line.selected and line.allocate_amount <= 0:
                raise ValidationError(_('Allocation amount must be greater than 0.'))
            if line.allocate_amount > line.residual_amount:
                raise ValidationError(_('Allocation amount cannot exceed residual amount.'))