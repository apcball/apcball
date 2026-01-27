# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Anfas Faisal K (odoo@cybrosys.info)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
################################################################################
from odoo import api, fields, models


class AccountPaymentRegister(models.TransientModel):
    """Extend payment register wizard to handle manual exchange rates from bills."""
    _inherit = 'account.payment.register'

    manual_currency_rate = fields.Float(
        string='Manual Exchange Rate',
        help='Manual exchange rate from the bill/invoice',
        digits=(12, 4),
        readonly=True,
        copy=False
    )
    use_manual_rate = fields.Boolean(
        string='Use Manual Rate',
        help='Indicates if manual rate should be used from the bill',
        readonly=True,
        copy=False
    )

    @api.model
    def default_get(self, fields_list):
        """Override to get manual exchange rate from the source bill."""
        res = super().default_get(fields_list)
        
        # Get active invoice/bill from context
        active_model = self.env.context.get('active_model')
        active_ids = self.env.context.get('active_ids', [])
        
        if active_model == 'account.move' and active_ids:
            moves = self.env['account.move'].browse(active_ids)
            
            # Check if all moves have manual exchange rate enabled and they all use the same rate
            manual_rate_moves = moves.filtered(lambda m: m.is_exchange and m.rate)
            
            if manual_rate_moves:
                # If all selected invoices use manual rate and same rate
                rates = manual_rate_moves.mapped('rate')
                if len(set(rates)) == 1:  # All use the same rate
                    res['use_manual_rate'] = True
                    res['manual_currency_rate'] = rates[0]
        
        return res

    def _create_payment_vals_from_wizard(self, batch_result):
        """Override to apply manual exchange rate to payment."""
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        
        # Apply manual rate if it exists
        if self.use_manual_rate and self.manual_currency_rate:
            payment_vals['use_manual_rate'] = True
            payment_vals['manual_currency_rate'] = self.manual_currency_rate
        
        return payment_vals

    def _create_payment_vals_from_batch(self, batch_result):
        """Override to apply manual exchange rate to batch payments."""
        payment_vals = super()._create_payment_vals_from_batch(batch_result)
        
        # Apply manual rate if it exists
        if self.use_manual_rate and self.manual_currency_rate:
            payment_vals['use_manual_rate'] = True
            payment_vals['manual_currency_rate'] = self.manual_currency_rate
        
        return payment_vals
    
    def _init_payments(self, to_process, edit_mode=False):
        """Override to pass manual rate via context."""
        # Set manual rate in context for payment creation
        if self.use_manual_rate and self.manual_currency_rate:
            self = self.with_context(
                manual_exchange_rate=self.manual_currency_rate,
                use_manual_exchange=True
            )
        return super()._init_payments(to_process, edit_mode=edit_mode)


