# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


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
            'fee_amount': preview_data['fee_amount'],
            'vat_amount': preview_data['vat_amount'],
            'wht_amount': preview_data['wht_amount'],
            'total_deductions': preview_data['total_deductions'],
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
