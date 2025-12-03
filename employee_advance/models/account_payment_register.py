from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _get_default_line(self):
        """Detect and return the appropriate move lines for payment"""
        if self.env.context.get('force_advance_payment'):
            # When force_advance_payment is True, we need to get the appropriate lines
            # including current asset accounts (like 141101) for advance clearing
            active_ids = self.env.context.get('active_ids')
            active_model = self.env.context.get('active_model')
            
            if active_model == 'account.move' and active_ids:
                moves = self.env['account.move'].browse(active_ids)
                lines = self._get_lines_vals_list(moves)
                return lines
        return super()._get_default_line()

    @api.model
    def default_get(self, fields_list):
        """Override default_get to handle advance payment scenarios"""
        res = super().default_get(fields_list)

        # Check if this is called from the 'Clear with Advance' button
        if self.env.context.get('force_advance_payment'):
            advance_box_id = self.env.context.get('default_advance_box_id')
            if advance_box_id:
                advance_box = self.env['employee.advance.box'].browse(advance_box_id)
                
                if not advance_box.exists():
                    raise UserError(_("No Advance Box configured for this employee."))
                
                if not advance_box.journal_id:
                    raise UserError(_("No journal configured for the advance box."))

                # Auto-fill journal from advance box
                res['journal_id'] = advance_box.journal_id.id
        
        # Check if this is called from advance box refill
        if self.env.context.get('advance_box_refill'):
            advance_box_id = self.env.context.get('default_advance_box_id')
            if advance_box_id:
                advance_box = self.env['employee.advance.box'].browse(advance_box_id)
                
                if not advance_box.exists():
                    raise UserError(_("No Advance Box configured for this refill."))
                
                if not advance_box.journal_id:
                    raise UserError(_("No journal configured for the advance box."))

                # Auto-fill journal from advance box
                res['journal_id'] = advance_box.journal_id.id
                
                # Set payment type to outbound (money going out)
                res['payment_type'] = 'outbound'
                
                # Note: destination_account_id field removed as it doesn't exist in account.payment model
                # Internal transfer will be handled through move lines instead

        return res

    def _get_lines_vals_list(self, moves):
        """Override to include current asset accounts for advance payments"""
        if self.env.context.get('force_advance_payment'):
            # Include current asset accounts in addition to the default receivable/payable
            # This allows payments to be made against current asset accounts like 141101
            lines_vals_list = []
            for move in moves:
                # Get payable lines (liability_payable) for vendor bills
                for line in move.line_ids:
                    # Include payable accounts (normal behavior for vendor bills)  
                    if line.account_id.account_type == 'liability_payable' and line.balance < 0:
                        lines_vals_list.append({
                            'name': line.name,
                            'move_line_id': line.id,
                            'account_id': line.account_id.id,
                            'partner_id': line.partner_id.id,
                            'communicate': line.name,
                            'amount_original': abs(line.balance),
                            'amount_residual': abs(line.amount_residual),
                            'amount': abs(line.amount_residual),
                            'debit': line.balance < 0,
                            'credit': line.balance > 0,
                        })
            return lines_vals_list
        else:
            # Default behavior
            return super()._get_lines_vals_list(moves)

    def _create_payment_vals_from_wizard(self, batch_result):
        """Override to handle advance payment logic"""
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        
        if self.env.context.get('force_advance_payment'):
            # Add flag to identify this as an advance clearing payment
            payment_vals['is_advance_clearing'] = True
            # Ensure unique reference to prevent duplicate error
            advance_box_id = self.env.context.get('default_advance_box_id')
            if advance_box_id:
                advance_box = self.env['employee.advance.box'].browse(advance_box_id)
                if advance_box:
                    # Add advance box info to reference to make it unique
                    if payment_vals.get('ref'):
                        payment_vals['ref'] = f"{payment_vals['ref']} - Advance: {advance_box.name}"
                    else:
                        payment_vals['ref'] = f"Advance Clearing - {advance_box.name}"
            # Ensure the payment name will be generated by the sequence to avoid duplicates
            payment_vals['name'] = False

        return payment_vals

    def _create_payments(self):
        """Override to handle advance payment logic and prevent duplicate entries"""
        if self.env.context.get('force_advance_payment'):
            # Process advance payment validation
            advance_box_id = self.env.context.get('default_advance_box_id')
            if advance_box_id:
                advance_box = self.env['employee.advance.box'].browse(advance_box_id)
                if not advance_box.exists():
                    raise UserError(_("No Advance Box configured for this employee."))
                # Validate that the advance box has the required journal and account
                if not advance_box.journal_id:
                    raise UserError(_("No journal configured for the advance box."))
                if not advance_box.account_id:
                    raise UserError(_("No account configured for the advance box."))
                # Check fiscal lock
                company_id = advance_box.company_id or self.env.company
                from odoo import fields
                locked_date = company_id._get_user_fiscal_lock_date()
                current_date = fields.Date.context_today(self.env.user)
                if current_date <= locked_date:
                    raise UserError(_("Cannot create payment before or during the lock date %s.", locked_date))

        # Call the original method to create the payment
        payments = super()._create_payments()
        
        # If this is an advance payment, also reconcile with the advance account
        if self.env.context.get('force_advance_payment') and payments:
            advance_box_id = self.env.context.get('default_advance_box_id')
            if advance_box_id:
                advance_box = self.env['employee.advance.box'].browse(advance_box_id)
                if advance_box.account_id:
                    for payment in payments:
                        # Add a custom flag for advance clearing
                        payment.write({'is_advance_clearing': True})
                        # Link to the advance box
                        for move_line in payment.reconciled_bill_ids:
                            move_line.move_id.write({'advance_box_id': advance_box.id})
        
        return payments


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # Advance box refill tracking fields
    is_advance_box_refill = fields.Boolean(
        string='Is Advance Box Refill',
        default=False,
        help='True if this payment is an advance box refill'
    )
    advance_box_id = fields.Many2one(
        'employee.advance.box',
        string='Advance Box',
        help='Advance box related to this payment'
    )
    destination_account_id = fields.Many2one(
        'account.account',
        string='Destination Account',
        help='Destination account for internal transfers'
    )

    def _create_payment_vals_from_wizard(self, batch_result):
        """Override to handle advance box refill payments"""
        payment_vals_list = super()._create_payment_vals_from_wizard(batch_result)
        
        # Check if this is an advance box refill
        if self.env.context.get('advance_box_refill'):
            advance_box_id = self.env.context.get('default_advance_box_id')
            if advance_box_id:
                advance_box = self.env['employee.advance.box'].browse(advance_box_id)
                if advance_box:
                    # Add advance box reference to all payment values
                    for payment_vals in payment_vals_list:
                        payment_vals['advance_box_id'] = advance_box.id
                        payment_vals['is_advance_box_refill'] = True
                        # Set partner to employee's private address
                        payment_vals['partner_id'] = advance_box._get_employee_partner()
                        
                        # Set destination account for internal transfer
                        destination_account_id = self.env.context.get('internal_transfer_destination_account_id')
                        if destination_account_id:
                            payment_vals['destination_account_id'] = destination_account_id
        
        return payment_vals_list

    def _create_payments(self):
        """Override to handle advance box refill payment reconciliation"""
        payments = super()._create_payments()
        
        # If this is an advance box refill, handle reconciliation
        if self.env.context.get('advance_box_refill') and payments:
            advance_box_id = self.env.context.get('default_advance_box_id')
            if advance_box_id:
                advance_box = self.env['employee.advance.box'].browse(advance_box_id)
                if advance_box:
                    for payment in payments:
                        # Mark payment as advance box refill
                        payment.write({
                            'is_advance_box_refill': True,
                            'advance_box_id': advance_box.id
                        })
                        
                        # Reconcile payment with the temporary bill
                        active_ids = self.env.context.get('active_ids', [])
                        if active_ids:
                            temp_bill = self.env['account.move'].browse(active_ids[0])
                            if temp_bill.exists():
                                # Find payment move lines and bill payable lines
                                payment_move_lines = payment.move_id.line_ids.filtered(
                                    lambda l: l.account_id.internal_type in ('receivable', 'payable')
                                )
                                bill_payable_lines = temp_bill.line_ids.filtered(
                                    lambda l: l.account_id.internal_type in ('receivable', 'payable') and l.balance < 0
                                )
                                
                                # Reconcile payment with bill
                                if payment_move_lines and bill_payable_lines:
                                    for payment_line in payment_move_lines:
                                        for bill_line in bill_payable_lines:
                                            if payment_line.account_id == bill_line.account_id:
                                                try:
                                                    (payment_line + bill_line).reconcile()
                                                    _logger.info("💳 Reconciled payment line %s with bill line %s",
                                                               payment_line.id, bill_line.id)
                                                except Exception as e:
                                                    _logger.warning("⚠️ Could not reconcile payment with bill: %s", str(e))
                        
                        # Refresh advance box balance
                        try:
                            advance_box._refresh_balance_simple()
                            _logger.info("💰 Advance box balance refreshed after payment refill")
                        except Exception as e:
                            _logger.warning("⚠️ Balance refresh failed after refill: %s", str(e))
        
        return payments