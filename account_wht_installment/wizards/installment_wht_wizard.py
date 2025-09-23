# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class WHTInstallmentPaymentWizard(models.TransientModel):
    _name = "wht.installment.payment.wizard"
    _description = "Installment Payment with WHT (TH)"

    move_id = fields.Many2one("account.move", required=True, readonly=True, string="Vendor Bill")
    partner_id = fields.Many2one("res.partner", required=True, readonly=True)
    date = fields.Date(string="Payment Date", default=fields.Date.context_today, required=True)
    journal_id = fields.Many2one(
        "account.journal",
        string="Bank/Cash Journal",
        required=True,
        domain="[('type', 'in', ('bank','cash'))]",
    )
    amount_to_clear = fields.Monetary(string="Amount to clear (gross)", required=True)
    currency_id = fields.Many2one(related="move_id.currency_id", store=False, readonly=True)
    company_id = fields.Many2one(related="move_id.company_id", store=False, readonly=True)

    wht_percent = fields.Float(string="WHT %", default=lambda self: float(self.env["ir.config_parameter"].sudo().get_param("account_wht_installment.default_wht_percent", "3.0")))
    wht_amount = fields.Monetary(string="WHT amount", compute="_compute_amounts", store=False)
    bank_charge = fields.Monetary(string="Bank charges", default=0.0, help="ค่าธรรมเนียมธนาคาร (ถ้ามี)")
    net_pay_amount = fields.Monetary(string="Net pay (bank)", compute="_compute_amounts", store=False)
    
    # WHT Certificate fields
    wht_tax_id = fields.Many2one(
        "account.withholding.tax",
        string="Withholding Tax",
        help="Select the withholding tax to be applied. This will create withholding tax moves and certificate."
    )
    wht_cert_income_type = fields.Selection(
        selection=[
            ("1", "1. เงินเดือน ค่าจ้าง ฯลฯ 40(1)"),
            ("2", "2. ค่าธรรมเนียม ค่านายหน้า ฯลฯ 40(2)"),
            ("3", "3. ค่าแห่งลิขสิทธิ์ ฯลฯ 40(3)"),
            ("4A", "4. ดอกเบี้ย ฯลฯ 40(4)ก"),
            ("5", "5. ค่าจ้างทำของ ค่าบริการ ค่าเช่า ค่าขนส่ง ฯลฯ 3 เตรส"),
            ("6", "6. อื่นๆ (ระบุ)"),
        ],
        string="Type of Income",
        default="5",
        help="Type of income for WHT certificate"
    )

    memo = fields.Char(string="Memo/Ref")
    
    # VAT option selection
    include_vat = fields.Boolean(
        string="Include VAT calculation", 
        default=False,
        help="Check this box to include VAT calculation for this partial payment"
    )
    vat_rate = fields.Float(
        string="VAT Rate (%)", 
        default=7.0,
        help="VAT rate percentage"
    )
    manual_vat_account_id = fields.Many2one(
        "account.account", 
        string="VAT Account",
        help="Select account for recording VAT"
    )
    
    # VAT fields for partial payment calculation
    bill_has_vat = fields.Boolean(string="Bill has VAT", compute="_compute_bill_vat_info", store=False)
    bill_vat_amount = fields.Monetary(string="Total VAT on Bill", compute="_compute_bill_vat_info", store=False)
    bill_amount_untaxed = fields.Monetary(string="Bill Amount (ex VAT)", compute="_compute_bill_vat_info", store=False)
    payment_percentage = fields.Float(string="Payment %", compute="_compute_payment_percentage", store=False)
    proportional_vat_amount = fields.Monetary(string="Proportional VAT", compute="_compute_proportional_vat", store=False)
    vat_account_id = fields.Many2one("account.account", string="VAT Account", compute="_compute_vat_account", store=False)
    
    @api.depends("move_id")
    def _compute_bill_vat_info(self):
        """Calculate VAT information from the original bill"""
        for w in self:
            _logger.info("🔍 Computing bill VAT info for move_id: %s", w.move_id.id if w.move_id else "None")
            # Check if VAT on partial payment is enabled
            vat_enabled = w.env["ir.config_parameter"].sudo().get_param(
                "account_wht_installment.enable_vat_on_partial_payment", "True"
            ).lower() == "true"
            _logger.info("🔍 VAT enabled: %s", vat_enabled)
            
            if w.move_id and vat_enabled:
                # Debug logging
                _logger.info("=== VAT DEBUG INFO ===")
                _logger.info("Bill ID: %s, Name: %s", w.move_id.id, w.move_id.name)
                
                # Find VAT tax lines (typically 7% VAT in Thailand)
                all_tax_lines = w.move_id.line_ids.filtered(lambda l: l.tax_line_id)
                for line in all_tax_lines:
                    _logger.info("Tax line: account=%s, tax=%s, amount=%s, type=%s, debit=%s, credit=%s", 
                                line.account_id.name, line.tax_line_id.name, 
                                line.tax_line_id.amount, line.tax_line_id.type_tax_use,
                                line.debit, line.credit)
                
                vat_lines = w.move_id.line_ids.filtered(
                    lambda l: l.tax_line_id and (
                        # Standard 7% purchase VAT - check both positive and negative amounts
                        (l.tax_line_id.amount == 7.0 and l.tax_line_id.type_tax_use == 'purchase') or
                        # VAT with name containing "VAT" or "ภาษีมูลค่าเพิ่ม" and 7%
                        (l.tax_line_id.amount == 7.0 and (
                            'vat' in (l.tax_line_id.name or '').lower() or
                            'ภาษีมูลค่าเพิ่ม' in (l.tax_line_id.name or '') or
                            'ภาษี 7%' in (l.tax_line_id.name or '') or
                            'ภาษีซื้อ' in (l.tax_line_id.name or '')
                        )) or
                        # Account name contains VAT-related terms (for manual VAT entries)
                        (l.tax_line_id and l.tax_line_id.amount == 7.0 and (
                            'vat' in (l.account_id.name or '').lower() or
                            'ภาษีมูลค่าเพิ่ม' in (l.account_id.name or '') or
                            'ภาษีซื้อ' in (l.account_id.name or '')
                        ))
                    )
                )
                
                _logger.info("🔍 Found %d VAT lines", len(vat_lines))
                for vat_line in vat_lines:
                    _logger.info("🔍 VAT line: %s, balance=%s, debit=%s, credit=%s", 
                                vat_line.account_id.name, vat_line.balance, vat_line.debit, vat_line.credit)
                
                if vat_lines:
                    w.bill_has_vat = True
                    # VAT amount should be absolute value (positive for input VAT)
                    w.bill_vat_amount = abs(sum(vat_lines.mapped('balance')))
                    w.bill_amount_untaxed = w.move_id.amount_untaxed
                    _logger.info("✅ VAT detected: amount=%s", w.bill_vat_amount)
                else:
                    w.bill_has_vat = False
                    w.bill_vat_amount = 0.0
                    w.bill_amount_untaxed = w.move_id.amount_untaxed
                    _logger.info("No VAT detected")
            else:
                w.bill_has_vat = False
                w.bill_vat_amount = 0.0
                w.bill_amount_untaxed = 0.0
    
    @api.depends("amount_to_clear", "move_id.amount_total")
    def _compute_payment_percentage(self):
        """Calculate what percentage of the total bill we're paying"""
        for w in self:
            _logger.info("🔍 Computing payment percentage: amount_to_clear=%s, amount_total=%s", 
                        w.amount_to_clear, w.move_id.amount_total if w.move_id else "None")
            if w.move_id and w.move_id.amount_total > 0:
                w.payment_percentage = (w.amount_to_clear / w.move_id.amount_total) * 100
                _logger.info("✅ Payment percentage: %s%%", w.payment_percentage)
            else:
                w.payment_percentage = 0.0
                _logger.info("❌ Payment percentage set to 0")
    
    @api.depends("amount_to_clear", "include_vat", "vat_rate")
    def _compute_proportional_vat(self):
        """Calculate VAT amount based on payment amount and VAT rate"""
        for w in self:
            _logger.info("🔍 Computing VAT: include_vat=%s, amount_to_clear=%s, vat_rate=%s", 
                        w.include_vat, w.amount_to_clear, w.vat_rate)
            
            if w.include_vat and w.amount_to_clear > 0 and w.vat_rate > 0:
                # Calculate VAT from base amount (partial payment amount)
                base_amount = w.amount_to_clear
                vat_amount = (base_amount * w.vat_rate) / 100
                w.proportional_vat_amount = vat_amount
                _logger.info("✅ VAT calculated: base=%s, rate=%s%%, VAT=%s", 
                            base_amount, w.vat_rate, vat_amount)
            else:
                w.proportional_vat_amount = 0.0
                _logger.info("❌ VAT not calculated")
    
    @api.depends("manual_vat_account_id", "include_vat")
    def _compute_vat_account(self):
        """Use manually selected VAT account"""
        for w in self:
            if w.include_vat and w.manual_vat_account_id:
                w.vat_account_id = w.manual_vat_account_id
            else:
                w.vat_account_id = False

    @api.depends("amount_to_clear", "wht_percent", "bank_charge", "proportional_vat_amount")
    def _compute_amounts(self):
        for w in self:
            gross = w.amount_to_clear or 0.0
            rate = max(w.wht_percent or 0.0, 0.0) / 100.0
            bank_charge = w.bank_charge or 0.0
            vat_amt = w.proportional_vat_amount or 0.0
            
            w.wht_amount = round(gross * rate, 2)
            
            # For bills with VAT, the net payment calculation is:
            # Net payment = gross amount - WHT - bank charges
            # (VAT is handled as a separate debit entry, not affecting cash flow)
            w.net_pay_amount = gross - w.wht_amount - bank_charge

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        """Auto-fill WHT tax based on partner's default settings"""
        if self.partner_id:
            # Check if partner has default WHT tax
            if hasattr(self.partner_id, 'supplier_wht_tax_id') and self.partner_id.supplier_wht_tax_id:
                self.wht_tax_id = self.partner_id.supplier_wht_tax_id
            elif hasattr(self.partner_id, 'supplier_company_wht_tax_id') and self.partner_id.supplier_company_wht_tax_id:
                self.wht_tax_id = self.partner_id.supplier_company_wht_tax_id
                
    @api.onchange("wht_tax_id")
    def _onchange_wht_tax_id(self):
        """Auto-fill WHT income type and percent based on selected tax"""
        if self.wht_tax_id:
            if self.wht_tax_id.wht_cert_income_type:
                self.wht_cert_income_type = self.wht_tax_id.wht_cert_income_type
            if self.wht_tax_id.amount:
                self.wht_percent = self.wht_tax_id.amount

    def action_confirm(self):
        from odoo import _  # Re-import _ to avoid conflicts with logging
        self.ensure_one()
        bill = self.move_id.with_company(self.company_id.id)
        if bill.state != "posted" or bill.move_type not in ("in_invoice", "in_refund"):
            raise UserError(_("Wizard can be used only on posted Vendor Bills/CNs."))
        if bill.amount_residual <= 0:
            raise UserError(_("Nothing to clear; the bill is already fully paid."))
            
        # Debug: Log all lines in the bill to see what's available
        _logger.info("🔍 === BILL LINES DEBUG ===")
        _logger.info("Bill: %s, Total: %s", bill.name, bill.amount_total)
        for line in bill.line_ids:
            _logger.info("📄 Line: account=%s, tax_line=%s, tax_ids=%s, balance=%s", 
                        line.account_id.name, 
                        line.tax_line_id.name if line.tax_line_id else None,
                        [f"{t.name}({t.amount}%)" for t in line.tax_ids], 
                        line.balance)
        _logger.info("🔍 === END BILL LINES DEBUG ===")

        # Basic validations
        if self.amount_to_clear <= 0:
            raise UserError(_("Amount to clear must be > 0"))
        if self.amount_to_clear > abs(bill.amount_residual):
            raise UserError(_("Amount to clear exceeds residual."))
        if not self.journal_id.default_account_id:
            raise UserError(_("Selected journal is missing Bank/Cash account."))
        if self.bank_charge < 0:
            raise UserError(_("Bank charges cannot be negative."))
        if self.net_pay_amount < 0:
            raise UserError(_("Net payment amount cannot be negative. Please reduce WHT percentage or bank charges."))
        if self.wht_percent < 0 or self.wht_percent > 100:
            raise UserError(_("WHT percentage must be between 0 and 100."))

        # Config: WHT Payable account
        wht_acc_param = self.env["ir.config_parameter"].sudo().get_param("account_wht_installment.wht_payable_account_id")
        if not wht_acc_param:
            raise UserError(_("Please set 'WHT Payable Account (TH)' in Accounting Settings."))
        wht_account = self.env["account.account"].browse(int(wht_acc_param))
        if not wht_account.exists():
            raise UserError(_("Configured WHT account not found."))

        # Config: Bank Charge account (if bank charges > 0)
        bank_charge_account = None
        if self.bank_charge > 0:
            bank_charge_acc_param = self.env["ir.config_parameter"].sudo().get_param("account_wht_installment.bank_charge_account_id")
            if not bank_charge_acc_param:
                raise UserError(_("Please set 'Bank Charge Account' in Accounting Settings."))
            bank_charge_account = self.env["account.account"].browse(int(bank_charge_acc_param))
            if not bank_charge_account.exists():
                raise UserError(_("Configured Bank Charge account not found."))

        company = bill.company_id
        company_currency = company.currency_id
        currency = bill.currency_id

        # Amounts are assumed in company currency when posting; for simplicity assume same currency
        gross = self.amount_to_clear
        wht_amt = self.wht_amount
        bank_charge_amt = self.bank_charge or 0.0
        net_amt = self.net_pay_amount

        if any(v < 0 for v in (gross, wht_amt, bank_charge_amt, net_amt)):
            raise UserError(_("Computed amounts are invalid."))

        # Helper to detect payable-like accounts (Odoo 17 may use 'liability' or account_type internals)
        def _is_payable_account(acc):
            if not acc:
                return False
            
            # Check account_type for Odoo 17+ (this is the modern way)
            if hasattr(acc, 'account_type') and acc.account_type:
                # In Odoo 17, payable accounts typically have account_type like 'liability_payable'
                if 'payable' in str(acc.account_type).lower():
                    return True
                # Also check for current liability types that might be payable
                if str(acc.account_type).lower() in ('liability_current', 'liability_payable'):
                    return True
            
            # Legacy: direct attribute on account (older modules)
            if hasattr(acc, 'internal_type') and acc.internal_type in ('payable', 'liability'):
                return True
                
            # Check user_type_id (middle versions of Odoo)
            if hasattr(acc, 'user_type_id') and acc.user_type_id:
                user_type_name = getattr(acc.user_type_id, 'name', '').lower()
                if 'payable' in user_type_name or 'creditor' in user_type_name:
                    return True
                    
            # new account type relation (some Odoo 17 setups)
            if hasattr(acc, 'account_type_id') and getattr(acc.account_type_id, 'internal_type', False) in ('payable', 'liability'):
                return True
                
            # fallback to internal_group (e.g., 'liabilities')
            if getattr(acc, 'internal_group', False) in ('liabilities', 'payable'):
                return True
                
            return False

        # Find the payable account/line on the bill to debit
        # In a vendor bill, the payable line should have credit > 0 (liability increase)
        payable_lines = bill.line_ids.filtered(
            lambda l: _is_payable_account(l.account_id) and not l.reconciled and l.credit > 0
        )
        
        # Debug logging to see what the helper detects
        _logger.info("=== DEBUGGING PAYABLE ACCOUNT DETECTION ===")
        for line in bill.line_ids:
            is_payable = _is_payable_account(line.account_id)
            account_type = getattr(line.account_id, 'account_type', 'N/A')
            user_type = getattr(getattr(line.account_id, 'user_type_id', None), 'name', 'N/A')
            _logger.info("Line %s: account=%s(id=%s), account_type=%s, user_type=%s, is_payable=%s, reconciled=%s, debit=%s, credit=%s", 
                        line.id, line.account_id.name, line.account_id.id, account_type, user_type, 
                        is_payable, line.reconciled, line.debit, line.credit)
        
        payable_line = payable_lines[:1]
        if not payable_line:
            # Build diagnostics to help troubleshooting which lines exist on the bill
            details = []
            for l in bill.line_ids:
                acct = l.account_id
                acct_name = acct.name or ''
                acct_id = acct.id or ''
                # Get more detailed account information for debugging
                account_type = getattr(acct, 'account_type', 'N/A')
                user_type = getattr(getattr(acct, 'user_type_id', None), 'name', 'N/A')
                acct_internal = getattr(acct, 'internal_type', False) or (hasattr(acct, 'account_type_id') and getattr(acct.account_type_id, 'internal_type', False)) or getattr(acct, 'internal_group', False)
                is_payable = _is_payable_account(acct)
                details.append(
                    "Line(id=%s): account=%s(id=%s), account_type=%s, user_type=%s, internal_type=%s, is_payable=%s, debit=%s, credit=%s, reconciled=%s" % (
                        l.id, acct_name, acct_id, account_type, user_type, acct_internal, is_payable,
                        float(l.debit or 0.0), float(l.credit or 0.0), bool(l.reconciled)
                    )
                )
            raise UserError(_(
                "Cannot find a payable line on the bill to reconcile against. Please check the vendor bill lines.\n\nFound lines:\n%s" % ("\n".join(details))
            ))
        payable_account_id = payable_line.account_id.id

        # Check if we need to handle VAT for partial payment
        vat_amt = self.proportional_vat_amount or 0.0
        
        # Debug logging for VAT calculation
        _logger.info("💰 === VAT PAYMENT DEBUG ===")
        _logger.info("💰 Bill has VAT: %s", self.bill_has_vat)
        _logger.info("💰 VAT amount: %s", vat_amt)
        _logger.info("💰 VAT account: %s", self.vat_account_id.name if self.vat_account_id else "None")
        _logger.info("💰 Gross amount: %s", gross)
        _logger.info("💰 WHT amount: %s", wht_amt)
        _logger.info("💰 Bank charges: %s", bank_charge_amt)
        
        # Adjust amounts if VAT is involved
        # For partial payments with VAT, we need to:
        # 1. Dr AP (gross + proportional VAT) - to reduce the total payable including VAT
        # 2. Cr Bank (gross - WHT) - actual payment (bank charges are handled separately)
        # 3. Cr WHT (if applicable)
        # 4. Dr VAT Input (proportional VAT) - to claim VAT
        if vat_amt > 0 and self.vat_account_id and self.include_vat:
            # AP debit should be just the gross amount (VAT is separate)
            adjusted_gross = gross
            # Bank payment: to balance the journal entry properly
            # Total debits = AP + VAT + Bank Charges = 200 + 13.08 + 20 = 233.08
            # Total credits should equal total debits
            # Bank credit + WHT credit = 233.08
            # Bank credit = 233.08 - WHT = 233.08 - 6 = 227.08
            bank_payment_amount = adjusted_gross + vat_amt + bank_charge_amt - wht_amt
            _logger.info("💰 With VAT: AP debit=%s, VAT debit=%s, Bank Charges=%s, Bank credit=%s (to balance)", 
                        adjusted_gross, vat_amt, bank_charge_amt, bank_payment_amount)
        else:
            adjusted_gross = gross
            # Bank payment: gross + bank charges - WHT (to balance)
            bank_payment_amount = gross + bank_charge_amt - wht_amt
            _logger.info("💰 Without VAT: AP debit=%s, Bank Charges=%s, Bank credit=%s (to balance)", 
                        adjusted_gross, bank_charge_amt, bank_payment_amount)
        
        _logger.info("Adjusted gross: %s", adjusted_gross)
        _logger.info("Bank payment amount: %s", bank_payment_amount)

        # Main JE: Dr AP gross, Cr Bank (net payment), Cr WHT, Dr VAT (if applicable)
        move_lines = [
            (0, 0, {
                "name": _("Installment clearance for %s") % (bill.name or bill.ref or ""),
                "account_id": payable_account_id,
                "partner_id": bill.partner_id.id,
                "debit": adjusted_gross if adjusted_gross > 0 else 0.0,
                "credit": 0.0,
            }),
            (0, 0, {
                "name": _("Bank payment"),
                "account_id": self.journal_id.default_account_id.id,
                "partner_id": False,
                "debit": 0.0,
                "credit": bank_payment_amount if bank_payment_amount > 0 else 0.0,
            }),
        ]
        
        # Add VAT line if VAT is involved in partial payment
        if vat_amt > 0 and self.vat_account_id and self.include_vat:
            _logger.info("🔍 Adding VAT line: amount=%s, account=%s", vat_amt, self.vat_account_id.name)
            vat_line_data = {
                "name": _("VAT 7% (Proportional for partial payment)"),
                "account_id": self.vat_account_id.id,
                "partner_id": bill.partner_id.id,
                "debit": vat_amt,
                "credit": 0.0,
            }
            # Find the original VAT tax for tax invoice creation
            original_vat_lines = bill.line_ids.filtered(
                lambda l: l.tax_line_id and (
                    # Standard 7% purchase VAT
                    (l.tax_line_id.amount == 7.0 and l.tax_line_id.type_tax_use == 'purchase') or
                    # VAT with name containing "VAT" or "ภาษีมูลค่าเพิ่ม" and 7%
                    (l.tax_line_id.amount == 7.0 and (
                        'vat' in (l.tax_line_id.name or '').lower() or
                        'ภาษีมูลค่าเพิ่ม' in (l.tax_line_id.name or '') or
                        'ภาษี 7%' in (l.tax_line_id.name or '') or
                        'ภาษีซื้อ' in (l.tax_line_id.name or '')
                    )) or
                    # Account name contains VAT-related terms (for manual VAT entries)
                    (l.tax_line_id and l.tax_line_id.amount == 7.0 and (
                        'vat' in (l.account_id.name or '').lower() or
                        'ภาษีมูลค่าเพิ่ม' in (l.account_id.name or '') or
                        'ภาษีซื้อ' in (l.account_id.name or '')
                    ))
                )
            )
            if original_vat_lines:
                vat_line_data["tax_line_id"] = original_vat_lines[0].tax_line_id.id
                # Set base amount for tax calculation
                vat_line_data["tax_base_amount"] = (vat_amt * 100) / 7.0  # Calculate base from 7% VAT
            move_lines.append((0, 0, vat_line_data))
            _logger.info("✅ VAT line added to move_lines")
        else:
            _logger.info("❌ VAT line not added: vat_amt=%s, vat_account=%s", vat_amt, self.vat_account_id)
        
        # Add WHT line only if WHT amount > 0
        if wht_amt > 0:
            wht_line_data = {
                "name": _("Withholding tax %.2f%%") % (self.wht_percent or 0.0),
                "account_id": wht_account.id,
                "partner_id": bill.partner_id.id,
                "debit": 0.0,
                "credit": wht_amt,
            }
            # Add WHT tax information if tax is selected
            if self.wht_tax_id:
                wht_line_data["wht_tax_id"] = self.wht_tax_id.id
            move_lines.append((0, 0, wht_line_data))

        # Add bank charges line if bank charges > 0
        if bank_charge_amt > 0:
            if not bank_charge_account:
                raise UserError(_("Bank charge account is not configured. Please set it in Accounting Settings."))
            move_lines.append((0, 0, {
                "name": _("Bank Charges"),
                "account_id": bank_charge_account.id,
                "partner_id": False,
                "debit": bank_charge_amt,
                "credit": 0.0,
            }))

        # Debug: Show all move lines before creating the move
        _logger.info("🔍 === MOVE LINES DEBUG ===")
        total_debit = 0
        total_credit = 0
        for i, (_, _, line_data) in enumerate(move_lines):
            debit = line_data.get('debit', 0)
            credit = line_data.get('credit', 0)
            total_debit += debit
            total_credit += credit
            _logger.info("🔍 Line %d: %s - Dr: %s, Cr: %s", 
                        i+1, line_data.get('name', ''), debit, credit)
        _logger.info("🔍 Total Debit: %s, Total Credit: %s, Difference: %s", 
                    total_debit, total_credit, total_debit - total_credit)
        _logger.info("🔍 === END MOVE LINES DEBUG ===")

        move_vals = {
            "date": self.date,
            "journal_id": self.journal_id.id,
            "ref": self.memo or (bill.name or ""),
            "line_ids": move_lines,
        }
        
        # Debug: Log all move lines before creating
        _logger.info("📝 === MOVE LINES DEBUG ===")
        total_debit = 0
        total_credit = 0
        for line_data in move_lines:
            line = line_data[2]  # Get the dict from (0, 0, dict)
            debit = line.get('debit', 0)
            credit = line.get('credit', 0)
            total_debit += debit
            total_credit += credit
            _logger.info("📝 %s: Dr %s, Cr %s", line.get('name', 'Unknown'), debit, credit)
        _logger.info("📝 Total Debit: %s, Total Credit: %s, Difference: %s", 
                    total_debit, total_credit, total_debit - total_credit)
        _logger.info("📝 === END MOVE LINES DEBUG ===")
        
        pay_move = self.env["account.move"].create(move_vals)
        pay_move.action_post()

        # Create withholding tax moves and certificate if WHT tax is selected
        if self.wht_tax_id and wht_amt > 0:
            self._create_wht_moves_and_cert(pay_move, gross, wht_amt)

        # Create VAT tax invoice for partial payment if VAT is involved
        if vat_amt > 0 and self.vat_account_id and self.include_vat:
            vat_base_amount = (vat_amt * 100) / 7.0  # Calculate base from 7% VAT
            self._create_vat_tax_invoice(pay_move, vat_amt, vat_base_amount)

        # Reconcile AP debit (our move) against bill's AP credit (partial)
        ap_debit_line = pay_move.line_ids.filtered(lambda l: _is_payable_account(l.account_id) and l.debit > 0)
        bill_ap_credit = bill.line_ids.filtered(lambda l: _is_payable_account(l.account_id) and l.credit > 0 and not l.reconciled)

        if len(ap_debit_line) != 1:
            raise UserError(_("Cannot find exactly one payable debit line in payment move. Found %d lines.") % len(ap_debit_line))
        if len(bill_ap_credit) < 1:
            raise UserError(_("Cannot find any payable credit lines in bill to reconcile against."))

        lines_to_reconcile = ap_debit_line + bill_ap_credit[:1]  # Take only the first credit line
        lines_to_reconcile.reconcile()

        # Return to bill
        action = self.env.ref("account.action_move_in_invoice_type").read()[0]
        action["res_id"] = bill.id
        action["views"] = [(self.env.ref("account.view_move_form").id, "form")]
        return action

    def _create_wht_moves_and_cert(self, payment_move, base_amount, wht_amount):
        """Create withholding tax moves and certificate"""
        self.ensure_one()
        
        # Create withholding tax move
        wht_move_vals = {
            "move_id": payment_move.id,
            "partner_id": self.partner_id.id,
            "wht_tax_id": self.wht_tax_id.id,
            "amount_income": base_amount,
            "amount_wht": wht_amount,
            "wht_cert_income_type": self.wht_cert_income_type,
            "wht_cert_income_desc": dict(self._fields['wht_cert_income_type'].selection)[self.wht_cert_income_type] if self.wht_cert_income_type else "",
        }
        
        wht_move = self.env["account.withholding.move"].create(wht_move_vals)
        
        # Create withholding tax certificate
        try:
            payment_move.create_wht_cert()
        except Exception as e:
            # If WHT cert creation fails, log it but don't block the payment
            _logger.warning("Failed to create WHT certificate: %s", str(e))
            # You could also show a warning to the user
            # raise UserError(_("Payment created successfully, but WHT certificate creation failed: %s") % str(e))

    def _create_vat_tax_invoice(self, payment_move, vat_amount, vat_base_amount):
        """Create VAT tax invoice for partial payment"""
        self.ensure_one()
        
        if not vat_amount or not vat_base_amount:
            return
            
        # Find the VAT line in the payment move
        vat_lines = payment_move.line_ids.filtered(
            lambda l: l.tax_line_id and (
                # Standard 7% purchase VAT
                (l.tax_line_id.amount == 7.0 and l.tax_line_id.type_tax_use == 'purchase') or
                # VAT with name containing "VAT" or "ภาษีมูลค่าเพิ่ม" and 7%
                (l.tax_line_id.amount == 7.0 and (
                    'vat' in (l.tax_line_id.name or '').lower() or
                    'ภาษีมูลค่าเพิ่ม' in (l.tax_line_id.name or '') or
                    'ภาษี 7%' in (l.tax_line_id.name or '') or
                    'ภาษีซื้อ' in (l.tax_line_id.name or '')
                )) or
                # Account name contains VAT-related terms (for manual VAT entries)
                (l.tax_line_id and l.tax_line_id.amount == 7.0 and (
                    'vat' in (l.account_id.name or '').lower() or
                    'ภาษีมูลค่าเพิ่ม' in (l.account_id.name or '') or
                    'ภาษีซื้อ' in (l.account_id.name or '')
                ))
            )
        )
        
        if not vat_lines:
            return
            
        vat_line = vat_lines[0]
        
        # Create tax invoice for the VAT line
        try:
            # Use the context to indicate this is a partial payment
            vat_line_with_context = vat_line.with_context(partial_payment=True)
            
            # Create tax invoice record
            tax_invoice_vals = {
                "move_id": payment_move.id,
                "move_line_id": vat_line.id,
                "partner_id": self.partner_id.id,
                "tax_base_amount": vat_base_amount,
                "balance": vat_amount,
                "tax_invoice_number": False,  # Will be filled later when vendor info is provided
                "tax_invoice_date": False,    # Will be filled later when vendor info is provided
            }
            
            tax_invoice = self.env["account.move.tax.invoice"].create(tax_invoice_vals)
            vat_line.tax_invoice_ids = [(4, tax_invoice.id)]
            
        except Exception as e:
            # Log the error but don't block the payment
            _logger.warning("Failed to create VAT tax invoice for partial payment: %s", str(e))
