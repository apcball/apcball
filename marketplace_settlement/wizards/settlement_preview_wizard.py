# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SettlementPreviewWizard(models.TransientModel):
    _name = 'settlement.preview.wizard'
    _description = 'Settlement Net-off Preview'

    preview_text = fields.Text(string="Preview", readonly=True)
    warning_message = fields.Text(string="Warning", readonly=True)
    can_perform_netting = fields.Boolean(string="Can Perform Netting", readonly=True)
    settlement_id = fields.Many2one('marketplace.settlement', string='Settlement', readonly=True)
    
    # Amount fields for netting preview
    total_receivables = fields.Monetary(string="Total Receivables", readonly=True)
    total_payables = fields.Monetary(string="Total Payables", readonly=True) 
    net_amount = fields.Monetary(string="Net Amount", readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    
    # Detail text fields
    receivable_details = fields.Text(string="Receivable Details", readonly=True)
    payable_details = fields.Text(string="Payable Details", readonly=True)

    @api.depends('total_receivables', 'total_payables')
    def _compute_can_perform_netting(self):
        for wizard in self:
            wizard.can_perform_netting = (wizard.total_receivables > 0 and wizard.total_payables > 0)

    @api.depends('total_receivables', 'total_payables', 'net_amount')
    def _compute_warnings(self):
        for wizard in self:
            warnings = []
            
            if wizard.total_receivables <= 0:
                warnings.append(_('No settlement receivables found. This may be because:'))
                warnings.append(_('• Settlement has not been posted yet'))
                warnings.append(_('• Settlement amount is zero'))
                warnings.append(_('• Settlement has been reconciled already'))
            
            if wizard.total_payables <= 0:
                warnings.append(_('No outstanding vendor bill payables found. This may be because:'))
                warnings.append(_('• No vendor bills have been linked to this settlement'))
                warnings.append(_('• Vendor bills are not posted'))
                warnings.append(_('• Vendor bills have been reconciled already'))
            
            if abs(wizard.net_amount) > max(wizard.total_receivables, wizard.total_payables) * 2:
                warnings.append(_('Net amount is significantly large. Please verify the amounts.'))
            
            # Add workflow guidance
            if wizard.total_receivables > 0 and wizard.total_payables > 0:
                if wizard.net_amount > 0:
                    warnings.append(_('Net result: Company will receive {:.2f} after netting').format(wizard.net_amount))
                elif wizard.net_amount < 0:
                    warnings.append(_('Net result: Company will pay {:.2f} after netting').format(-wizard.net_amount))
                else:
                    warnings.append(_('Perfect netting: No net amount remaining'))
            
            wizard.warning_message = '\n'.join(warnings) if warnings else ''

    def action_confirm_netting(self):
        """Confirm and perform the AR/AP netting"""
        self.ensure_one()
        
        if not self.can_perform_netting:
            raise UserError(_('Cannot perform netting. Please check the receivable and payable amounts.'))
        
        # Perform the actual netting
        return self.settlement_id.action_netoff_ar_ap()

    def action_cancel(self):
        """Cancel the preview"""
        return {'type': 'ir.actions.act_window_close'}

    @api.model
    def default_get(self, fields_list):
        """Set default values from context"""
        res = super().default_get(fields_list)
        
        settlement_id = self.env.context.get('default_settlement_id')
        if settlement_id:
            settlement = self.env['marketplace.settlement'].browse(settlement_id)
            res.update({
                'settlement_id': settlement_id,
                'currency_id': settlement.company_currency_id.id,
            })
        
        # Set amounts from context if provided
        for field in ['total_receivables', 'total_payables', 'net_amount', 'currency_id']:
            context_key = f'default_{field}'
            if context_key in self.env.context:
                res[field] = self.env.context[context_key]
        
        return res


class MarketplaceSettlementPreviewWizard(models.TransientModel):
    _name = 'marketplace.settlement.preview.wizard'
    _description = 'Settlement Preview Wizard'

    settlement_id = fields.Many2one(
        'marketplace.settlement',
        string='Settlement',
        required=True,
        readonly=True
    )
    
    # Preview data fields
    total_invoice_amount = fields.Float(
        string='Total Invoice Amount',
        readonly=True,
        digits='Product Price'
    )
    
    fee_amount = fields.Float(
        string='Marketplace Fee',
        readonly=True,
        digits='Product Price'
    )
    
    vat_amount = fields.Float(
        string='VAT on Fee',
        readonly=True,
        digits='Product Price'
    )
    
    wht_amount = fields.Float(
        string='Withholding Tax',
        readonly=True,
        digits='Product Price'
    )
    
    total_deductions = fields.Float(
        string='Total Deductions',
        readonly=True,
        digits='Product Price'
    )
    
    net_settlement = fields.Float(
        string='Net Settlement Amount',
        readonly=True,
        digits='Product Price'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        readonly=True
    )
    
    invoice_detail_ids = fields.One2many(
        'marketplace.settlement.preview.line',
        'wizard_id',
        string='Invoice Details',
        readonly=True
    )
    
    @api.model
    def default_get(self, fields_list):
        """Initialize wizard with preview data"""
        res = super().default_get(fields_list)
        
        settlement_id = self.env.context.get('default_settlement_id')
        if not settlement_id:
            return res
            
        settlement = self.env['marketplace.settlement'].browse(settlement_id)
        if not settlement.exists():
            return res
            
        # Get preview data
        preview_data = settlement._calculate_settlement_preview()
        
        # Update wizard fields
        res.update({
            'settlement_id': settlement.id,
            'total_invoice_amount': preview_data['total_invoice_amount'],
            'fee_amount': preview_data.get('total_vendor_bills', 0.0),  # Use vendor bills as fees
            'vat_amount': 0.0,  # VAT is included in vendor bills
            'wht_amount': 0.0,  # WHT is included in vendor bills
            'total_deductions': preview_data.get('total_vendor_bills', 0.0),  # Vendor bills are the deductions
            'net_settlement': preview_data['net_settlement'],
            'currency_id': settlement.company_currency_id.id,
        })
        
        return res

    @api.model
    def create(self, vals):
        """Create wizard and invoice detail lines"""
        wizard = super().create(vals)
        
        if wizard.settlement_id:
            # Get preview data
            preview_data = wizard.settlement_id._calculate_settlement_preview()
            
            # Create invoice detail lines
            for detail in preview_data['invoice_details']:
                self.env['marketplace.settlement.preview.line'].create({
                    'wizard_id': wizard.id,
                    'invoice_name': detail['invoice_name'],
                    'partner_name': detail['partner_name'],
                    'amount': detail['amount'],
                    'currency_id': detail['currency_id'],
                })
        
        return wizard

    def action_create_settlement(self):
        """Create the settlement after preview confirmation"""
        self.ensure_one()
        
        if not self.settlement_id:
            raise UserError(_('Settlement record not found.'))
            
        # Call the settlement creation action
        return self.settlement_id.action_create_settlement()

    def action_cancel(self):
        """Cancel and return to settlement form"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Marketplace Settlement'),
            'res_model': 'marketplace.settlement',
            'res_id': self.settlement_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


class MarketplaceSettlementPreviewLine(models.TransientModel):
    _name = 'marketplace.settlement.preview.line'
    _description = 'Settlement Preview Line'

    wizard_id = fields.Many2one(
        'marketplace.settlement.preview.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    
    invoice_name = fields.Char(
        string='Invoice',
        readonly=True
    )
    
    partner_name = fields.Char(
        string='Customer',
        readonly=True
    )
    
    amount = fields.Float(
        string='Amount',
        readonly=True,
        digits='Product Price'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        readonly=True
    )
