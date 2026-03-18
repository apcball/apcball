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
    
    # Fee allocation now works with vendor bills instead of settlement deductions
    settlement_fee_total = fields.Monetary('Settlement Fee Total', currency_field='company_currency_id', 
                                         compute='_compute_settlement_totals', readonly=True,
                                         help='Total fees from linked vendor bills')
    settlement_vat_total = fields.Monetary('Settlement VAT Total', currency_field='company_currency_id', 
                                         compute='_compute_settlement_totals', readonly=True,
                                         help='Total VAT from linked vendor bills')
    settlement_wht_total = fields.Monetary('Settlement WHT Total', currency_field='company_currency_id', 
                                         compute='_compute_settlement_totals', readonly=True,
                                         help='Total WHT from linked vendor bills')
    
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

    @api.depends('settlement_id', 'settlement_id.vendor_bill_ids', 
                 'settlement_id.vendor_bill_ids.state',
                 'settlement_id.vendor_bill_ids.amount_untaxed',
                 'settlement_id.vendor_bill_ids.line_ids')
    def _compute_settlement_totals(self):
        """Compute settlement totals from linked vendor bills instead of settlement deductions"""
        import logging
        _logger = logging.getLogger(__name__)
        
        for record in self:
            total_fee = 0.0
            total_vat = 0.0 
            total_wht = 0.0
            
            if not record.settlement_id:
                record.settlement_fee_total = total_fee
                record.settlement_vat_total = total_vat
                record.settlement_wht_total = total_wht
                continue
            
            _logger.info(f"=== Computing settlement totals for {record.settlement_id.name} ===")
            _logger.info(f"Number of vendor bills: {len(record.settlement_id.vendor_bill_ids)}")
            
            # Calculate totals from linked vendor bills
            for bill in record.settlement_id.vendor_bill_ids:
                _logger.info(f"Processing bill: {bill.name}, State: {bill.state}")
                if bill.state == 'posted':
                    # Base fee amount (without tax)
                    bill_fee = bill.amount_untaxed or 0.0
                    total_fee += bill_fee
                    _logger.info(f"  Bill amount_untaxed: {bill_fee}")
                    
                    # Calculate VAT and WHT from tax lines
                    vat_amount = 0.0
                    wht_amount = 0.0
                    
                    # Method 1: Check invoice tax lines (more accurate)
                    _logger.info(f"  Checking {len(bill.invoice_line_ids)} invoice lines")
                    for tax_line in bill.invoice_line_ids:
                        _logger.info(f"    Line: {tax_line.name}, Price: {tax_line.price_subtotal}, Taxes: {[tax.name for tax in tax_line.tax_ids]}")
                        for tax in tax_line.tax_ids:
                            # Calculate tax amount for this line
                            tax_amount = (tax_line.price_subtotal * tax.amount) / 100
                            _logger.info(f"      Tax: {tax.name}, Rate: {tax.amount}%, Amount: {tax_amount}")
                            
                            if tax.amount > 0:  # VAT (positive rate)
                                vat_amount += tax_amount
                            elif tax.amount < 0:  # WHT (negative rate)
                                wht_amount += abs(tax_amount)
                    
                    # Method 2: Check move lines for tax amounts (fallback)
                    if vat_amount == 0.0 and wht_amount == 0.0:
                        _logger.info(f"  Fallback: Checking {len(bill.line_ids)} move lines")
                        for line in bill.line_ids:
                            if line.tax_line_id:
                                line_amount = abs(line.debit - line.credit)
                                _logger.info(f"    Tax line: {line.tax_line_id.name}, Rate: {line.tax_line_id.amount}%, Amount: {line_amount}")
                                if line.tax_line_id.amount > 0:  # VAT
                                    vat_amount += line_amount
                                elif line.tax_line_id.amount < 0:  # WHT
                                    wht_amount += line_amount
                    
                    total_vat += vat_amount
                    total_wht += wht_amount
                    _logger.info(f"  Bill totals - VAT: {vat_amount}, WHT: {wht_amount}")
            
            record.settlement_fee_total = total_fee
            record.settlement_vat_total = total_vat  
            record.settlement_wht_total = total_wht
            
            _logger.info(f"Final totals - Fee: {total_fee}, VAT: {total_vat}, WHT: {total_wht}")
            _logger.info("=== End settlement totals computation ===")  

    @api.depends('settlement_id')
    def _compute_company(self):
        for record in self:
            record.company_id = record.settlement_id.journal_id.company_id if record.settlement_id.journal_id else self.env.company

    @api.depends('allocation_base_amount', 'settlement_id.total_invoice_amount')
    def _compute_allocation_percentage(self):
        for record in self:
            total_invoice = record.settlement_id.total_invoice_amount
            base_amount = record.allocation_base_amount or 0.0
            
            # Use higher precision for percentage calculation to avoid rounding issues
            if total_invoice and not float_is_zero(total_invoice, precision_digits=2):
                record.allocation_percentage = (base_amount / total_invoice) * 100.0
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
            if not record.settlement_id or not record.invoice_id:
                continue  # Skip validation if required fields are not yet set
                
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
        
        # Debug: Check settlement amounts
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"=== Fee Allocation Debug ===")
        _logger.info(f"Settlement: {self.settlement_id.name}")
        _logger.info(f"Invoice: {self.invoice_id.name}")
        _logger.info(f"Allocation Base Amount: {self.allocation_base_amount}")
        _logger.info(f"Settlement Fee Total (from vendor bills): {self.settlement_fee_total}")
        _logger.info(f"Settlement VAT Total (from vendor bills): {self.settlement_vat_total}")
        _logger.info(f"Settlement WHT Total (from vendor bills): {self.settlement_wht_total}")
        _logger.info(f"Settlement Total Invoice Amount: {self.settlement_id.total_invoice_amount}")
        
        # Use total invoice amount, but with fallback for edge cases
        settlement_total = self.settlement_id.total_invoice_amount
        
        # Fallback: If total_invoice_amount is zero, try to calculate from original amounts
        if not settlement_total or float_is_zero(settlement_total, precision_digits=2):
            settlement_total = 0.0
            for inv in self.settlement_id.invoice_ids:
                if inv.move_type == 'out_refund':
                    settlement_total -= abs(inv.amount_untaxed)
                else:
                    settlement_total += abs(inv.amount_untaxed)
            _logger.info(f"Calculated settlement total from invoices: {settlement_total}")
        
        # Final check
        if not settlement_total or float_is_zero(settlement_total, precision_digits=2):
            raise UserError(_("Cannot allocate proportionally: Settlement has no invoices or total amount is zero. "
                            "Please ensure the settlement contains posted invoices with amounts greater than zero."))
        
        # Calculate allocation percentage
        allocation_ratio = self.allocation_base_amount / settlement_total
        _logger.info(f"Allocation ratio: {allocation_ratio} ({self.allocation_base_amount} / {settlement_total})")
        
        # Calculate allocated amounts from vendor bill totals instead of settlement deductions
        base_fee_alloc = (self.settlement_fee_total or 0.0) * allocation_ratio
        vat_input_alloc = (self.settlement_vat_total or 0.0) * allocation_ratio
        wht_alloc = (self.settlement_wht_total or 0.0) * allocation_ratio
        
        _logger.info(f"Calculated allocations:")
        _logger.info(f"  Base Fee: {base_fee_alloc}")
        _logger.info(f"  VAT Input: {vat_input_alloc}")
        _logger.info(f"  WHT: {wht_alloc}")
        
        # Allocate each type of fee/deduction
        self.write({
            'base_fee_alloc': base_fee_alloc,
            'vat_input_alloc': vat_input_alloc,
            'wht_alloc': wht_alloc,
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
