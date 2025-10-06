from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountPaymentVoucher(models.Model):
    _name = "account.payment.voucher"
    _description = "AP Payment Voucher (Multi-Vendor with WHT)"
    _order = "date desc, id desc"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Voucher Number", readonly=True, copy=False, default="/")
    date = fields.Date(string="Voucher Date", default=fields.Date.context_today, required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", readonly=True)
    note = fields.Text(string="Note")
    state = fields.Selection([
        ("draft", "Draft"),
        ("confirmed", "Confirmed"),
    ], default="draft", tracking=True)

    line_ids = fields.One2many("account.payment.voucher.line", "voucher_id", string="Lines")

    # Computed fields for totals
    amount_total_gross = fields.Monetary(string="Total Gross", currency_field="currency_id", compute="_compute_amount_totals", store=True)
    amount_total_wht = fields.Monetary(string="Total WHT", currency_field="currency_id", compute="_compute_amount_totals", store=True)
    amount_total_net = fields.Monetary(string="Total Net", currency_field="currency_id", compute="_compute_amount_totals", store=True)

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('buz.account.payment.voucher') or '/'
        if 'date' not in vals or not vals['date']:
            vals['date'] = fields.Date.context_today(self)
        return super().create(vals)

    def write(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('buz.account.payment.voucher') or '/'
        return super().write(vals)

    @api.depends("line_ids.amount_to_pay_gross", "line_ids.wht_amount")
    def _compute_amount_totals(self):
        for voucher in self:
            voucher.amount_total_gross = sum(line.amount_to_pay_gross for line in voucher.line_ids)
            voucher.amount_total_wht = sum(line.wht_amount for line in voucher.line_ids)
            voucher.amount_total_net = sum(line.amount_to_pay_net for line in voucher.line_ids)

    def action_confirm(self):
        """Confirm the voucher and create payments for each vendor"""
        for voucher in self:
            if voucher.state != 'draft':
                continue
                
            # Group lines by partner
            partner_groups = {}
            for line in voucher.line_ids:
                partner_id = line.partner_id.id
                if partner_id not in partner_groups:
                    partner_groups[partner_id] = []
                partner_groups[partner_id].append(line)

            # For each partner, create a single outbound payment
            for partner_id, lines in partner_groups.items():
                partner = self.env['res.partner'].browse(partner_id)
                
                # Calculate total net amount to pay for this partner
                total_net_amount = sum(line.amount_to_pay_net for line in lines)
                
                if total_net_amount <= 0:
                    continue  # Skip if nothing to pay
                
                # Get the default bank journal from configuration
                default_bank_journal = self.env['ir.config_parameter'].sudo().get_param('buz.default_bank_journal_id')
                journal_id = int(default_bank_journal) if default_bank_journal else None
                
                if not journal_id:
                    journal = self.env['account.journal'].search([
                        ('type', 'in', ('bank', 'cash')), 
                        ('company_id', '=', voucher.company_id.id)
                    ], limit=1)
                    if not journal:
                        raise UserError(_("No bank or cash journal found. Please configure the default bank journal in settings."))
                    journal_id = journal.id
                
                # Create outbound payment for this partner
                payment = self.env['account.payment'].create({
                    'payment_type': 'outbound',
                    'partner_type': 'supplier',
                    'partner_id': partner.id,
                    'amount': total_net_amount,
                    'date': voucher.date,
                    'journal_id': journal_id,
                    'ref': f"PV {voucher.name}",
                    'company_id': voucher.company_id.id,
                    'currency_id': voucher.currency_id.id,
                })
                
                # Post the payment
                payment.action_post()
                
                # Get unpaid vendor bills from the lines
                unpaid_bills = self.env['account.move']
                for line in lines:
                    if line.move_id.amount_residual != 0:
                        unpaid_bills |= line.move_id
                
                # Reconcile the payment with the bills
                if unpaid_bills:
                    self._reconcile_payment_with_bills(payment, unpaid_bills)
                
                # Handle WHT if any lines have WHT
                wht_lines = [line for line in lines if line.wht_amount > 0]
                if wht_lines:
                    self._create_wht_entries(wht_lines, payment, partner)
                    
                    # Check if we should auto-generate WHT certificates
                    auto_generate_wht_cert = self.env['ir.config_parameter'].sudo().get_param(
                        'buz.auto_generate_wht_cert', default=True
                    )
                    if auto_generate_wht_cert:
                        self._create_wht_certificates(wht_lines, payment, partner)
                
                # Add payment to chatter
                voucher.message_post(body=_("Payment %s created for vendor %s") % (payment.name, partner.name))

            # Set voucher state to confirmed
            voucher.state = 'confirmed'
        return True

    def _reconcile_payment_with_bills(self, payment, bills):
        """Reconcile the payment with the provided vendor bills"""
        # Get the payment's payable move line
        payment_move_line = payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == 'liability_payable'
        )
        
        if not payment_move_line:
            _logger.warning("No payable line found for payment %s" % payment.name)
            return
        
        # Get the bill move lines that are payable 
        bill_move_lines = self.env['account.move.line']
        for bill in bills:
            bill_move_lines |= bill.line_ids.filtered(
                lambda line: line.account_id.account_type == 'liability_payable'
            )
        # Also include vendor refunds (which have a different account type)
        for bill in bills:
            bill_move_lines |= bill.line_ids.filtered(
                lambda line: line.account_id.account_type == 'asset_receivable'
            )
        
        # Add the payment reconciliation to each bill line
        lines_to_reconcile = (payment_move_line + bill_move_lines).filtered(
            lambda line: line.reconciled is False
        )
        
        # Perform the reconciliation
        if len(lines_to_reconcile) > 1:
            lines_to_reconcile.reconcile()

    def _create_wht_entries(self, wht_lines, payment, partner):
        """Create journal entries for Withholding Tax"""
        # This is a simplified implementation - in a real scenario you'd need to follow 
        # local accounting standards for WHT entries
        wht_total = sum(line.wht_amount for line in wht_lines)
        
        if wht_total <= 0:
            return
            
        # Find WHT payable account (this is a simplified approach)
        # In practice, you'd use specific WHT accounts based on each tax type
        wht_payable_account = self.env['account.account'].search([
            ('code', '=ilike', '%wht%payable%'),  # Simplified search
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not wht_payable_account:
            # If no specific WHT account found, use a fallback account
            wht_payable_account = self.env['account.account'].search([
                ('user_type_id.name', '=', 'Current Liabilities'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            
        if not wht_payable_account:
            _logger.warning("No suitable WHT payable account found, skipping WHT entries")
            return

        # Create a journal entry for WHT
        wht_journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not wht_journal:
            _logger.warning("No general journal found, skipping WHT entries")
            return
            
        wht_entry = self.env['account.move'].create({
            'journal_id': wht_journal.id,
            'date': self.date,
            'ref': f'WHT for PV {self.name}',
            'company_id': self.company_id.id,
        })
        
        # Create WHT entry lines: Debit P&L account, Credit WHT Payable
        for line in wht_lines:
            # Find appropriate expense account to debit for WHT (simplified)
            expense_account = line.move_id.line_ids.filtered(
                lambda l: l.account_id.user_type_id.type in ['expense', 'cogs']
            )[:1].account_id or wht_journal.default_account_id
            
            if not expense_account:
                continue
                
            # Debit expense account for WHT
            self.env['account.move.line'].create({
                'move_id': wht_entry.id,
                'account_id': expense_account.id,
                'debit': line.wht_amount,
                'credit': 0.0,
                'partner_id': partner.id,
                'name': f'WHT for PV {self.name}',
            })
            
            # Credit WHT payable account
            self.env['account.move.line'].create({
                'move_id': wht_entry.id,
                'account_id': wht_payable_account.id,
                'debit': 0.0,
                'credit': line.wht_amount,
                'partner_id': partner.id,
                'name': f'WHT for PV {self.name}',
            })
        
        # Post the WHT journal entry
        wht_entry.action_post()
        
        # Add to chatter
        self.message_post(body=_("WHT journal entry %s created for %.2f") % (wht_entry.name, wht_total))

    def _create_wht_certificates(self, wht_lines, payment, partner):
        """Create WHT certificates if the required module is installed"""
        # Check if the l10n_th_account_wht_cert_form module is installed
        module_installed = self.env['ir.module.module'].search([
            ('name', '=', 'l10n_th_account_wht_cert_form'),
            ('state', '=', 'installed')
        ])
        
        if not module_installed:
            _logger.info("l10n_th_account_wht_cert_form module not installed, skipping WHT certificate creation")
            return
        
        # Create WHT certificates (Thailand-specific implementation)
        try:
            for line in wht_lines:
                if line.wht_amount > 0:
                    # Create WHT certificate
                    wht_cert = self.env['withholding.tax.cert'].create({
                        'payment_id': payment.id,
                        'partner_id': partner.id,
                        'date': self.date,
                        'income_type': '4',  # Example: 4 for services, would depend on actual tax type
                        'base': line.wht_base_amount,
                        'rate': line.wht_rate * 100,  # Convert decimal to percentage
                        'amount': line.wht_amount,
                        'ref_wht_cert_id': line.move_id.id,
                        'company_id': self.company_id.id,
                    })
                    
                    # Add to chatter
                    self.message_post(body=_("WHT Certificate %s created for partner %s") % (wht_cert.name, partner.name))
        except Exception as e:
            _logger.error(f"Error creating WHT certificates: {str(e)}")
            # Don't block the payment process, just log the error

    def action_register_payments(self):
        """Button action to confirm and register payments"""
        return self.action_confirm()
    
    def action_view_payments(self):
        """
        Smart button action to show related payments for this voucher
        """
        self.ensure_one()
        
        # Find payments related to this voucher by looking at the reference
        # Payments are created with ref = f"PV {voucher.name}"
        payments = self.env['account.payment'].search([('ref', 'like', f"PV {self.name}")])
        
        action = {
            'name': _('Payments'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', payments.ids)],
            'context': {'create': False, 'edit': True},
        }
        
        # If there's only one payment, open it directly in form view
        if len(payments) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': payments.id,
            })
        
        return action


class AccountPaymentVoucherLine(models.Model):
    _name = "account.payment.voucher.line"
    _description = "AP Payment Voucher Line"

    voucher_id = fields.Many2one("account.payment.voucher", string="Payment Voucher", required=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", string="Vendor", required=True, domain=[("supplier_rank", ">", 0)])
    move_id = fields.Many2one(
        "account.move", 
        string="Bill/Refund", 
        domain="[('partner_id', '=', partner_id), ('move_type', 'in', ['in_invoice', 'in_refund']), ('state', '=', 'posted')]"
    )
    
    # Monetary fields (using signed fields for correct handling of refunds)
    amount_total_signed = fields.Monetary(string="Total Amount", currency_field="currency_id", related="move_id.amount_total_signed", readonly=True)
    amount_residual_signed = fields.Monetary(string="Residual Amount", currency_field="currency_id", related="move_id.amount_residual_signed", readonly=True)
    
    amount_to_pay_gross = fields.Monetary(
        string="Amount to Pay (Gross)",
        currency_field="currency_id",
        default=lambda self: 0.0,
        help="Gross amount to pay for this bill in the voucher"
    )
    
    # WHT fields (Thailand-specific)
    wht_tax_id = fields.Many2one(
        'account.tax', 
        string="WHT Tax", 
        domain="[('type_tax_use', '=', 'purchase')]"
    )
    wht_base_amount = fields.Monetary(
        string="WHT Base Amount",
        currency_field="currency_id",
        default=lambda self: 0.0,
        help="Base amount for calculating WHT"
    )
    wht_rate = fields.Float(string="WHT Rate", default=0.0, help="WHT rate as a decimal (e.g., 0.03 for 3%)")
    wht_amount = fields.Monetary(string="WHT Amount", currency_field="currency_id", compute="_compute_wht_amount", store=True)
    amount_to_pay_net = fields.Monetary(
        string="Amount to Pay (Net)",
        currency_field="currency_id",
        compute="_compute_amount_to_pay_net",
        store=True,
        help="Net amount after WHT deduction"
    )
    
    currency_id = fields.Many2one(related="voucher_id.currency_id", store=True, readonly=True)

    @api.onchange('move_id')
    def _onchange_move_id(self):
        """Set the default amount to pay equal to the bill's residual amount"""
        if self.move_id:
            # Use signed residual for correct handling of refunds
            self.amount_to_pay_gross = abs(self.move_id.amount_residual_signed)
            # Set WHT base amount to the gross amount by default
            self.wht_base_amount = abs(self.move_id.amount_residual_signed)

    @api.onchange('wht_tax_id')
    def _onchange_wht_tax(self):
        """Update WHT rate when tax is selected"""
        if self.wht_tax_id:
            self.wht_rate = self.wht_tax_id.amount / 100.0  # Convert percentage to decimal
        else:
            self.wht_rate = 0.0

    @api.depends('wht_base_amount', 'wht_rate')
    def _compute_wht_amount(self):
        for line in self:
            line.wht_amount = line.wht_base_amount * line.wht_rate

    @api.depends('amount_to_pay_gross', 'wht_amount')
    def _compute_amount_to_pay_net(self):
        for line in self:
            line.amount_to_pay_net = line.amount_to_pay_gross - line.wht_amount

    @api.constrains('move_id')
    def _check_move_company(self):
        """Ensure bill belongs to the same company as the voucher"""
        for line in self:
            if line.move_id and line.voucher_id:
                if line.move_id.company_id != line.voucher_id.company_id:
                    raise UserError(
                        _("Bill %s belongs to company %s, but voucher is for company %s. "
                          "All bills in a voucher must belong to the same company as the voucher.") % 
                         (line.move_id.name, line.move_id.company_id.name, line.voucher_id.company_id.name)
                    )

    @api.constrains('amount_to_pay_gross', 'wht_base_amount')
    def _check_positive_amounts(self):
        """Ensure amounts are positive"""
        for line in self:
            if line.amount_to_pay_gross < 0:
                raise UserError(_("Amount to pay must be positive"))
            if line.wht_base_amount < 0:
                raise UserError(_("WHT base amount must be positive"))

    @api.constrains('wht_rate')
    def _check_wht_rate(self):
        """Ensure WHT rate is between 0 and 1"""
        for line in self:
            if line.wht_rate < 0 or line.wht_rate > 1:
                raise UserError(_("WHT rate must be between 0 and 1 (e.g., 0.03 for 3%)"))