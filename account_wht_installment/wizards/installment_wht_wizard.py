# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

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

    @api.depends("amount_to_clear", "wht_percent", "bank_charge")
    def _compute_amounts(self):
        for w in self:
            gross = w.amount_to_clear or 0.0
            rate = max(w.wht_percent or 0.0, 0.0) / 100.0
            bank_charge = w.bank_charge or 0.0
            w.wht_amount = round(gross * rate, 2)
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
        self.ensure_one()
        bill = self.move_id.with_company(self.company_id.id)
        if bill.state != "posted" or bill.move_type not in ("in_invoice", "in_refund"):
            raise UserError(_("Wizard can be used only on posted Vendor Bills/CNs."))
        if bill.amount_residual <= 0:
            raise UserError(_("Nothing to clear; the bill is already fully paid."))

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
        import logging
        _logger = logging.getLogger(__name__)
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

        # Main JE: Dr AP gross, Cr Bank (gross - wht), Cr WHT
        move_lines = [
            (0, 0, {
                "name": _("Installment clearance for %s") % (bill.name or bill.ref or ""),
                "account_id": payable_account_id,
                "partner_id": bill.partner_id.id,
                "debit": gross if gross > 0 else 0.0,
                "credit": 0.0,
            }),
            (0, 0, {
                "name": _("Bank payment"),
                "account_id": self.journal_id.default_account_id.id,
                "partner_id": False,
                "debit": 0.0,
                "credit": (gross - wht_amt) if (gross - wht_amt) > 0 else 0.0,
            }),
        ]
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

        move_vals = {
            "date": self.date,
            "journal_id": self.journal_id.id,
            "ref": self.memo or (bill.name or ""),
            "line_ids": move_lines,
        }
        pay_move = self.env["account.move"].create(move_vals)
        pay_move.action_post()

        # Extra JE for bank charges if needed
        if bank_charge_amt > 0:
            if not bank_charge_account:
                raise UserError(_("Bank charge account is not configured. Please set it in Accounting Settings."))
            fee_move = self.env["account.move"].create({
                "date": self.date,
                "journal_id": self.journal_id.id,
                "ref": (self.memo or (bill.name or "")) + " - Bank Charges",
                "line_ids": [
                    (0, 0, {
                        "name": _("Bank Charges for %s") % (bill.name or bill.ref or ""),
                        "account_id": bank_charge_account.id,
                        "debit": bank_charge_amt,
                        "credit": 0.0,
                    }),
                    (0, 0, {
                        "name": _("Bank Charges for %s") % (bill.name or bill.ref or ""),
                        "account_id": self.journal_id.default_account_id.id,
                        "debit": 0.0,
                        "credit": bank_charge_amt,
                    }),
                ],
            })
            fee_move.action_post()

        # Create withholding tax moves and certificate if WHT tax is selected
        if self.wht_tax_id and wht_amt > 0:
            self._create_wht_moves_and_cert(pay_move, gross, wht_amt)

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
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning("Failed to create WHT certificate: %s", str(e))
            # You could also show a warning to the user
            # raise UserError(_("Payment created successfully, but WHT certificate creation failed: %s") % str(e))
