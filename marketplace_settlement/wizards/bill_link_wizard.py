from odoo import models, fields, api, _
from odoo.exceptions import UserError


class BillLinkWizard(models.TransientModel):
    _name = 'bill.link.wizard'
    _description = 'Link Vendor Bills to Settlement'

    # Settlement mode (when called from settlement)
    settlement_id = fields.Many2one('marketplace.settlement', string='Settlement')
    
    # Vendor bill mode (when called from vendor bill)
    vendor_bill_id = fields.Many2one('account.move', string='Vendor Bill')
    
    partner_id = fields.Many2one('res.partner', string='Partner', required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    
    # Available bills for selection
    available_bill_ids = fields.Many2many('account.move', 'bill_link_available_rel',
                                         'wizard_id', 'bill_id',
                                         string='Available Vendor Bills',
                                         compute='_compute_available_bills')
    
    # Selected bills (for settlement mode)
    selected_bill_ids = fields.Many2many('account.move', 'bill_link_selected_rel',
                                        'wizard_id', 'bill_id',
                                        string='Selected Vendor Bills',
                                        domain="[('id', 'in', available_bill_ids)]")
    
    # Available settlements (for vendor bill mode)
    available_settlement_ids = fields.Many2many('marketplace.settlement', 'bill_link_settlements_rel',
                                               'wizard_id', 'settlement_id',
                                               string='Available Settlements',
                                               compute='_compute_available_settlements')
    
    # Selected settlement (for vendor bill mode)
    selected_settlement_id = fields.Many2one('marketplace.settlement', 
                                            string='Selected Settlement',
                                            domain="[('id', 'in', available_settlement_ids)]")
    
    # Debug information
    debug_info = fields.Text('Debug Info', compute='_compute_debug_info')
    
    mode = fields.Selection([
        ('settlement', 'Link Bills to Settlement'),
        ('vendor_bill', 'Link Bill to Settlement')
    ], string='Mode', compute='_compute_mode')

    @api.depends('settlement_id', 'vendor_bill_id')
    def _compute_mode(self):
        for wizard in self:
            if wizard.settlement_id:
                wizard.mode = 'settlement'
            elif wizard.vendor_bill_id:
                wizard.mode = 'vendor_bill'
            else:
                wizard.mode = 'settlement'  # default

    @api.depends('partner_id', 'company_id', 'settlement_id')
    def _compute_available_bills(self):
        """Compute available vendor bills for linking"""
        for wizard in self:
            if not wizard.partner_id:
                wizard.available_bill_ids = False
                continue
                
            domain = [
                ('move_type', 'in', ['in_invoice', 'in_refund']),
                ('partner_id', '=', wizard.partner_id.id),
                ('state', '=', 'posted'),
                ('amount_residual', '>', 0),
                ('x_settlement_id', '=', False),  # Not already linked
            ]
            
            if wizard.company_id:
                domain.append(('company_id', '=', wizard.company_id.id))
            
            available_bills = self.env['account.move'].search(domain)
            wizard.available_bill_ids = available_bills

    @api.depends('partner_id', 'company_id', 'vendor_bill_id')
    def _compute_available_settlements(self):
        """Compute available settlements for linking"""
        for wizard in self:
            if not wizard.partner_id:
                wizard.available_settlement_ids = False
                continue
                
            domain = [
                ('marketplace_partner_id', '=', wizard.partner_id.id),
                # Allow draft, confirmed, and posted settlements for linking
                ('state', 'in', ['draft', 'confirmed', 'posted']),
            ]
            
            if wizard.company_id:
                domain.append(('company_id', '=', wizard.company_id.id))
            
            available_settlements = self.env['marketplace.settlement'].search(domain)
            wizard.available_settlement_ids = available_settlements

    @api.depends('partner_id', 'available_settlement_ids', 'mode')
    def _compute_debug_info(self):
        """Compute debug information for troubleshooting"""
        for wizard in self:
            info = []
            info.append(f"Mode: {wizard.mode}")
            info.append(f"Partner: {wizard.partner_id.name if wizard.partner_id else 'None'}")
            info.append(f"Partner ID: {wizard.partner_id.id if wizard.partner_id else 'None'}")
            
            if wizard.mode == 'vendor_bill':
                # Check settlements with this partner
                all_settlements = self.env['marketplace.settlement'].search([
                    ('marketplace_partner_id', '=', wizard.partner_id.id if wizard.partner_id else False)
                ])
                info.append(f"Total settlements with this partner: {len(all_settlements)}")
                
                draft_settlements = all_settlements.filtered(lambda s: s.state in ['draft', 'confirmed', 'posted'])
                info.append(f"Available settlements (draft/confirmed/posted): {len(draft_settlements)}")
                
                info.append("Settlement details:")
                for s in all_settlements[:3]:  # Show first 3
                    info.append(f"  - {s.name} (State: {s.state}, Partner: {s.marketplace_partner_id.name})")
                    
            wizard.debug_info = "\n".join(info)

    def action_link_bills(self):
        """Link selected bills to settlement"""
        self.ensure_one()
        
        if self.mode == 'settlement':
            if not self.settlement_id:
                raise UserError(_('Settlement is required.'))
            
            if not self.selected_bill_ids:
                raise UserError(_('Please select at least one vendor bill to link.'))
            
            # Validate bills
            for bill in self.selected_bill_ids:
                if bill.x_settlement_id:
                    raise UserError(_('Bill %s is already linked to settlement %s.') % 
                                  (bill.name, bill.x_settlement_id.name))
                if bill.partner_id != self.partner_id:
                    raise UserError(_('All bills must be from the same partner.'))
            
            # Link bills to settlement
            self.selected_bill_ids.write({'x_settlement_id': self.settlement_id.id})
            
            return {
                'type': 'ir.actions.act_window',
                'name': _('Settlement'),
                'res_model': 'marketplace.settlement',
                'res_id': self.settlement_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
            
        elif self.mode == 'vendor_bill':
            if not self.vendor_bill_id:
                raise UserError(_('Vendor Bill is required.'))
            
            if not self.selected_settlement_id:
                raise UserError(_('Please select a settlement to link to.'))
            
            # Validate
            if self.vendor_bill_id.x_settlement_id:
                raise UserError(_('This bill is already linked to settlement %s.') % 
                              self.vendor_bill_id.x_settlement_id.name)
            
            # Link bill to settlement
            self.vendor_bill_id.write({'x_settlement_id': self.selected_settlement_id.id})
            
            return {
                'type': 'ir.actions.act_window',
                'name': _('Vendor Bill'),
                'res_model': 'account.move',
                'res_id': self.vendor_bill_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    def action_auto_select_bills(self):
        """Auto-select bills based on amount criteria"""
        self.ensure_one()
        
        if self.mode != 'settlement' or not self.settlement_id:
            return
        
        if not self.available_bill_ids:
            raise UserError(_('No bills available for auto-selection.'))
        
        # Get settlement net amount target
        settlement_amount = self.settlement_id.net_settlement_amount
        
        # Sort bills by date and amount (oldest first, smallest first)
        sorted_bills = self.available_bill_ids.sorted(
            key=lambda b: (b.invoice_date or b.date, b.amount_residual)
        )
        
        selected_bills = []
        remaining_amount = settlement_amount
        
        for bill in sorted_bills:
            if remaining_amount <= 0:
                break
            if bill.amount_residual <= remaining_amount:
                selected_bills.append(bill.id)
                remaining_amount -= bill.amount_residual
            elif remaining_amount > 0:
                # Include bills that don't exceed remaining amount significantly
                if bill.amount_residual <= remaining_amount * 1.2:  # 20% tolerance
                    selected_bills.append(bill.id)
                    break
        
        self.selected_bill_ids = [(6, 0, selected_bills)]

    @api.model
    def default_get(self, fields_list):
        """Set default values when opening wizard"""
        res = super().default_get(fields_list)
        
        # Get context values
        settlement_id = self.env.context.get('default_settlement_id')
        vendor_bill_id = self.env.context.get('default_vendor_bill_id')
        partner_id = self.env.context.get('default_partner_id')
        
        if settlement_id:
            res['settlement_id'] = settlement_id
            settlement = self.env['marketplace.settlement'].browse(settlement_id)
            res['partner_id'] = settlement.marketplace_partner_id.id
            
        elif vendor_bill_id:
            res['vendor_bill_id'] = vendor_bill_id
            bill = self.env['account.move'].browse(vendor_bill_id)
            res['partner_id'] = bill.partner_id.id
            
        elif partner_id:
            res['partner_id'] = partner_id
            
        return res
