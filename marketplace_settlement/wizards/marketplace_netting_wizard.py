from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MarketplaceNettingWizard(models.TransientModel):
    _name = 'marketplace.netting.wizard'
    _description = 'AR/AP Netting Wizard'

    settlement_id = fields.Many2one('marketplace.settlement', string='Settlement', required=True)
    marketplace_partner_id = fields.Many2one(related='settlement_id.marketplace_partner_id', string='Marketplace Partner', readonly=True)
    
    # Available vendor bills for netting
    available_vendor_bill_ids = fields.Many2many('account.move', 'netting_wizard_available_bills_rel', 
                                                'wizard_id', 'bill_id',
                                                string='Available Vendor Bills',
                                                compute='_compute_available_vendor_bills')
    
    # Selected vendor bills for netting
    selected_vendor_bill_ids = fields.Many2many('account.move', 'netting_wizard_selected_bills_rel', 
                                               'wizard_id', 'bill_id',
                                               string='Vendor Bills to Net',
                                               domain="[('id', 'in', available_vendor_bill_ids)]")
    
    # Summary fields
    total_receivables = fields.Monetary('Total Receivables', currency_field='currency_id', 
                                       related='settlement_id.net_settlement_amount', readonly=True)
    total_selected_bills = fields.Monetary('Selected Vendor Bills', currency_field='currency_id', 
                                          compute='_compute_totals')
    net_amount = fields.Monetary('Net Amount', currency_field='currency_id', 
                                compute='_compute_totals',
                                help='Positive = amount to receive, Negative = amount to pay')
    currency_id = fields.Many2one(related='settlement_id.company_currency_id', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    @api.depends('settlement_id', 'marketplace_partner_id')
    def _compute_available_vendor_bills(self):
        """Compute available vendor bills for netting"""
        for wizard in self:
            if not wizard.settlement_id or not wizard.marketplace_partner_id:
                wizard.available_vendor_bill_ids = False
                continue
                
            # Find posted vendor bills from the same marketplace partner with outstanding amounts
            # Include bills directly linked to this settlement
            domain = [
                ('move_type', 'in', ['in_invoice', 'in_refund']),
                ('partner_id', '=', wizard.marketplace_partner_id.id),
                ('state', '=', 'posted'),
                ('amount_residual', '>', 0),
                '|',
                ('x_settlement_id', '=', wizard.settlement_id.id),  # Direct link to this settlement
                ('x_settlement_id', '=', False)  # Not linked to any settlement
            ]
            
            available_bills = self.env['account.move'].search(domain)
            wizard.available_vendor_bill_ids = available_bills

    @api.depends('selected_vendor_bill_ids')
    def _compute_totals(self):
        """Compute totals for selected vendor bills"""
        for wizard in self:
            total_bills = sum(bill.amount_residual for bill in wizard.selected_vendor_bill_ids)
            wizard.total_selected_bills = total_bills
            wizard.net_amount = wizard.total_receivables - total_bills

    def action_confirm_netting(self):
        """Confirm netting with selected vendor bills"""
        self.ensure_one()
        
        if not self.selected_vendor_bill_ids:
            raise UserError(_('Please select at least one vendor bill for netting.'))
        
        # Link selected bills to settlement if not already linked
        for bill in self.selected_vendor_bill_ids:
            if not bill.x_settlement_id:
                bill.x_settlement_id = self.settlement_id.id
        
        # Perform the netting
        return self.settlement_id.action_netoff_ar_ap()

    def action_auto_select_bills(self):
        """Auto-select vendor bills up to the receivable amount"""
        self.ensure_one()
        
        if not self.available_vendor_bill_ids:
            raise UserError(_('No vendor bills available for netting.'))
        
        # Sort bills by date (oldest first) and amount (smallest first)
        sorted_bills = self.available_vendor_bill_ids.sorted(
            key=lambda b: (b.invoice_date or b.date, b.amount_residual)
        )
        
        selected_bills = []
        remaining_amount = self.total_receivables
        
        for bill in sorted_bills:
            if remaining_amount <= 0:
                break
            if bill.amount_residual <= remaining_amount:
                selected_bills.append(bill.id)
                remaining_amount -= bill.amount_residual
            elif remaining_amount > 0:
                # Include partial bills if they don't exceed remaining amount significantly
                if bill.amount_residual <= remaining_amount * 1.2:  # 20% tolerance
                    selected_bills.append(bill.id)
                    break
        
        self.selected_vendor_bill_ids = [(6, 0, selected_bills)]

    def action_clear_selection(self):
        """Clear all selected vendor bills"""
        self.ensure_one()
        self.selected_vendor_bill_ids = [(5, 0, 0)]

    @api.model
    def default_get(self, fields_list):
        """Set default values when opening wizard"""
        res = super().default_get(fields_list)
        
        # Get settlement from context
        settlement_id = self.env.context.get('active_id')
        if settlement_id:
            res['settlement_id'] = settlement_id
            
        return res
