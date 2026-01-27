# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class BuzClearingPaymentCreditLine(models.TransientModel):
    _name = 'buz.clearing.payment.credit.line'
    _description = 'Clearing Payment Credit Note Line'
    
    wizard_id = fields.Many2one(
        'buz.clearing.payment.wizard', 
        string='Wizard', 
        required=True, 
        ondelete='cascade'
    )
    credit_note_id = fields.Many2one(
        'account.move', 
        string='Credit Note', 
        required=True,
        domain=[('state', '=', 'posted'), 
                ('move_type', '=', 'out_refund'), 
                ('payment_state', 'in', ['not_paid', 'partial'])]
    )
    credit_note_number = fields.Char(
        string='Number', 
        related='credit_note_id.name', 
        readonly=True
    )
    credit_note_date = fields.Date(
        string='Date', 
        related='credit_note_id.invoice_date', 
        readonly=True
    )
    credit_note_partner_id = fields.Many2one(
        'res.partner', 
        string='Customer', 
        related='credit_note_id.partner_id', 
        readonly=True
    )
    partner_tax_id = fields.Char(
        string='Tax ID', 
        related='credit_note_partner_id.vat', 
        readonly=True
    )
    residual_amount = fields.Monetary(
        string='Available Amount', 
        compute='_compute_residual_amount',
        currency_field='currency_id',
        readonly=True,
        store=False
    )
    
    @api.depends('credit_note_id', 'credit_note_id.amount_residual')
    def _compute_residual_amount(self):
        """Compute residual amount as absolute value for credit notes"""
        for line in self:
            if line.credit_note_id:
                # For credit notes, amount_residual is negative, so we use abs()
                line.residual_amount = abs(line.credit_note_id.amount_residual)
            else:
                line.residual_amount = 0.0
    use_amount = fields.Monetary(
        string='Use Amount', 
        currency_field='currency_id',
        default=0.0
    )
    currency_id = fields.Many2one(
        'res.currency', 
        related='credit_note_id.currency_id', 
        readonly=True
    )
    selected = fields.Boolean(
        string='Select', 
        default=False
    )
    
    @api.onchange('selected')
    def _onchange_selected(self):
        """Auto-fill use_amount when selected"""
        if self.selected and not self.use_amount:
            self.use_amount = self.residual_amount
        elif not self.selected:
            self.use_amount = 0.0
    
    @api.onchange('use_amount')
    def _onchange_use_amount(self):
        """Auto-select when use_amount is entered"""
        if self.use_amount > 0:
            self.selected = True
        else:
            self.selected = False
    
    @api.constrains('use_amount', 'residual_amount')
    def _check_use_amount(self):
        """Validate use_amount does not exceed residual_amount"""
        for line in self:
            if line.use_amount < 0:
                raise ValidationError(
                    _('Use amount must be greater than or equal to 0 for credit note %s') 
                    % line.credit_note_number
                )
            if line.use_amount > line.residual_amount:
                raise ValidationError(
                    _('Use amount (%.2f) cannot exceed available amount (%.2f) for credit note %s') 
                    % (line.use_amount, line.residual_amount, line.credit_note_number)
                )