class AccountPayment(models.Model):
    """Extend account.payment to use manual exchange rate."""
    _inherit = 'account.payment'

    manual_currency_rate = fields.Float(
        string='Manual Exchange Rate',
        help='Manual exchange rate applied to this payment',
        digits=(12, 4),
        copy=False
    )
    use_manual_rate = fields.Boolean(
        string='Uses Manual Rate',
        help='Indicates if this payment uses a manual exchange rate',
        copy=False
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to capture manual rate from context."""
        for vals in vals_list:
            # Check if manual rate is in context or in vals
            ctx = self.env.context
            if ctx.get('use_manual_exchange') and ctx.get('manual_exchange_rate'):
                vals['use_manual_rate'] = True
                vals['manual_currency_rate'] = ctx.get('manual_exchange_rate')
        
        # Create payments
        payments = super().create(vals_list)
        
        # Apply manual rate to move lines after creation (as backup)
        for payment in payments:
            if payment.use_manual_rate and payment.manual_currency_rate and payment.move_id:
                payment._apply_manual_rate_to_move()
        
        return payments

    def _seek_for_lines(self):
        """Override to use manual exchange rate when computing amounts."""
        if self.use_manual_rate and self.manual_currency_rate and self.manual_currency_rate > 0:
            # Store manual rate in context for line computations
            self = self.with_context(manual_payment_rate=self.manual_currency_rate)
        return super()._seek_for_lines()
    
    def _get_liquidity_move_line_vals(self, amount):
        """Override to use manual exchange rate."""
        vals = super()._get_liquidity_move_line_vals(amount)
        
        if self.use_manual_rate and self.manual_currency_rate and self.manual_currency_rate > 0:
            company_currency = self.company_id.currency_id
            if self.currency_id and self.currency_id != company_currency:
                # Recalculate balance using manual rate
                amount_currency = vals.get('amount_currency', 0.0)
                if amount_currency:
                    balance = amount_currency * self.manual_currency_rate
                    vals['balance'] = balance
                    vals['debit'] = balance if balance > 0 else 0.0
                    vals['credit'] = -balance if balance < 0 else 0.0
        
        return vals
    
    def _get_counterpart_move_line_vals(self, invoice=None):
        """Override to use manual exchange rate."""
        vals_list = super()._get_counterpart_move_line_vals(invoice)
        
        if self.use_manual_rate and self.manual_currency_rate and self.manual_currency_rate > 0:
            company_currency = self.company_id.currency_id
            if self.currency_id and self.currency_id != company_currency:
                # Recalculate balance using manual rate for all counterpart lines
                for vals in vals_list:
                    amount_currency = vals.get('amount_currency', 0.0)
                    if amount_currency:
                        balance = amount_currency * self.manual_currency_rate
                        vals['balance'] = balance
                        vals['debit'] = balance if balance > 0 else 0.0
                        vals['credit'] = -balance if balance < 0 else 0.0
        
        return vals_list
    
    def _apply_manual_rate_to_move(self):
        """Apply manual exchange rate to payment move lines."""
        self.ensure_one()
        
        if not self.use_manual_rate or not self.manual_currency_rate or self.manual_currency_rate <= 0:
            return
        
        company_currency = self.company_id.currency_id
        
        # Only apply if payment currency differs from company currency
        if not self.currency_id or self.currency_id == company_currency:
            return
        
        if not self.move_id:
            return
        
        # Update ALL move lines with manual rate including amount_residual
        # Use direct SQL to avoid triggering recomputations
        # Update ALL lines (not just payment currency ones)
        self.env.cr.execute("""
            UPDATE account_move_line
            SET balance = amount_currency * %s,
                debit = CASE WHEN amount_currency * %s > 0 THEN amount_currency * %s ELSE 0 END,
                credit = CASE WHEN amount_currency * %s < 0 THEN -(amount_currency * %s) ELSE 0 END,
                amount_residual = CASE 
                    WHEN amount_residual_currency != 0 
                    THEN amount_residual_currency * %s 
                    ELSE 0
                END
            WHERE move_id = %s 
                AND amount_currency != 0
        """, (
            self.manual_currency_rate,
            self.manual_currency_rate,
            self.manual_currency_rate,
            self.manual_currency_rate,
            self.manual_currency_rate,
            self.manual_currency_rate,
            self.move_id.id
        ))
        
        # Invalidate cache completely to force reload
        self.move_id.invalidate_recordset(['line_ids', 'amount_total', 'amount_residual'])
        self.move_id.line_ids.invalidate_recordset([
            'balance', 'debit', 'credit', 
            'amount_residual', 'amount_residual_currency',
            'matched_debit_ids', 'matched_credit_ids'
        ])
    
    def _synchronize_to_moves(self, changed_fields):
        """Override to preserve manual rate after synchronization."""
        # Don't reapply rate during sync to avoid loops
        if self.env.context.get('skip_manual_rate_apply'):
            return super()._synchronize_to_moves(changed_fields)
        
        res = super()._synchronize_to_moves(changed_fields)
        
        # Reapply manual rate after sync only if amount changed
        if 'amount' in changed_fields or 'currency_id' in changed_fields:
            for payment in self:
                if payment.use_manual_rate and payment.manual_currency_rate and payment.move_id:
                    payment.with_context(skip_manual_rate_apply=True)._apply_manual_rate_to_move()
        
        return res
    
    def write(self, vals):
        """Override to preserve manual rate after write."""
        res = super().write(vals)
        
        # Reapply manual rate if move exists and rate is set
        for payment in self:
            if payment.use_manual_rate and payment.manual_currency_rate and payment.move_id:
                if not self.env.context.get('skip_manual_rate_apply'):
                    payment._apply_manual_rate_to_move()
        
        return res


class AccountMove(models.Model):
    """Extend account.move for payment moves to use manual rate."""
    _inherit = 'account.move'

    def _recompute_dynamic_lines(self, recompute_all_taxes=False, recompute_tax_base_amount=False):
        """Override to preserve manual exchange rate in payment moves."""
        # Don't apply manual rate during recomputation to avoid loops
        if self.env.context.get('skip_manual_rate_apply'):
            return super()._recompute_dynamic_lines(recompute_all_taxes, recompute_tax_base_amount)
        
        # Store manual rate info before recomputation
        manual_rates = {}
        for move in self:
            if move.payment_id and move.payment_id.use_manual_rate and move.payment_id.manual_currency_rate:
                manual_rates[move.id] = move.payment_id.manual_currency_rate
        
        # Call parent
        res = super()._recompute_dynamic_lines(recompute_all_taxes, recompute_tax_base_amount)
        
        # Restore manual rates if needed
        for move in self:
            if move.id in manual_rates and manual_rates[move.id]:
                manual_rate = manual_rates[move.id]
                company_currency = move.company_id.currency_id
                
                if move.currency_id and move.currency_id != company_currency:
                    # Update all lines with manual rate using SQL
                    self.env.cr.execute("""
                        UPDATE account_move_line
                        SET balance = amount_currency * %s,
                            debit = CASE WHEN amount_currency * %s > 0 THEN amount_currency * %s ELSE 0 END,
                            credit = CASE WHEN amount_currency * %s < 0 THEN -(amount_currency * %s) ELSE 0 END
                        WHERE move_id = %s 
                            AND currency_id != %s
                            AND amount_currency != 0
                    """, (
                        manual_rate,
                        manual_rate,
                        manual_rate,
                        manual_rate,
                        manual_rate,
                        move.id,
                        company_currency.id
                    ))
                    
                    # Invalidate cache
                    move.line_ids.invalidate_recordset(['balance', 'debit', 'credit', 'amount_residual', 'amount_residual_currency'])
        
        return res


class AccountMoveLine(models.Model):
    """Extend account.move.line to use manual exchange rate from payment."""
    _inherit = 'account.move.line'

    @api.depends('amount_currency', 'currency_id', 'company_id', 'move_id.date',
                 'move_id.payment_id', 'move_id.payment_id.use_manual_rate', 
                 'move_id.payment_id.manual_currency_rate')
    def _compute_currency_rate(self):
        """Override to use manual exchange rate from payment."""
        for line in self:
            # Check if this line belongs to a payment with manual rate
            if (line.move_id.payment_id and 
                line.move_id.payment_id.use_manual_rate and 
                line.move_id.payment_id.manual_currency_rate and
                line.move_id.payment_id.manual_currency_rate > 0):
                # Use manual rate from payment
                line.currency_rate = line.move_id.payment_id.manual_currency_rate
            else:
                # Use standard currency rate computation
                super(AccountMoveLine, line)._compute_currency_rate()
    
    @api.model
    def _get_query_currency_table(self, options):
        """Override to inject manual rates into currency table for payments."""
        query, params = super()._get_query_currency_table(options)
        
        # Add manual payment rates to the currency table
        # This ensures reconciliation uses the correct rate
        manual_rate_sql = """
            UNION ALL
            SELECT
                ap.currency_id as currency_id,
                %s as company_id,
                ap.manual_currency_rate as rate,
                am.date as date_start,
                am.date as date_end
            FROM account_payment ap
            JOIN account_move am ON am.id = ap.move_id
            WHERE ap.use_manual_rate = true
                AND ap.manual_currency_rate > 0
                AND ap.company_id = %s
        """
        
        if options.get('company_id'):
            company_id = options['company_id']
            query = query.rstrip(';') + manual_rate_sql
            params = params + [company_id, company_id]
        
        return query, params
    
    def _prepare_reconciliation_partials(self):
        """Override to ensure both payment and invoice use same manual rate."""
        # Collect manual rates from both payment and invoice/bill
        payment_rate = None
        invoice_rate = None
        
        for line in self:
            # Check payment lines for manual rate
            if (line.move_id.payment_id and 
                line.move_id.payment_id.use_manual_rate and 
                line.move_id.payment_id.manual_currency_rate and
                line.move_id.payment_id.manual_currency_rate > 0):
                payment_rate = line.move_id.payment_id.manual_currency_rate
            
            # Check invoice/bill lines for manual rate
            if line.move_id.is_exchange and line.move_id.rate and line.move_id.rate > 0:
                invoice_rate = line.move_id.rate
        
        # If both have manual rates and they match, use that rate for reconciliation
        # This prevents exchange differences when rates are the same
        if payment_rate and invoice_rate and abs(payment_rate - invoice_rate) < 0.0001:
            self = self.with_context(
                manual_reconciliation_rate=payment_rate,
                skip_exchange_difference=True
            )
        
        return super()._prepare_reconciliation_partials()
    
    def _prepare_exchange_difference_move_vals(self, amounts_list, company=None, exchange_date=None, **kwargs):
        """Override to prevent exchange difference when using same manual rate."""
        # Check if all reconciled lines use the same manual rate
        bill_rate = None
        payment_rate = None
        
        for line in self:
            # Check if this is a bill/invoice with manual rate
            if line.move_id.is_exchange and line.move_id.rate and line.move_id.rate > 0:
                bill_rate = line.move_id.rate
            
            # Check if this is a payment with manual rate
            if (line.move_id.payment_id and 
                line.move_id.payment_id.use_manual_rate and 
                line.move_id.payment_id.manual_currency_rate and
                line.move_id.payment_id.manual_currency_rate > 0):
                payment_rate = line.move_id.payment_id.manual_currency_rate
        
        # Check context first
        if self.env.context.get('skip_exchange_difference'):
            return {}
        
        # If bill and payment both use manual rate and they are the same, no exchange difference
        if bill_rate and payment_rate and abs(bill_rate - payment_rate) < 0.0001:
            # Both use the same manual rate, skip exchange difference
            # Return empty dict to prevent exchange difference entry
            return {}
        
        return super()._prepare_exchange_difference_move_vals(amounts_list, company, exchange_date, **kwargs)



