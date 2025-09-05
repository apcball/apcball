from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_is_zero, float_compare


class MarketplaceFeeAllocation(models.Model):
    _name = 'marketplace.fee.allocation'
    _description = 'Marketplace Fee Allocation Table'
    _order = 'settlement_id desc, invoice_id'
    _rec_name = 'display_name'

    # Links to Settlement and Invoice
    settlement_id = fields.Many2one('marketplace.settlement', string='Settlement', required=True, ondelete='cascade')
    invoice_id = fields.Many2one('account.move', string='Invoice', required=True, 
                                domain="[('move_type', 'in', ['out_invoice', 'out_refund'])]")
    
    # Invoice Information (for reporting convenience)
    invoice_number = fields.Char(related='invoice_id.name', string='Invoice Number', readonly=True, store=True)
    invoice_date = fields.Date(related='invoice_id.invoice_date', string='Invoice Date', readonly=True, store=True)
    invoice_partner_id = fields.Many2one(related='invoice_id.partner_id', string='Customer', readonly=True, store=True)
    invoice_amount_untaxed = fields.Monetary(related='invoice_id.amount_untaxed', string='Invoice Amount (Pre-tax)', 
                                           currency_field='company_currency_id', readonly=True, store=True)
    invoice_amount_total = fields.Monetary(related='invoice_id.amount_total', string='Invoice Total', 
                                         currency_field='company_currency_id', readonly=True, store=True)
    
    # Settlement Information (for form view convenience)
    trade_channel = fields.Selection(related='settlement_id.trade_channel', string='Trade Channel', readonly=True, store=True)
    settlement_date = fields.Date(related='settlement_id.date', string='Settlement Date', readonly=True, store=True)
    settlement_fee_total = fields.Monetary(related='settlement_id.fee_amount', string='Settlement Fee Total', 
                                         currency_field='company_currency_id', readonly=True)
    settlement_vat_total = fields.Monetary(related='settlement_id.vat_on_fee_amount', string='Settlement VAT Total', 
                                         currency_field='company_currency_id', readonly=True)
    settlement_wht_total = fields.Monetary(related='settlement_id.wht_amount', string='Settlement WHT Total', 
                                         currency_field='company_currency_id', readonly=True)
    
    # Allocation Method
    allocation_method = fields.Selection([
        ('proportional', 'Proportional by Pre-tax Amount'),
        ('exact', 'Exact Values from Marketplace CSV')
    ], string='Allocation Method', default='proportional', required=True)
    
    # Base Values for Calculation
    allocation_base_amount = fields.Monetary('Allocation Base Amount', currency_field='company_currency_id',
                                           help='Amount used as base for proportional allocation (usually pre-tax invoice amount)')
    allocation_percentage = fields.Float('Allocation %', digits=(12, 6), compute='_compute_allocation_percentage', store=True,
                                        help='Percentage of total settlement used for this invoice')
    
    # Allocated Amounts
    base_fee_alloc = fields.Monetary('Base Fee Allocated', currency_field='company_currency_id',
                                   help='Marketplace fee allocated to this invoice')
    vat_input_alloc = fields.Monetary('VAT Input Allocated', currency_field='company_currency_id',
                                    help='VAT on fee allocated to this invoice')
    wht_alloc = fields.Monetary('WHT Allocated', currency_field='company_currency_id',
                              help='Withholding tax allocated to this invoice')
    net_payout_alloc = fields.Monetary('Net Payout Allocated', currency_field='company_currency_id',
                                     help='Net amount after deductions allocated to this invoice')
    
    # Totals for verification
    total_deductions_alloc = fields.Monetary('Total Deductions Allocated', currency_field='company_currency_id',
                                           compute='_compute_allocation_totals', store=True,
                                           help='Sum of all deductions allocated to this invoice')
    
    # Company and currency
    company_id = fields.Many2one('res.company', string='Company', compute='_compute_company', readonly=True, store=True)
    company_currency_id = fields.Many2one(related='settlement_id.company_currency_id', string='Currency', readonly=True, store=True)
    
    # Display name
    display_name = fields.Char('Display Name', compute='_compute_display_name', store=True)

    @api.depends('settlement_id.name', 'invoice_id.name')
    def _compute_display_name(self):
        for record in self:
            if record.settlement_id and record.invoice_id:
                record.display_name = f"{record.settlement_id.name} - {record.invoice_id.name}"
            else:
                record.display_name = "New Fee Allocation"

    @api.depends('settlement_id')
    def _compute_company(self):
        for record in self:
            record.company_id = record.settlement_id.journal_id.company_id if record.settlement_id.journal_id else self.env.company

    @api.depends('allocation_base_amount', 'settlement_id.total_invoice_amount')
    def _compute_allocation_percentage(self):
        for record in self:
            if record.settlement_id.total_invoice_amount and not float_is_zero(record.settlement_id.total_invoice_amount, precision_digits=2):
                record.allocation_percentage = (record.allocation_base_amount / record.settlement_id.total_invoice_amount) * 100
            else:
                record.allocation_percentage = 0.0

    @api.depends('base_fee_alloc', 'vat_input_alloc', 'wht_alloc')
    def _compute_allocation_totals(self):
        for record in self:
            record.total_deductions_alloc = (record.base_fee_alloc or 0.0) + (record.vat_input_alloc or 0.0) + (record.wht_alloc or 0.0)

    @api.model
    def create(self, vals):
        # Auto-populate allocation base amount from invoice if not provided
        if not vals.get('allocation_base_amount') and vals.get('invoice_id'):
            invoice = self.env['account.move'].browse(vals['invoice_id'])
            vals['allocation_base_amount'] = invoice.amount_untaxed
        
        return super().create(vals)

    @api.constrains('settlement_id', 'invoice_id')
    def _check_invoice_in_settlement(self):
        """Ensure invoice is part of the settlement"""
        for record in self:
            if record.invoice_id not in record.settlement_id.invoice_ids:
                raise ValidationError(_("Invoice %s is not part of settlement %s") % 
                                    (record.invoice_id.name, record.settlement_id.name))

    @api.constrains('allocation_method', 'base_fee_alloc', 'vat_input_alloc', 'wht_alloc')
    def _check_allocation_values(self):
        """Validate allocation values based on method"""
        for record in self:
            if record.allocation_method == 'exact':
                # For exact method, ensure all values are provided
                if float_is_zero(record.base_fee_alloc + record.vat_input_alloc + record.wht_alloc, precision_digits=2):
                    raise ValidationError(_("For exact allocation method, at least one allocation amount must be provided"))

    def action_allocate_proportional(self):
        """Allocate fees proportionally based on pre-tax amount"""
        self.ensure_one()
        
        if not self.settlement_id.total_invoice_amount or float_is_zero(self.settlement_id.total_invoice_amount, precision_digits=2):
            raise UserError(_("Cannot allocate proportionally: Total invoice amount is zero"))
        
        # Calculate allocation percentage
        allocation_ratio = self.allocation_base_amount / self.settlement_id.total_invoice_amount
        
        # Allocate each type of fee/deduction
        self.write({
            'base_fee_alloc': (self.settlement_id.fee_amount or 0.0) * allocation_ratio,
            'vat_input_alloc': (self.settlement_id.vat_on_fee_amount or 0.0) * allocation_ratio,
            'wht_alloc': (self.settlement_id.wht_amount or 0.0) * allocation_ratio,
            'allocation_method': 'proportional'
        })
        
        # Calculate net payout allocation
        self.net_payout_alloc = self.allocation_base_amount - self.total_deductions_alloc
        
        return True

    def action_set_exact_values(self, base_fee=0.0, vat_input=0.0, wht=0.0):
        """Set exact allocation values (usually from marketplace CSV)"""
        self.ensure_one()
        
        self.write({
            'base_fee_alloc': base_fee,
            'vat_input_alloc': vat_input,
            'wht_alloc': wht,
            'allocation_method': 'exact'
        })
        
        # Calculate net payout allocation
        self.net_payout_alloc = self.allocation_base_amount - self.total_deductions_alloc
        
        return True

    @api.model
    def generate_allocations_for_settlement(self, settlement_id, allocation_method='proportional'):
        """Generate fee allocation records for all invoices in a settlement"""
        settlement = self.env['marketplace.settlement'].browse(settlement_id)
        
        if not settlement:
            raise UserError(_("Settlement not found"))
        
        # Remove existing allocations for this settlement
        existing_allocations = self.search([('settlement_id', '=', settlement_id)])
        existing_allocations.unlink()
        
        allocations = []
        for invoice in settlement.invoice_ids:
            allocation_vals = {
                'settlement_id': settlement_id,
                'invoice_id': invoice.id,
                'allocation_method': allocation_method,
                'allocation_base_amount': invoice.amount_untaxed,
            }
            
            allocation = self.create(allocation_vals)
            
            # If proportional method, calculate allocations immediately
            if allocation_method == 'proportional':
                allocation.action_allocate_proportional()
            
            allocations.append(allocation)
        
        return allocations

    def action_view_invoice(self):
        """Open the related invoice"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_settlement(self):
        """Open the related settlement"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlement'),
            'res_model': 'marketplace.settlement',
            'res_id': self.settlement_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
