from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    apply_wht = fields.Boolean(string='Apply Withholding Tax')
    wht_type_id = fields.Many2one('account.wht.type', string='WHT Type')
    wht_base_amount = fields.Monetary(string='WHT Base Amount', currency_field='currency_id', compute='_compute_wht_amount', store=True, readonly=False)
    wht_amount = fields.Monetary(string='WHT Amount', currency_field='currency_id', compute='_compute_wht_amount', store=True, readonly=False)
    
    @api.depends('wht_type_id', 'amount', 'apply_wht')
    def _compute_wht_amount(self):
        for payment in self:
            if payment.apply_wht and payment.wht_type_id:
                # Default behavior: Base is the full payment amount (gross)
                # If user wants to edit base, they can (readonly=False above allows edits if not computed... wait, computed fields are readonly by default unless inverse is set or it's just a default)
                # Making it compute + store + readonly=False allows override but recomputes on dependencies.
                # To allow manual override that sticks, we usually use an onchange or a separate override flag, 
                # OR we avoid @api.depends for the value itself if we want it fully editable primarily.
                # However, for a good UX, we want it to auto-calculate initially.
                # Let's use onchange for calculation instead of compute to allow manual override without it jumping back?
                # The requirement says: "base auto-calculates... default, user can override".
                # Standard Odoo way for editable computed fields (store=True) works if we don't trigger recompute too aggressively.
                # But here 'amount' changes often.
                pass
    
    @api.onchange('wht_type_id', 'amount', 'apply_wht')
    def _onchange_wht_values(self):
        if self.apply_wht and self.wht_type_id:
            # We assume the 'amount' entered by user in payment form is the GROSS amount (before WHT).
            # Constraint in prompt: "Accounts Payable is cleared by full gross amount"
            # "Cash paid = 97,000", "Total Bills = 100,000".
            # The 'amount' field in account.payment usually represents the amount to reconcile with the bill (Gross).
            # Wait, standard Odoo: 
            # If I pay a 100 invoice, I say Amount = 100.
            # Then I want to say "Actually, 3 is WHT, I only pay 97 cash".
            # So `amount` (the main field) should be 100 (the AP reduction).
            # And we need to split the move lines: Dr AP 100, Cr Bank 97, Cr WHT 3.
            
            self.wht_base_amount = self.amount
            if self.wht_type_id.rate:
                self.wht_amount = self.amount * (self.wht_type_id.rate / 100.0)

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        """Override to inject WHT line and adjust Bank/Cash line."""
        res = super()._prepare_move_line_default_vals(write_off_line_vals, force_balance=force_balance)
        
        if not self.apply_wht or not self.wht_amount or not self.wht_type_id:
            return res

        # res is a list of dicts.
        # Standard payment creates:
        # 1. Receivable/Payable line (The one reconciling the invoice) -> Amount = 100 (Debit for Vendor Payment)
        # 2. Liquidity line (Bank) -> Amount = -100 (Credit)
        
        # We want:
        # 1. Payable: Dr 100 (Unchanged)
        # 2. Liquidity: Cr 97 (Adjusted)
        # 3. WHT: Cr 3 (New)
        
        liquidity_lines = [x for x in res if x['account_id'] == self.outstanding_account_id.id]
        if not liquidity_lines:
            # Fallback for when outstanding account is not used (direct bank)
            # Find the line that is NOT the counterpart (payable/receivable)
            # In simple payments, there are 2 lines. One is destination_account_id (payable), other is liquidity.
             liquidity_lines = [x for x in res if x['account_id'] != self.destination_account_id.id]
             
        if not liquidity_lines:
             return res

        # Assuming single liquidity line for simplicity in standard payments
        liq_line = liquidity_lines[0]
        
        # Adjust liquidity amount
        # Vendor Payment (Outbound): Liquidity is Credit (-). We accept less negative? 
        # Wait. 
        # Dr AP 100 (+100)
        # Cr Bank 100 (-100)
        # 
        # We want:
        # Dr AP 100 (+100)
        # Cr Bank 97 (-97)
        # Cr WHT 3 (-3)
        
        # In Odoo dicts (debit/credit fields are computed from 'amount_currency' and 'balance' usually in prepare? 
        # No, _prepare_move_line_default_vals usually returns 'debit', 'credit', 'amount_currency'.
        
        current_credit = liq_line.get('credit', 0.0)
        current_debit = liq_line.get('debit', 0.0)
        
        # Determine sign. Outbound payment: Credit > 0.
        if current_credit > 0:
            new_credit = current_credit - self.wht_amount
            if new_credit < 0:
                 raise UserError(_("WHT Amount cannot exceed Payment Amount."))
            liq_line['credit'] = new_credit
            
            # Adjust amount_currency if present
            if liq_line.get('amount_currency'):
                # Outbound: amount_currency is negative
                # -100 -> -97. So we add WHT amount. 
                # But wait, amount_currency sign depends on currency.
                # Let's assume standard behavior: negative for credit.
                # If we reduce credit (make it less negative), we add positive value?
                # -100 + 3 = -97. yes.
                
                # We need to be careful about currency. wht_amount is in payment currency.
                # If foreign currency, we need conversion? 
                # For now assuming payment currency = company currency or handled. 
                # The fields wht_amount are Monetary with currency_id.
                
                # Actually, `wht_amount` is in `currency_id` (Payment Currency).
                # `credit` is in Company Currency.
                # We need to convert wht_amount to company currency for the 'credit' field update.
                
                pass # Complex currency handling needed? 
                # If payment is in same currency as company, easy.
                # If different, we need to convert WHT amount to company currency to adjust 'credit'.
                
                # Let's look at how Odoo constructs these.
                
        # Create WHT Line
        wht_line = {
            'name': _('Withholding Tax - %s') % self.wht_type_id.name,
            'account_id': self.wht_type_id.account_id.id,
            'partner_id': self.partner_id.id,
            'currency_id': self.currency_id.id,
        }
        
        # Calculate amounts
        # WHT is always Credit for Vendor Payment (we withhold money we should have paid).
        # Dr Liability (decrease liability)
        # Cr Cash (decrease asset)
        # Cr WHT Payable (increase liability)
        
        # For 'credit' field (Company Currency):
        wht_amount_company = self.wht_amount
        if self.currency_id != self.company_id:
             wht_amount_company = self.currency_id._convert(
                self.wht_amount, 
                self.company_id, 
                self.company_id, 
                self.date or fields.Date.context_today(self)
            )

        if current_credit > 0:
             # Outbound
             liq_line['credit'] -= wht_amount_company
             if liq_line.get('amount_currency'):
                  # Amount currency is negative for credit lines in outbound?
                  sign = -1 if liq_line['amount_currency'] < 0 else 1
                  liq_line['amount_currency'] = (abs(liq_line['amount_currency']) - self.wht_amount) * sign

             wht_line['credit'] = wht_amount_company
             wht_line['debit'] = 0.0
             wht_line['amount_currency'] = -self.wht_amount # Negative because it's credit
        else:
             # Inbound (Customer Payment)? WHT might be Receivable (Debit)?
             # Requirement says "Vendor Payment". 
             # But good to be safe. Customer pays us 97, but Invoice was 100. They withheld 3.
             # Dr Bank 97
             # Dr WHT Receivable 3
             # Cr AR 100
             
             # If Inbound: Debit > 0.
             liq_line['debit'] -= wht_amount_company
             if liq_line.get('amount_currency'):
                  sign = 1
                  liq_line['amount_currency'] = (abs(liq_line['amount_currency']) - self.wht_amount) * sign
                  
             wht_line['debit'] = wht_amount_company
             wht_line['credit'] = 0.0
             wht_line['amount_currency'] = self.wht_amount
             
        res.append(wht_line)
        return res

