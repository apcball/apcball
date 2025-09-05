from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError
from odoo.tools.float_utils import float_is_zero
from odoo.tools import float_compare


class MarketplaceSettlement(models.Model):
    _name = 'marketplace.settlement'
    _description = 'Marketplace Settlement'
    _order = 'date desc, name desc'

    name = fields.Char('Settlement Ref', required=True, default='New', copy=False)
    company_id = fields.Many2one('res.company', string='Company', required=True, 
                                default=lambda self: self.env.company)
    marketplace_partner_id = fields.Many2one('res.partner', string='Marketplace Partner', required=True)
    profile_id = fields.Many2one('marketplace.settlement.profile', string='Profile', 
                                help='Profile used to create this settlement')
    journal_id = fields.Many2one('account.journal', string='Journal', required=True)
    date = fields.Date('Date', required=True, default=fields.Date.context_today)
    invoice_ids = fields.Many2many('account.move', string='Invoices')
    move_id = fields.Many2one('account.move', string='Settlement Move')
    settlement_account_id = fields.Many2one('account.account', string='Settlement Account',
        help='Optional account to post the marketplace aggregate line to. If empty the marketplace partner receivable will be used.')
    # Deduction fields removed - fees should be handled through vendor bills for proper tax documentation
    # This ensures proper VAT recovery and WHT documentation
    company_currency_id = fields.Many2one('res.currency', string='Company Currency', compute='_compute_company_currency')
    trade_channel = fields.Selection([
        ('shopee', 'Shopee'), 
        ('lazada', 'Lazada'), 
        ('nocnoc', 'Noc Noc'), 
        ('tiktok', 'Tiktok'), 
        ('spx', 'SPX'),
        ('other', 'Other')
    ], string='Trade Channel', default='shopee')
    invoice_count = fields.Integer('Invoice Count', compute='_compute_invoice_count')
    total_invoice_amount = fields.Monetary('Total Invoice Amount', currency_field='company_currency_id', compute='_compute_amounts')
    total_deductions = fields.Monetary('Total Deductions', currency_field='company_currency_id', compute='_compute_amounts')
    net_settlement_amount = fields.Monetary('Net Settlement Amount', currency_field='company_currency_id', compute='_compute_amounts')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('reversed', 'Reversed')
    ], string='State', default='draft', compute='_compute_state', store=True)
    is_settled = fields.Boolean('Already Settled', compute='_compute_settlement_status', 
                                help='Indicates if this settlement has been posted and cannot be modified')
    can_modify = fields.Boolean('Can Modify', compute='_compute_settlement_status',
                                help='Indicates if settlement can still be modified')
    
    # AR/AP Netting fields
    vendor_bill_ids = fields.One2many('account.move', 'x_settlement_id',
                                     string='Linked Vendor Bills',
                                     domain="[('move_type', 'in', ['in_invoice', 'in_refund']), ('state', '=', 'posted')]",
                                     help='Vendor bills linked to this settlement for netting')
    # Keep the old field for backward compatibility but make it compute-based
    old_vendor_bill_ids = fields.Many2many('account.move', 'settlement_vendor_bill_rel', 
                                          'settlement_id', 'vendor_bill_id',
                                          string='Related Vendor Bills (Legacy)',
                                          compute='_compute_old_vendor_bill_ids',
                                          help='Legacy field for backward compatibility')
    netting_move_id = fields.Many2one('account.move', string='Netting Move', readonly=True,
                                     help='Journal entry created for AR/AP netting')
    vendor_bill_count = fields.Integer('Vendor Bill Count', compute='_compute_vendor_bill_count')
    total_vendor_bills = fields.Monetary('Total Vendor Bills', currency_field='company_currency_id', 
                                        compute='_compute_amounts')
    net_payout_amount = fields.Monetary('Net Payout Amount', currency_field='company_currency_id', 
                                       compute='_compute_amounts',
                                       help='Final amount to be reconciled against bank statement after netting')
    is_netted = fields.Boolean('AR/AP Netted', compute='_compute_netting_state', store=True,
                              help='Indicates if AR/AP netting has been performed')
    can_perform_netting = fields.Boolean('Can Perform Netting', compute='_compute_netting_state', store=True,
                                        help='Indicates if netting is possible')

    # Fee Allocation fields
    fee_allocation_ids = fields.One2many('marketplace.fee.allocation', 'settlement_id', 
                                        string='Fee Allocations',
                                        help='Fee allocation breakdown per invoice for reporting')
    fee_allocation_count = fields.Integer('Fee Allocation Count', compute='_compute_fee_allocation_count')
    has_fee_allocations = fields.Boolean('Has Fee Allocations', compute='_compute_fee_allocation_state', store=True)
    allocation_method = fields.Selection([
        ('proportional', 'Proportional by Pre-tax Amount'),
        ('exact', 'Exact Values from Marketplace CSV')
    ], string='Default Allocation Method', default='proportional',
       help='Default method for fee allocation calculations')

    # Thai Localization fields
    is_thai_localization_available = fields.Boolean('Thai Localization Available', 
                                                   compute='_compute_thai_localization_available')
    use_thai_wht = fields.Boolean('Use Thai WHT', default=False,
                                 help='Enable Thai withholding tax certificate generation')
    thai_income_tax_form = fields.Selection([
        ('pnd1', 'PND1'),
        ('pnd3', 'PND3'),
        ('pnd53', 'PND53'),
    ], string='Thai Income Tax Form', help='Thai withholding tax form type')
    thai_wht_income_type = fields.Selection([
        ('service', 'Service Income'),
        ('commission', 'Commission'),
        ('rental', 'Rental Income'),
        ('royalty', 'Royalty'),
        ('interest', 'Interest'),
        ('dividend', 'Dividend'),
        ('other', 'Other Income'),
    ], string='Thai WHT Income Type', help='Type of income for Thai withholding tax')
    wht_cert_count = fields.Integer('WHT Cert Count', compute='_compute_wht_cert_count')
    # Use a Text field to store WHT certificate data instead of Many2many to avoid dependency issues
    wht_cert_data = fields.Text('WHT Certificate Data', compute='_compute_wht_cert_data')

    @api.model
    def create(self, vals):
        """Generate sequence for settlement reference"""
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('marketplace.settlement') or 'New'
        return super().create(vals)

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for record in self:
            record.invoice_count = len(record.invoice_ids)

    @api.depends('vendor_bill_ids')
    def _compute_vendor_bill_count(self):
        for record in self:
            record.vendor_bill_count = len(record.vendor_bill_ids)

    @api.depends('vendor_bill_ids')
    def _compute_old_vendor_bill_ids(self):
        """Backward compatibility for the old Many2many field"""
        for record in self:
            record.old_vendor_bill_ids = record.vendor_bill_ids

    @api.depends('fee_allocation_ids')
    def _compute_fee_allocation_count(self):
        for record in self:
            record.fee_allocation_count = len(record.fee_allocation_ids)

    @api.depends('fee_allocation_ids')
    def _compute_fee_allocation_state(self):
        for record in self:
            record.has_fee_allocations = len(record.fee_allocation_ids) > 0

    def _compute_thai_localization_available(self):
        """Check if Thai localization modules are available"""
        for record in self:
            # Check if Thai WHT module is installed
            try:
                if 'marketplace.thai.localization' in self.env:
                    thai_localization = self.env['marketplace.thai.localization'].sudo()
                    record.is_thai_localization_available = thai_localization.is_thai_localization_available()
                else:
                    record.is_thai_localization_available = False
            except KeyError:
                record.is_thai_localization_available = False

    def _compute_wht_cert_count(self):
        """Compute count of related WHT certificates"""
        for record in self:
            if not record.is_thai_localization_available:
                record.wht_cert_count = 0
                continue
                
            # Try to count WHT certificates if module is available
            wht_cert_model = self.env.get('withholding.tax.cert', None)
            if not wht_cert_model:
                record.wht_cert_count = 0
                continue
                
            # Count certificates for this settlement's vendor and period
            domain = [
                ('partner_id', '=', record.marketplace_partner_id.id if record.marketplace_partner_id else False),
                ('date', '>=', record.date),
                ('date', '<=', record.date),
            ]
            
            # If settlement has move_id, also filter by invoice
            if record.move_id:
                domain.append(('move_id', '=', record.move_id.id))
                
            record.wht_cert_count = wht_cert_model.search_count(domain)

    def _compute_wht_cert_data(self):
        """Compute related WHT certificate data as text"""
        for record in self:
            if not record.is_thai_localization_available:
                record.wht_cert_data = ""
                continue
                
            # Try to find WHT certificates if module is available
            wht_cert_model = self.env.get('withholding.tax.cert', None)
            if not wht_cert_model:
                record.wht_cert_data = ""
                continue
                
            # Find certificates for this settlement's vendor and period
            domain = [
                ('partner_id', '=', record.marketplace_partner_id.id if record.marketplace_partner_id else False),
                ('date', '>=', record.date),
                ('date', '<=', record.date),
            ]
            
            # If settlement has move_id, also filter by invoice
            if record.move_id:
                domain.append(('move_id', '=', record.move_id.id))
                
            certs = wht_cert_model.search(domain)
            if certs:
                cert_data = []
                for cert in certs:
                    cert_info = f"Certificate: {cert.name or cert.id}, Amount: {cert.amount or 0}"
                    cert_data.append(cert_info)
                record.wht_cert_data = "\n".join(cert_data)
            else:
                record.wht_cert_data = ""

    @api.onchange('marketplace_partner_id')
    def _onchange_marketplace_partner_id(self):
        """Set Thai WHT defaults from partner configuration"""
        if self.marketplace_partner_id:
            # Set Thai localization defaults if available
            if hasattr(self.marketplace_partner_id, 'is_thai_wht_enabled'):
                self.use_thai_wht = getattr(self.marketplace_partner_id, 'is_thai_wht_enabled', False)
            
            if hasattr(self.marketplace_partner_id, 'default_thai_income_tax_form'):
                if self.marketplace_partner_id.default_thai_income_tax_form:
                    self.thai_income_tax_form = self.marketplace_partner_id.default_thai_income_tax_form
            
            if hasattr(self.marketplace_partner_id, 'default_thai_wht_income_type'):
                if self.marketplace_partner_id.default_thai_wht_income_type:
                    self.thai_wht_income_type = self.marketplace_partner_id.default_thai_wht_income_type

    @api.constrains('invoice_ids')
    def _check_invoice_constraints(self):
        """Validate invoice constraints for settlement"""
        for record in self:
            if not record.invoice_ids:
                continue
                
            # Check 1: All invoices must be from the same company
            companies = record.invoice_ids.mapped('company_id')
            if len(companies) > 1:
                raise UserError(_(
                    'All invoices in a settlement must belong to the same company.\n'
                    'Found invoices from companies: %s'
                ) % ', '.join(companies.mapped('name')))
            
            # Check 2: Ideally same currency (warning for mixed currencies)
            currencies = record.invoice_ids.mapped('currency_id')
            if len(currencies) > 1:
                # This is a warning, not a hard constraint
                pass  # Could add a warning mechanism here
            
            # Check 3: Prevent selecting already settled invoices
            already_settled_invoices = []
            for invoice in record.invoice_ids:
                # Check if invoice is already in another posted settlement
                other_settlements = self.env['marketplace.settlement'].search([
                    ('id', '!=', record.id),
                    ('invoice_ids', 'in', invoice.id),
                    ('state', '=', 'posted')
                ])
                if other_settlements:
                    already_settled_invoices.append({
                        'invoice': invoice.name,
                        'settlement': other_settlements[0].name
                    })
            
            if already_settled_invoices:
                error_msg = _('The following invoices are already settled:\n')
                for item in already_settled_invoices:
                    error_msg += _('• Invoice %s in Settlement %s\n') % (item['invoice'], item['settlement'])
                raise UserError(error_msg)

    @api.constrains('marketplace_partner_id')
    def _check_marketplace_partner_accounts(self):
        """Ensure marketplace partner has proper accounts configured"""
        for record in self:
            if not record.marketplace_partner_id:
                continue
            
            partner = record.marketplace_partner_id
            missing_accounts = []
            
            # Check receivable account
            if not partner.property_account_receivable_id:
                missing_accounts.append('Receivable Account')
            
            # Check payable account
            if not partner.property_account_payable_id:
                missing_accounts.append('Payable Account')
            
            if missing_accounts:
                raise UserError(_(
                    'Marketplace Partner "%s" is missing the following required accounts:\n%s\n\n'
                    'Please configure these accounts in the partner\'s Accounting tab.'
                ) % (partner.name, '\n'.join('• ' + acc for acc in missing_accounts)))

    @api.depends('invoice_ids', 'vendor_bill_ids')
    def _compute_amounts(self):
        for record in self:
            total_invoice = 0.0
            for inv in record.invoice_ids:
                # For fee allocation purposes, use total amount not residual
                # This ensures fee allocation works even after settlement reconciliation
                if inv.move_type == 'out_refund':
                    total_invoice -= abs(inv.amount_total)
                else:
                    total_invoice += abs(inv.amount_total)
            
            # Calculate total vendor bills
            total_vendor_bills = 0.0
            for bill in record.vendor_bill_ids:
                if bill.state == 'posted':
                    total_vendor_bills += abs(bill.amount_residual)
            
            record.total_invoice_amount = total_invoice
            record.total_vendor_bills = total_vendor_bills
            record.total_deductions = 0.0  # No deductions in settlement - these are in vendor bills
            record.net_settlement_amount = total_invoice  # Full invoice amount
            # Net payout is settlement amount minus vendor bills (after netting)
            record.net_payout_amount = record.net_settlement_amount - total_vendor_bills

    @api.depends('move_id', 'netting_move_id', 'vendor_bill_ids', 'state')
    def _compute_netting_state(self):
        for record in self:
            # Can perform netting if settlement is posted and has vendor bills
            record.can_perform_netting = (
                record.state == 'posted' and 
                len(record.vendor_bill_ids.filtered(lambda b: b.state == 'posted' and b.amount_residual > 0)) > 0 and 
                not record.netting_move_id
            )
            # Is netted if netting move exists and is posted
            record.is_netted = bool(record.netting_move_id and record.netting_move_id.state == 'posted')

    def _compute_company_currency(self):
        for rec in self:
            rec.company_currency_id = rec.env.company.currency_id

    @api.depends('move_id')
    def _compute_state(self):
        for record in self:
            if not record.move_id:
                record.state = 'draft'
            elif record.move_id.state == 'posted':
                # Check if there's a reverse move
                reverse_moves = self.env['account.move'].search([
                    ('reversed_entry_id', '=', record.move_id.id),
                    ('state', '=', 'posted')
                ])
                if reverse_moves:
                    record.state = 'reversed'
                else:
                    record.state = 'posted'
            else:
                record.state = 'draft'

    @api.depends('state', 'move_id')
    def _compute_settlement_status(self):
        for record in self:
            record.is_settled = record.state == 'posted'
            record.can_modify = record.state in ['draft', 'reversed']

    def action_view_invoices(self):
        """Open related invoices"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlement Invoices'),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
            'context': {'default_trade_channel': self.trade_channel},
        }

    def action_view_settlement_move(self):
        """Open settlement move"""
        self.ensure_one()
        if not self.move_id:
            return None
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlement Move'),
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
        }

    def action_create_settlement(self):
        self.ensure_one()
        
        # Security check: Only accounting groups can post settlements
        if not self.env.user.has_group('account.group_account_user'):
            raise AccessError(_('Only Accounting users can post settlements. Please contact your administrator.'))
        
        # Check if settlement is already created
        if self.move_id:
            return self._open_settlement_move_with_banner()
        
        # Prevent modification of posted settlements
        if self.state == 'posted':
            raise UserError(_('Posted settlements cannot be modified. Please reverse the settlement first.'))
            
        if not self.invoice_ids:
            raise UserError(_('Please select invoices to settle.'))

        # Additional validation for currency consistency (warning)
        currencies = self.invoice_ids.mapped('currency_id')
        if len(currencies) > 1:
            # Show warning but allow posting
            currency_names = ', '.join(currencies.mapped('name'))
            # You might want to show a confirmation dialog here
            # For now, we'll log the warning
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning('Settlement %s contains invoices with multiple currencies: %s', 
                          self.name, currency_names)

        # Remove deduction validation - fees now handled through vendor bills
        # This ensures proper VAT documentation and WHT certificates through vendor bills

        # Create the settlement move
        move = self._create_settlement_move()
        self.move_id = move.id

        # Return action to open the settlement move with banner
        return self._open_settlement_move_with_banner()

    def action_preview_settlement(self):
        """Preview settlement before posting"""
        self.ensure_one()
        
        if self.move_id:
            raise UserError(_('Settlement has already been created.'))
            
        if not self.invoice_ids:
            raise UserError(_('Please select invoices to settle.'))

        # Calculate preview totals
        preview_data = self._calculate_settlement_preview()
        
        # Return wizard with preview data
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlement Preview'),
            'res_model': 'marketplace.settlement.preview.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_settlement_id': self.id,
                'default_preview_data': preview_data,
            },
        }

    def _calculate_settlement_preview(self):
        """Calculate settlement preview data"""
        self.ensure_one()
        
        # Calculate invoice totals
        total_invoice_amount = 0.0
        invoice_details = []
        
        for inv in self.invoice_ids:
            residual = inv.amount_residual
            sign = 1 if inv.move_type != 'out_refund' else -1
            amount = residual * sign
            
            total_invoice_amount += amount
            invoice_details.append({
                'invoice_name': inv.name,
                'partner_name': inv.partner_id.name,
                'amount': amount,
                'currency_id': inv.currency_id.id or self.company_currency_id.id,
            })
        
        # Calculate deductions
        fee_amount = self.fee_amount or 0.0
        vat_amount = self.vat_on_fee_amount or 0.0
        wht_amount = self.wht_amount or 0.0
        total_deductions = fee_amount + vat_amount + wht_amount
        
        # Calculate net settlement
        net_settlement = total_invoice_amount - total_deductions
        
        return {
            'total_invoice_amount': total_invoice_amount,
            'fee_amount': fee_amount,
            'vat_amount': vat_amount,
            'wht_amount': wht_amount,
            'total_deductions': total_deductions,
            'net_settlement': net_settlement,
            'invoice_details': invoice_details,
            'currency_symbol': self.company_currency_id.symbol,
        }

    def _create_settlement_move(self):
        """Create the settlement journal entry - simplified without deductions"""
        self.ensure_one()

        # Remove deduction validation - fees handled through vendor bills

        # prepare move lines
        lines = []
        total_amount = 0.0
        currency = self.invoice_ids[0].currency_id

        # helper to detect receivable account across Odoo versions
        def _is_receivable_account(account):
            if not account:
                return False
            # new style: account.user_type_id.type == 'receivable'
            if hasattr(account, 'user_type_id') and getattr(account.user_type_id, 'type', False):
                return account.user_type_id.type == 'receivable'
            # fallback: account.internal_type == 'receivable'
            if hasattr(account, 'internal_type'):
                return account.internal_type == 'receivable'
            # fallback: account.account_type_id.internal_type
            if hasattr(account, 'account_type_id') and getattr(account.account_type_id, 'internal_type', False):
                return account.account_type_id.internal_type == 'receivable'
            return False

        # Determine aggregate account for settlement:
        mp_account = self.settlement_account_id or getattr(self.journal_id, 'default_account_id', False) or self.marketplace_partner_id.property_account_receivable_id
        if not mp_account:
            raise UserError(_('Please configure a settlement account.'))

        # Prevent posting the marketplace aggregate to a receivable account by mistake.
        if _is_receivable_account(mp_account):
            raise UserError(_(
                'The settlement aggregate account (%s) is a receivable account.\n'
                'Please choose a bank/liquidity account as the settlement account.'
            ) % (mp_account.name,))

        for inv in self.invoice_ids:
            if inv.state != 'posted':
                raise UserError(_('Invoice %s must be posted.') % inv.name)
            # compute residual amount (amount due)
            residual = inv.amount_residual
            # support refunds (credit notes) with negative residual
            sign = 1
            if inv.move_type == 'out_refund':
                sign = -1
            amt = residual * sign
            if not float_is_zero(amt, precision_digits=2):
                total_amount += amt
                # credit/debit to customer's receivable
                cust_account = inv.partner_id.property_account_receivable_id
                if not cust_account:
                    raise UserError(_('Customer %s must have receivable account.') % inv.partner_id.name)
                # create line for that customer's receivable (reverse of invoice residual)
                lines.append((0, 0, {
                    'name': inv.name + ' - settlement',
                    'account_id': cust_account.id,
                    'partner_id': inv.partner_id.id,
                    'credit': amt if amt > 0 else 0.0,
                    'debit': -amt if amt < 0 else 0.0,
                }))

        # No deduction lines - these are now handled through vendor bills
        # This ensures proper VAT recovery and WHT documentation

        # marketplace aggregate line (direct settlement amount without deductions)
        if total_amount == 0.0:
            raise UserError(_('Total settlement amount is zero.'))

        lines.append((0, 0, {
            'name': self.name,
            'account_id': mp_account.id,
            'partner_id': self.marketplace_partner_id.id,
            'debit': total_amount if total_amount > 0 else 0.0,
            'credit': -total_amount if total_amount < 0 else 0.0,
        }))

        move_vals = {
            'ref': self.name,
            'journal_id': self.journal_id.id,
            'date': self.date,
            'line_ids': lines,
        }
        move = self.env['account.move'].create(move_vals)
        # use action_post() to post moves
        if hasattr(move, 'action_post'):
            move.action_post()
        elif hasattr(move, 'post'):
            move.post()

        # Reconcile invoices
        self._reconcile_invoices(move)
        
        return move

    def _reconcile_invoices(self, move):
        """Reconcile invoices with settlement move"""
        for inv in self.invoice_ids:
            # find invoice receivable line
            inv_rec_line = inv.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled)
            if not inv_rec_line:
                continue
            # find settlement move line for this customer
            settle_line = move.line_ids.filtered(lambda l: l.partner_id == inv.partner_id and l.account_id.account_type == 'asset_receivable')
            if settle_line:
                # reconcile
                (inv_rec_line + settle_line).reconcile()

    def _open_settlement_move_with_banner(self):
        """Open settlement move with reconciliation banner"""
        self.ensure_one()
        
        if not self.move_id:
            raise UserError(_('No settlement move found.'))
        
        # Create context with banner message
        banner_message = _(
            "Settlement created successfully! "
            "To automate fee deductions in future settlements, "
            "configure Reconciliation Models for marketplace fees."
        )
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlement Move'),
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'settlement_banner_message': banner_message,
                'show_reconciliation_models_link': True,
                'settlement_id': self.id,
            },
            'flags': {
                'action_buttons': True,
                'sidebar': True,
            },
        }

    def action_reverse_settlement(self):
        """Reverse the settlement move and update settlement state"""
        self.ensure_one()
        
        if not self.move_id:
            raise UserError(_('No settlement move to reverse.'))
            
        if self.state not in ['posted']:
            raise UserError(_('Can only reverse posted settlements.'))
            
        # Create reverse move
        reverse_move = self.move_id._reverse_moves([{
            'ref': _('Reverse of %s') % self.move_id.ref,
            'date': fields.Date.context_today(self),
        }])
        
        if reverse_move:
            # Post the reverse move
            reverse_move.action_post()
            
            # Clear the settlement link to allow recreation (using sudo to bypass write restrictions)
            old_move_id = self.move_id.id
            self.sudo().write({'move_id': False})
            
            # Return action to show both moves
            return {
                'type': 'ir.actions.act_window',
                'name': _('Settlement Reversed'),
                'res_model': 'account.move',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', [old_move_id, reverse_move.id])],
                'context': {
                    'default_ref': self.name,
                },
                'help': _(
                    '<p>Settlement has been reversed.</p>'
                    '<p>You can now create a new settlement with correct data.</p>'
                ),
            }
        else:
            raise UserError(_('Failed to create reverse move.'))

    def action_view_vendor_bills(self):
        """Open related vendor bills"""
        if not self.vendor_bill_ids:
            return {}
            
        return {
            'name': _('Vendor Bills'),
            'type': 'ir.actions.act_window',
            'res_model': 'marketplace.vendor.bill',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.vendor_bill_ids.ids)],
            'context': {
                'default_settlement_id': self.id,
                'default_vendor_id': self.marketplace_partner_id.id,
            }
        }

    def action_view_wht_certificates(self):
        """Open related WHT certificates - only if Thai localization is available"""
        if not self.is_thai_localization_available:
            return {}
        
        # Try to find WHT certificates through Thai localization module
        wht_cert_model = self.env.get('withholding.tax.cert', None)
        if not wht_cert_model:
            return {}
            
        # Look for WHT certificates related to this settlement's vendor and period
        domain = [
            ('partner_id', '=', self.marketplace_partner_id.id),
            ('date', '>=', self.date),
            ('date', '<=', self.date),
        ]
        
        # If settlement has move_id, also filter by invoice
        if self.move_id:
            domain.append(('move_id', '=', self.move_id.id))
        
        return {
            'name': _('WHT Certificates'),
            'type': 'ir.actions.act_window',
            'res_model': 'withholding.tax.cert',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {
                'default_partner_id': self.marketplace_partner_id.id,
                'default_date': self.date,
            }
        }

    def action_create_wht_certificate(self):
        """Create WHT certificate through Thai localization helper"""
        if not self.is_thai_localization_available or not self.use_thai_wht:
            return {}
        
        # Use the Thai localization helper to create certificate
        thai_localization = self.env['marketplace.thai.localization'].sudo()
        return thai_localization.create_thai_wht_certificate(
            settlement_id=self.id,
            partner_id=self.marketplace_partner_id.id,
            wht_amount=self.wht_amount,
            income_tax_form=self.thai_income_tax_form,
            wht_income_type=self.thai_wht_income_type,
            invoice_move_id=self.move_id.id if self.move_id else False
        )

    def action_view_netting_move(self):
        """Open netting move"""
        self.ensure_one()
        if not self.netting_move_id:
            return None
        return {
            'type': 'ir.actions.act_window',
            'name': _('Netting Move'),
            'res_model': 'account.move',
            'res_id': self.netting_move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_link_vendor_bills(self):
        """Open wizard to link vendor bills to this settlement"""
        self.ensure_one()
        
        if self.state != 'draft':
            raise UserError(_('Can only link vendor bills to draft settlements.'))
            
        return {
            'type': 'ir.actions.act_window',
            'name': _('Link Vendor Bills'),
            'res_model': 'bill.link.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_settlement_id': self.id,
                'default_partner_id': self.marketplace_partner_id.id,
            },
        }

    def action_view_vendor_bills(self):
        """View linked vendor bills"""
        self.ensure_one()
        
        if not self.vendor_bill_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Vendor Bills'),
                    'message': _('No vendor bills are linked to this settlement.'),
                    'type': 'info',
                }
            }
        
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Linked Vendor Bills'),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.vendor_bill_ids.ids)],
            'context': {
                'default_move_type': 'in_invoice',
                'default_partner_id': self.marketplace_partner_id.id,
            },
        }
        
        if len(self.vendor_bill_ids) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': self.vendor_bill_ids[0].id,
            })
        
        return action

    def action_netoff_ap_ar_preview(self):
        """Preview AR/AP netting amounts before performing netting"""
        self.ensure_one()
        
        if not self.move_id:
            raise UserError(_('Settlement must be posted before previewing netting.'))
        
        if self.state != 'posted':
            raise UserError(_('Can only preview netting on posted settlements.'))
            
        if not self.vendor_bill_ids:
            raise UserError(_('No vendor bills linked for netting.'))
        
        # Calculate amounts that would be netted
        marketplace_partner = self.marketplace_partner_id
        
        # Helper function to check account types (more comprehensive)
        def _get_account_type(account):
            if hasattr(account, 'account_type'):
                return account.account_type
            elif hasattr(account, 'user_type_id') and hasattr(account.user_type_id, 'type'):
                return account.user_type_id.type
            elif hasattr(account, 'internal_type'):
                return account.internal_type
            return None

        def _is_receivable_account(account):
            account_type = _get_account_type(account)
            return account_type in ['asset_receivable', 'receivable']

        def _is_payable_account(account):
            account_type = _get_account_type(account)
            return account_type in ['liability_payable', 'payable']

        # Calculate receivables from settlement 
        # For marketplace settlements, the receivable amount is typically the settlement account line (marketplace partner line)
        # Look for marketplace partner lines that represent the amount we should receive
        marketplace_settlement_lines = self.move_id.line_ids.filtered(
            lambda l: l.partner_id == marketplace_partner and l.debit > 0
        )
        
        # Alternative: Also check if there's a direct receivable line for marketplace partner
        settlement_receivable_lines = self.move_id.line_ids.filtered(
            lambda l: l.partner_id == marketplace_partner and 
            _is_receivable_account(l.account_id)
        )
        
        # Calculate total receivable amount (marketplace owes us)
        total_receivable_amount = 0.0
        
        # First try: Use marketplace partner debit lines (settlement amount)
        total_receivable_amount += sum(line.debit for line in marketplace_settlement_lines if line.debit > 0)
        
        # Second try: Use actual receivable lines if any
        total_receivable_amount += sum(line.debit for line in settlement_receivable_lines if line.debit > 0)
        
        # If still no receivable amount and settlement has net amount, use that
        if total_receivable_amount == 0 and self.net_settlement_amount > 0:
            total_receivable_amount = self.net_settlement_amount
        
        # Calculate payables from vendor bills (unreconciled only for netting)
        total_payable_amount = 0.0
        for bill in self.vendor_bill_ids:
            bill_payable_lines = bill.line_ids.filtered(
                lambda l: l.partner_id == marketplace_partner and 
                _is_payable_account(l.account_id) and
                not l.reconciled
            )
            total_payable_amount += sum(line.credit for line in bill_payable_lines if line.credit > 0)
        
        net_amount = total_receivable_amount - total_payable_amount
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('AR/AP Netting Preview'),
            'res_model': 'settlement.preview.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_settlement_id': self.id,
                'default_total_receivables': total_receivable_amount,
                'default_total_payables': total_payable_amount,
                'default_net_amount': net_amount,
                'default_currency_id': self.company_currency_id.id,
            },
        }
        return {
            'type': 'ir.actions.act_window',
            'name': _('AR/AP Netting Move'),
            'res_model': 'account.move',
            'res_id': self.netting_move_id.id,
            'view_mode': 'form',
        }

    def action_open_netting_wizard(self):
        """Open AR/AP netting wizard"""
        self.ensure_one()
        
        if not self.move_id:
            raise UserError(_('Settlement must be posted before performing netting.'))
        
        if self.state != 'posted':
            raise UserError(_('Can only perform netting on posted settlements.'))
            
        if self.netting_move_id:
            raise UserError(_('AR/AP netting has already been performed for this settlement.'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('AR/AP Netting'),
            'res_model': 'marketplace.netting.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_settlement_id': self.id,
            },
        }

    def action_netoff_ar_ap(self):
        """Perform AR/AP netting reconciliation"""
        self.ensure_one()
        
        # Validations
        if not self.move_id:
            raise UserError(_('Settlement must be posted before performing netting.'))
        
        if self.state != 'posted':
            raise UserError(_('Can only perform netting on posted settlements.'))
            
        if not self.vendor_bill_ids:
            raise UserError(_('No vendor bills selected for netting.'))
            
        if self.netting_move_id:
            raise UserError(_('AR/AP netting has already been performed for this settlement.'))
        
        # Check all vendor bills are posted
        unposted_bills = self.vendor_bill_ids.filtered(lambda b: b.state != 'posted')
        if unposted_bills:
            raise UserError(_('All vendor bills must be posted before netting. Unposted bills: %s') % 
                          ', '.join(unposted_bills.mapped('name')))

        return self._create_netting_move()

    def _create_netting_move(self):
        """Create journal entry for AR/AP netting"""
        self.ensure_one()
        
        # Get marketplace partner
        marketplace_partner = self.marketplace_partner_id
        
        # Prepare move lines
        netting_lines = []
        total_receivable_amount = 0.0
        total_payable_amount = 0.0
        
        # Helper function to check account types
        def _get_account_type(account):
            if hasattr(account, 'account_type'):
                return account.account_type
            elif hasattr(account, 'user_type_id') and hasattr(account.user_type_id, 'type'):
                return account.user_type_id.type
            elif hasattr(account, 'internal_type'):
                return account.internal_type
            return None

        # Process receivables from settlement move (marketplace partner receivable)
        settlement_receivable_lines = self.move_id.line_ids.filtered(
            lambda l: l.partner_id == marketplace_partner and 
            _get_account_type(l.account_id) in ['asset_receivable', 'receivable'] and
            not l.reconciled
        )
        
        for line in settlement_receivable_lines:
            if line.debit > 0:  # Marketplace owes us
                total_receivable_amount += line.debit
                netting_lines.append((0, 0, {
                    'name': f'Net-off AR: {line.name}',
                    'account_id': line.account_id.id,
                    'partner_id': marketplace_partner.id,
                    'credit': line.debit,  # Reverse the debit
                    'debit': 0.0,
                }))

        # Process payables from vendor bills (marketplace partner payable)
        for bill in self.vendor_bill_ids:
            bill_payable_lines = bill.line_ids.filtered(
                lambda l: l.partner_id == marketplace_partner and 
                _get_account_type(l.account_id) in ['liability_payable', 'payable'] and
                not l.reconciled
            )
            
            for line in bill_payable_lines:
                if line.credit > 0:  # We owe marketplace
                    total_payable_amount += line.credit
                    netting_lines.append((0, 0, {
                        'name': f'Net-off AP: {line.name}',
                        'account_id': line.account_id.id,
                        'partner_id': marketplace_partner.id,
                        'debit': line.credit,  # Reverse the credit
                        'credit': 0.0,
                    }))

        # Calculate net amount
        net_amount = total_receivable_amount - total_payable_amount
        
        if float_is_zero(net_amount, precision_digits=2):
            # Perfect netting - no additional line needed
            pass
        else:
            # Net amount goes to marketplace partner account
            marketplace_account = (self.settlement_account_id or 
                                 marketplace_partner.property_account_receivable_id)
            
            netting_lines.append((0, 0, {
                'name': f'Net Amount - {self.name}',
                'account_id': marketplace_account.id,
                'partner_id': marketplace_partner.id,
                'debit': net_amount if net_amount > 0 else 0.0,
                'credit': -net_amount if net_amount < 0 else 0.0,
            }))

        if not netting_lines:
            raise UserError(_('No lines to net. Please check that there are unreconciled receivables and payables.'))

        # Create netting move
        netting_move_vals = {
            'ref': f'AR/AP Netting - {self.name}',
            'journal_id': self.journal_id.id,
            'date': fields.Date.context_today(self),
            'line_ids': netting_lines,
        }
        
        netting_move = self.env['account.move'].create(netting_move_vals)
        
        # Post the netting move
        if hasattr(netting_move, 'action_post'):
            netting_move.action_post()
        elif hasattr(netting_move, 'post'):
            netting_move.post()
        
        # Link netting move to settlement using sudo to bypass read-only restrictions
        try:
            self.sudo().write({'netting_move_id': netting_move.id})
        except Exception as e:
            # If we can't write to settlement (e.g., it's posted), 
            # still perform reconciliation but don't link the move
            # The move will exist and can be found by reference
            pass
        
        # Perform reconciliation
        self._reconcile_netted_amounts(netting_move)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('AR/AP Netting Move'),
            'res_model': 'account.move',
            'res_id': netting_move.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _reconcile_netted_amounts(self, netting_move):
        """Reconcile the netted amounts between original moves and netting move"""
        self.ensure_one()
        
        def _get_account_type(account):
            if hasattr(account, 'account_type'):
                return account.account_type
            elif hasattr(account, 'user_type_id') and hasattr(account.user_type_id, 'type'):
                return account.user_type_id.type
            elif hasattr(account, 'internal_type'):
                return account.internal_type
            return None
        
        marketplace_partner = self.marketplace_partner_id
        
        # Reconcile receivables (settlement move lines with netting move lines)
        settlement_receivable_lines = self.move_id.line_ids.filtered(
            lambda l: l.partner_id == marketplace_partner and 
            _get_account_type(l.account_id) in ['asset_receivable', 'receivable'] and
            not l.reconciled
        )
        
        netting_receivable_lines = netting_move.line_ids.filtered(
            lambda l: l.partner_id == marketplace_partner and 
            _get_account_type(l.account_id) in ['asset_receivable', 'receivable'] and
            l.credit > 0  # These are the offsetting credits
        )
        
        # Group by account for reconciliation
        accounts_to_reconcile = {}
        
        # Add settlement lines
        for line in settlement_receivable_lines:
            if line.account_id not in accounts_to_reconcile:
                accounts_to_reconcile[line.account_id] = []
            accounts_to_reconcile[line.account_id].append(line)
        
        # Add netting lines
        for line in netting_receivable_lines:
            if line.account_id not in accounts_to_reconcile:
                accounts_to_reconcile[line.account_id] = []
            accounts_to_reconcile[line.account_id].append(line)
        
        # Reconcile by account
        for account, lines in accounts_to_reconcile.items():
            unreconciled_lines = [l for l in lines if not l.reconciled]
            if len(unreconciled_lines) > 1:
                try:
                    self.env['account.move.line'].browse([l.id for l in unreconciled_lines]).reconcile()
                except Exception as e:
                    # Continue with other reconciliations if one fails
                    pass
        
        # Reconcile payables (vendor bill lines with netting move lines)
        for bill in self.vendor_bill_ids:
            bill_payable_lines = bill.line_ids.filtered(
                lambda l: l.partner_id == marketplace_partner and 
                _get_account_type(l.account_id) in ['liability_payable', 'payable'] and
                not l.reconciled
            )
            
            for bill_line in bill_payable_lines:
                # Find corresponding netting line
                netting_payable_lines = netting_move.line_ids.filtered(
                    lambda l: l.partner_id == marketplace_partner and 
                    l.account_id == bill_line.account_id and
                    l.debit > 0 and  # These are the offsetting debits
                    not l.reconciled
                )
                
                if netting_payable_lines:
                    try:
                        (bill_line + netting_payable_lines[0]).reconcile()
                    except Exception as e:
                        # Continue with other reconciliations if one fails
                        pass

    def action_reverse_netting(self):
        """Reverse the AR/AP netting"""
        self.ensure_one()
        
        if not self.netting_move_id:
            raise UserError(_('No netting move to reverse.'))
            
        if not self.is_netted:
            raise UserError(_('Netting move is not posted.'))
        
        # Create reverse move
        reverse_move = self.netting_move_id._reverse_moves([{
            'ref': f'Reverse AR/AP Netting - {self.name}',
            'date': fields.Date.context_today(self),
        }])
        
        if reverse_move:
            # Post the reverse move
            reverse_move.action_post()
            
            # Clear the netting link
            old_netting_move_id = self.netting_move_id.id
            self.netting_move_id = False
            
            return {
                'type': 'ir.actions.act_window',
                'name': _('Netting Reversed'),
                'res_model': 'account.move',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', [old_netting_move_id, reverse_move.id])],
                'context': {
                    'default_ref': f'Netting - {self.name}',
                },
            }
        else:
            raise UserError(_('Failed to create reverse netting move.'))

    # Fee Allocation Methods
    def action_generate_fee_allocations(self):
        """Generate fee allocation records for all invoices in this settlement"""
        self.ensure_one()
        
        if not self.invoice_ids:
            raise UserError(_("No invoices found in this settlement to allocate fees."))
        
        # Use the fee allocation model's method to generate allocations
        FeeAllocation = self.env['marketplace.fee.allocation']
        allocations = FeeAllocation.generate_allocations_for_settlement(
            self.id, 
            self.allocation_method
        )
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fee Allocations Generated'),
            'res_model': 'marketplace.fee.allocation',
            'view_mode': 'tree,form',
            'domain': [('settlement_id', '=', self.id)],
            'context': {
                'default_settlement_id': self.id,
            },
        }

    def action_view_fee_allocations(self):
        """View fee allocation records for this settlement"""
        self.ensure_one()
        
        action = self.env.ref('marketplace_settlement.action_marketplace_fee_allocation').read()[0]
        action['domain'] = [('settlement_id', '=', self.id)]
        action['context'] = {
            'default_settlement_id': self.id,
            'default_allocation_method': self.allocation_method,
        }
        
        if self.fee_allocation_count == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.fee_allocation_ids[0].id
        
        return action

    def action_import_fee_allocations_csv(self):
        """Open CSV import wizard for fee allocations"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Import Fee Allocations',
            'res_model': 'marketplace.fee.allocation.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_settlement_id': self.id},
        }

    def action_recalculate_fee_allocations(self):
        """Recalculate all fee allocations for this settlement"""
        self.ensure_one()
        
        if not self.fee_allocation_ids:
            raise UserError(_("No fee allocations found to recalculate. Generate allocations first."))
        
        for allocation in self.fee_allocation_ids:
            if allocation.allocation_method == 'proportional':
                allocation.action_allocate_proportional()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Fee allocations have been recalculated.'),
                'type': 'success',
            }
        }

    def action_clear_fee_allocations(self):
        """Clear all fee allocation records for this settlement"""
        self.ensure_one()
        
        if not self.fee_allocation_ids:
            raise UserError(_("No fee allocations found to clear."))
        
        self.fee_allocation_ids.unlink()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Fee allocations have been cleared.'),
                'type': 'success',
            }
        }

    def get_fee_allocation_summary(self):
        """Get summary of fee allocations for reporting"""
        self.ensure_one()
        
        summary = {
            'total_base_fee_allocated': sum(self.fee_allocation_ids.mapped('base_fee_alloc')),
            'total_vat_input_allocated': sum(self.fee_allocation_ids.mapped('vat_input_alloc')),
            'total_wht_allocated': sum(self.fee_allocation_ids.mapped('wht_alloc')),
            'total_net_payout_allocated': sum(self.fee_allocation_ids.mapped('net_payout_alloc')),
            'allocation_count': len(self.fee_allocation_ids),
            'allocation_methods': list(set(self.fee_allocation_ids.mapped('allocation_method'))),
        }
        
        # Validation - check if allocations match settlement totals
        precision = self.env['decimal.precision'].precision_get('Account')
        summary['allocations_match'] = (
            float_compare(summary['total_base_fee_allocated'], self.fee_amount or 0.0, precision_digits=precision) == 0 and
            float_compare(summary['total_vat_input_allocated'], self.vat_on_fee_amount or 0.0, precision_digits=precision) == 0 and
            float_compare(summary['total_wht_allocated'], self.wht_amount or 0.0, precision_digits=precision) == 0
        )
        
        return summary

    def write(self, vals):
        """Override write to prevent modification of posted settlements"""
        for record in self:
            if record.state == 'posted' and not record.can_modify:
                # Allow some fields to be updated even when posted (like computed fields)
                allowed_fields = {
                    'state', 'is_settled', 'can_modify', 'invoice_count', 'vendor_bill_count',
                    'fee_allocation_count', 'total_invoice_amount', 'total_deductions', 
                    'net_settlement_amount', 'total_vendor_bills', 'net_payout_amount',
                    'is_netted', 'can_perform_netting', 'has_fee_allocations'
                }
                
                # Special case: allow move_id to be set to False (reversal operation)
                if 'move_id' in vals and vals['move_id'] is False:
                    allowed_fields.add('move_id')
                
                restricted_fields = set(vals.keys()) - allowed_fields
                if restricted_fields:
                    raise UserError(_(
                        'Posted settlements cannot be modified. The following fields are read-only:\n%s\n\n'
                        'To make changes, please reverse the settlement first.'
                    ) % ', '.join(restricted_fields))
        
        return super().write(vals)

    def unlink(self):
        """Override unlink to prevent deletion of posted settlements"""
        for record in self:
            if record.state == 'posted':
                raise UserError(_(
                    'Posted settlement "%s" cannot be deleted. '
                    'Please reverse the settlement first if you need to remove it.'
                ) % record.name)
        return super().unlink()

    def action_view_move(self):
        """Open the settlement move"""
        self.ensure_one()
        if not self.move_id:
            raise UserError(_('No settlement move found'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlement Move'),
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_invoices(self):
        """Open the list of invoices"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlement Invoices'),
            'res_model': 'account.move',
            'domain': [('id', 'in', self.invoice_ids.ids)],
            'view_mode': 'tree,form',
            'target': 'current',
        }

    def action_view_vendor_bills(self):
        """Open the list of linked vendor bills"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Linked Vendor Bills'),
            'res_model': 'account.move',
            'domain': [('id', 'in', self.vendor_bill_ids.ids)],
            'view_mode': 'tree,form',
            'target': 'current',
        }

    def action_view_fee_allocations(self):
        """Open the fee allocations"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fee Allocations'),
            'res_model': 'marketplace.fee.allocation',
            'domain': [('settlement_id', '=', self.id)],
            'view_mode': 'tree,form',
            'target': 'current',
            'context': {'default_settlement_id': self.id}
        }


class AccountMoveExtension(models.Model):
    """Extend account.move to support marketplace settlement linking"""
    _inherit = 'account.move'
    
    x_settlement_id = fields.Many2one('marketplace.settlement', string='Linked Settlement',
                                     help='Marketplace settlement linked to this vendor bill for AR/AP netting',
                                     index=True)
