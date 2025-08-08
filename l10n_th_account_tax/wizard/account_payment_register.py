# Copyright 2020 Ecosoft Co., Ltd (https://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from odoo import _, api, fields, models
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    wht_tax_id = fields.Many2one(
        comodel_name="account.withholding.tax",
        string="Withholding Tax",
        help="Optional hidden field to keep wht_tax. Useful for case 1 tax only",
    )
    wht_amount_base = fields.Monetary(
        string="Withholding Base",
        help="Based amount for the tax amount",
        currency_field="currency_id",
    )

    @api.depends("early_payment_discount_mode")
    def _compute_payment_difference_handling(self):
        res = super()._compute_payment_difference_handling()
        for wizard in self:
            if wizard.wht_amount_base and wizard.wht_tax_id:
                wizard.payment_difference_handling = "reconcile"
        return res

    @api.depends("payment_difference_handling", "wht_tax_id", "wht_amount_base")
    def _compute_show_payment_difference_handling(self):
        """Override to show payment difference handling when WHT is involved"""
        try:
            super()._compute_show_payment_difference_handling()
            for wizard in self:
                try:
                    # Check if wizard exists
                    if not wizard.exists():
                        continue
                    if wizard.wht_tax_id and wizard.wht_amount_base:
                        wizard.show_payment_difference_handling = True
                except Exception:
                    # Skip this wizard if error occurs
                    continue
        except Exception:
            # If any error occurs, skip the computation
            pass

    @api.onchange("wht_tax_id", "wht_amount_base")
    def _onchange_wht_tax_id(self):
        try:
            # Check if record exists
            if not self.exists():
                return
            if self.wht_tax_id and self.wht_amount_base:
                if self.wht_tax_id.is_pit:
                    self._onchange_pit()
                else:
                    self._onchange_wht()
        except Exception:
            # If any error occurs, skip the onchange
            pass

    def _get_source_amount(self):
        """Get source amount with compatibility for different Odoo versions"""
        try:
            if hasattr(self, 'source_amount_currency'):
                return self.source_amount_currency
            elif hasattr(self, 'source_amount'):
                return self.source_amount
            else:
                # Fallback to amount if neither exists
                return self.amount
        except Exception:
            # Ultimate fallback
            return self.amount or 0.0

    def _onchange_wht(self):
        """Onchange set for normal withholding tax"""
        try:
            # Check if record exists
            if not self.exists():
                return
                
            amount_wht = self.wht_tax_id.amount / 100 * self.wht_amount_base
            # Use source_amount_currency for Odoo 17 compatibility
            source_amount = self._get_source_amount()
            amount_currency = self.company_id.currency_id._convert(
                source_amount,
                self.currency_id,
                self.company_id,
                self.payment_date,
            )
            self.amount = amount_currency - amount_wht
            self.writeoff_account_id = self.wht_tax_id.account_id
            self.writeoff_label = self.wht_tax_id.display_name
        except Exception:
            # If any error occurs, skip the onchange
            pass

    def _onchange_pit(self):
        """Onchange set for personal income tax"""
        try:
            # Check if record exists
            if not self.exists():
                return
                
            amount_base_company = self.currency_id._convert(
                self.wht_amount_base,
                self.company_id.currency_id,
                self.company_id,
                self.payment_date,
            )
            amount_pit_company = self.wht_tax_id.pit_id._compute_expected_wht(
                self.partner_id,
                amount_base_company,
                self.payment_date,
                self.company_id.currency_id,
                self.company_id,
            )
            amount_pit = self.company_id.currency_id._convert(
                amount_pit_company,
                self.currency_id,
                self.company_id,
                self.payment_date,
            )
            # Use source_amount_currency for Odoo 17 compatibility
            source_amount = self._get_source_amount()
            amount_currency = self.company_id.currency_id._convert(
                source_amount,
                self.currency_id,
                self.company_id,
                self.payment_date,
            )
            self.amount = amount_currency - amount_pit
            self.writeoff_account_id = self.wht_tax_id.account_id
            self.writeoff_label = self.wht_tax_id.display_name
        except Exception:
            # If any error occurs, skip the onchange
            pass

    def _create_payment_vals_from_batch(self, batch_result):
        try:
            # Check if record exists
            if not self.exists():
                return super()._create_payment_vals_from_batch(batch_result)
                
            payment_vals = super()._create_payment_vals_from_batch(batch_result)
            # Check case auto and manual withholding tax
            if self.payment_difference_handling == "reconcile" and self.wht_tax_id:
                payment_vals["write_off_line_vals"] = self._prepare_writeoff_move_line(
                    payment_vals.get("write_off_line_vals", False)
                )
            return payment_vals
        except Exception:
            # If any error occurs, call super without additional processing
            return super()._create_payment_vals_from_batch(batch_result)

    @api.depends(
        "source_amount",
        "source_amount_currency", 
        "source_currency_id",
        "company_id",
        "currency_id",
        "payment_date",
    )
    def _compute_amount(self):
        """This function is the first entry point, to calculate withholding amount"""
        try:
            res = super()._compute_amount()
        except Exception as e:
            # Handle potential errors in parent method
            _logger.warning("Error in parent _compute_amount: %s", str(e))
            res = None
            
        # Enhanced WHT calculation - Get the sum withholding tax amount from invoice line
        skip_wht_deduct = self.env.context.get("skip_wht_deduct")
        active_model = self.env.context.get("active_model")
        
        if not skip_wht_deduct and active_model == "account.move":
            try:
                active_ids = self.env.context.get("active_ids", [])
                if not active_ids:
                    return res
                    
                # Filter only existing invoices
                invoices = self.env["account.move"].browse(active_ids).exists()
                if not invoices:
                    return res
                
                # Enhanced WHT detection - check all invoice lines
                all_wht_lines = []
                for invoice in invoices:
                    for line in invoice.line_ids:
                        if line.exists() and line.wht_tax_id and line.balance != 0:
                            all_wht_lines.append(line)
                
                if not all_wht_lines:
                    # Try alternative approach - check if lines have products with WHT
                    for invoice in invoices:
                        for line in invoice.line_ids:
                            if line.exists() and line.product_id and not line.wht_tax_id:
                                # Auto-assign WHT tax based on product and partner
                                self._auto_assign_wht_tax(line, invoice.partner_id)
                                if line.wht_tax_id:
                                    all_wht_lines.append(line)
                
                if all_wht_lines:
                    # Case WHT only, ensure only 1 wizard
                    try:
                        self.ensure_one()
                        # Check if wizard exists
                        if not self.exists():
                            return res
                    except Exception:
                        # If ensure_one fails or wizard doesn't exist, skip
                        return res
                    
                    try:
                        # Enhanced WHT calculation
                        self._calculate_and_apply_wht(all_wht_lines, invoices)
                    except Exception as e:
                        # Log error but don't break the flow
                        _logger.warning("Error processing WHT deduction: %s", str(e))
                        
            except Exception as e:
                # Log error but don't break the flow
                _logger.warning("Error in WHT computation: %s", str(e))
        return res

    def _update_payment_register(self, amount_base, amount_wht, wht_move_lines):
        try:
            self.ensure_one()
            # Check if record exists
            if not self.exists():
                return False
                
            if not amount_base:
                return False
                
            self.amount -= amount_wht
            self.wht_amount_base = amount_base
            
            # Filter only existing move lines
            existing_lines = wht_move_lines.filtered(lambda l: l.exists())
            wht_tax = existing_lines.mapped("wht_tax_id")
            if wht_tax and len(wht_tax) == 1:
                self.wht_tax_id = wht_tax
                self.writeoff_account_id = self.wht_tax_id.account_id
                self.writeoff_label = self.wht_tax_id.display_name
        except Exception as e:
            # Log error but don't break the flow
            _logger.warning("Error updating payment register with WHT: %s", str(e))
            return False
        return True

    def _auto_assign_wht_tax(self, line, partner):
        """Auto assign WHT tax to invoice line based on product and partner type"""
        try:
            if not line.product_id:
                return False
                
            # Determine WHT tax based on partner type
            if partner.company_type == 'company':
                wht_tax = line.product_id.supplier_company_wht_tax_id
            else:
                wht_tax = line.product_id.supplier_wht_tax_id
                
            if wht_tax:
                line.wht_tax_id = wht_tax
                _logger.info(f"Auto-assigned WHT tax {wht_tax.name} to line {line.name}")
                return True
                
        except Exception as e:
            _logger.warning(f"Error auto-assigning WHT tax: {e}")
            
        return False

    def _calculate_and_apply_wht(self, wht_lines, invoices):
        """Calculate and apply WHT amounts to payment register"""
        try:
            total_wht_base = 0
            total_wht_amount = 0
            wht_taxes = []
            
            for line in wht_lines:
                if not line.exists() or not line.wht_tax_id:
                    continue
                    
                # Calculate WHT base amount (absolute value of balance)
                base_amount = abs(line.balance)
                
                # Calculate WHT amount
                if line.wht_tax_id.is_pit:
                    # Personal Income Tax - use PIT calculation
                    try:
                        pit_date = self.payment_date or fields.Date.context_today(self)
                        effective_pit = line.wht_tax_id.with_context(pit_date=pit_date).pit_id
                        if effective_pit:
                            wht_amount = effective_pit._compute_expected_wht(
                                line.partner_id or invoices[0].partner_id,
                                base_amount,
                                pit_date,
                                self.currency_id,
                                self.company_id,
                            )
                        else:
                            wht_amount = 0
                    except Exception:
                        wht_amount = 0
                else:
                    # Regular WHT - fixed percentage
                    wht_amount = base_amount * (line.wht_tax_id.amount / 100)
                
                total_wht_base += base_amount
                total_wht_amount += wht_amount
                wht_taxes.append(line.wht_tax_id)
                
                _logger.info(f"WHT calculation: {line.name} - Base: {base_amount}, WHT: {wht_amount}")
            
            # Apply WHT to payment if any amount found
            if total_wht_amount > 0:
                # Reduce payment amount by WHT
                self.amount -= total_wht_amount
                self.wht_amount_base = total_wht_base
                
                # Set writeoff configuration
                unique_wht_taxes = list(set(wht_taxes))
                if len(unique_wht_taxes) == 1:
                    # Single WHT tax type
                    wht_tax = unique_wht_taxes[0]
                    self.wht_tax_id = wht_tax
                    self.writeoff_account_id = wht_tax.account_id
                    self.writeoff_label = wht_tax.display_name
                else:
                    # Multiple WHT tax types - use first one's account
                    self.writeoff_account_id = unique_wht_taxes[0].account_id
                    self.writeoff_label = f"WHT - Multiple Types ({len(unique_wht_taxes)} types)"
                
                # Set payment difference handling to reconcile
                self.payment_difference_handling = 'reconcile'
                
                _logger.info(f"Applied WHT: Base={total_wht_base}, Amount={total_wht_amount}, Final Payment={self.amount}")
                
        except Exception as e:
            _logger.error(f"Error calculating and applying WHT: {e}")
            # Don't break the flow, just log the error

    @api.onchange('partner_id', 'currency_id', 'payment_date')
    def _onchange_partner_currency_date(self):
        """Recalculate WHT when partner, currency, or date changes"""
        if self.env.context.get('active_model') == 'account.move':
            # Force recalculate WHT
            self._compute_amount()

    @api.onchange('amount')
    def _onchange_amount_wht_check(self):
        """Check if amount was manually changed and WHT should be recalculated"""
        if (self.env.context.get('active_model') == 'account.move' and 
            hasattr(self, 'wht_amount_base') and self.wht_amount_base):
            # If user manually changed amount, don't override with WHT calculation
            # But show a warning message if needed
            pass

    @api.model
    def default_get(self, fields_list):
        try:
            res = super().default_get(fields_list)
            if self.env.context.get("active_model") == "account.move":
                active_ids = self.env.context.get("active_ids", False)
                if not active_ids:
                    return res
                    
                # Filter only existing moves
                move_ids = self.env["account.move"].browse(active_ids).exists()
                if not move_ids:
                    return res
                    
                partner_ids = move_ids.mapped("partner_id")
                wht_tax_line = move_ids.line_ids.filtered(lambda l: l.exists() and l.wht_tax_id)
                
                if len(partner_ids) > 1 and wht_tax_line:
                    raise UserError(
                        _(
                            "You can't register a payment for invoices "
                            "(with withholding tax) belong to multiple partners."
                        )
                    )
                # Force group payment for WHT
                if wht_tax_line:
                    res["group_payment"] = True
            return res
        except UserError:
            # Re-raise UserError as it's intentional
            raise
        except Exception as e:
            # Log error but return basic result
            _logger.warning("Error in default_get: %s", str(e))
            return super().default_get(fields_list)

    def _create_payments(self):
        try:
            self.ensure_one()
            # Check if record exists
            if not self.exists():
                return super()._create_payments()
                
            if self.wht_tax_id and not self.group_payment:
                raise UserError(
                    _(
                        "Please check Group Payments when dealing "
                        "with multiple invoices that has withholding tax."
                    )
                )
            # For case calculate tax invoice partial payment
            if self.payment_difference_handling == "open":
                self = self.with_context(partial_payment=True)
            elif self.payment_difference_handling == "reconcile":
                self = self.with_context(skip_account_move_synchronization=True)
            # Add context reverse_tax_invoice for case reversal
            active_ids = self.env.context.get("active_ids", False)
            if active_ids:
                # Filter only existing moves
                move_ids = self.env["account.move"].browse(active_ids).exists()
                if any(move.move_type in ["in_refund", "out_refund"] for move in move_ids):
                    self = self.with_context(reverse_tax_invoice=True)
            return super()._create_payments()
        except UserError:
            # Re-raise UserError as it's intentional
            raise
        except AttributeError as e:
            if "'NoneType' object has no attribute 'get'" in str(e):
                _logger.warning("Reconciliation returned None, handling gracefully: %s", str(e))
                # Try to create payments without immediate reconciliation
                try:
                    # Create payment records first
                    payment_vals_list = []
                    for batch_result in self._get_batches():
                        payment_vals_list.append(self._safe_create_payment_vals(batch_result))
                    
                    payments = self.env['account.payment'].create(payment_vals_list)
                    return payments
                except Exception as create_error:
                    _logger.warning("Error creating payments safely: %s", str(create_error))
                    return self.env['account.payment']
            else:
                _logger.warning("AttributeError in _create_payments: %s", str(e))
                return super()._create_payments()
        except Exception as e:
            # Log error but try to continue
            _logger.warning("Error in _create_payments: %s", str(e))
            return super()._create_payments()

    def action_create_payments(self):
        """Override to handle WHT specific logic"""
        try:
            return self._create_payments()
        except Exception as e:
            _logger.warning("Error in action_create_payments: %s", str(e))
            # Try to call parent method as fallback
            return super().action_create_payments() if hasattr(super(), 'action_create_payments') else self._create_payments()

    def _safe_create_payment_vals(self, batch_result):
        """Safely create payment values from batch result"""
        try:
            return self._create_payment_vals_from_batch(batch_result)
        except Exception as e:
            _logger.warning("Error creating payment vals from batch: %s", str(e))
            # Return minimal payment values
            return {
                'payment_type': self.payment_type,
                'partner_type': self.partner_type,
                'partner_id': self.partner_id.id,
                'amount': self.amount,
                'currency_id': self.currency_id.id,
                'payment_date': self.payment_date,
                'journal_id': self.journal_id.id,
                'company_id': self.company_id.id,
            }

    def _prepare_writeoff_move_line(self, write_off_line_vals=None):
        """Prepare value withholding tax move of payment"""
        try:
            # Check if record exists
            if not self.exists():
                return write_off_line_vals or []
                
            # Use proper currency conversion for Odoo 17
            try:
                if hasattr(self.env["res.currency"], "_get_conversion_rate"):
                    conversion_rate = self.env["res.currency"]._get_conversion_rate(
                        self.currency_id,
                        self.company_id.currency_id,
                        self.company_id,
                        self.payment_date,
                    )
                else:
                    # Fallback for older versions
                    conversion_rate = self.currency_id._get_conversion_rate(
                        self.currency_id,
                        self.company_id.currency_id,
                        self.company_id,
                        self.payment_date,
                    )
            except Exception:
                # Ultimate fallback - use rate 1.0
                conversion_rate = 1.0
            
            wht_amount_base_company = self.company_id.currency_id.round(
                self.wht_amount_base * conversion_rate
            )
            if write_off_line_vals:
                for write_off in write_off_line_vals:
                    write_off["wht_tax_id"] = self.wht_tax_id.id
                    write_off["tax_base_amount"] = wht_amount_base_company
                return write_off_line_vals

            write_off_amount_currency = (
                self.payment_difference
                if self.payment_type == "inbound"
                else -self.payment_difference
            )
            write_off_balance = self.company_id.currency_id.round(
                write_off_amount_currency * conversion_rate
            )
            return [
                {
                    "name": self.writeoff_label,
                    "account_id": self.writeoff_account_id.id,
                    "partner_id": self.partner_id.id,
                    "currency_id": self.currency_id.id,
                    "amount_currency": write_off_amount_currency,
                    "balance": write_off_balance,
                    "wht_tax_id": self.wht_tax_id.id,
                    "tax_base_amount": wht_amount_base_company,
                }
            ]
        except Exception as e:
            # Log error and return empty list
            _logger.warning("Error in _prepare_writeoff_move_line: %s", str(e))
            return write_off_line_vals or []


