from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountReceiptVoucher(models.Model):
    _name = "account.receipt.voucher"
    _description = "AR Receipt Voucher (Multi-Customer)"
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

    line_ids = fields.One2many("account.receipt.voucher.line", "voucher_id", string="Lines")

    # Computed fields for totals
    amount_total = fields.Monetary(string="Total Amount", currency_field="currency_id", compute="_compute_amount_total", store=True)
    
    # Payment status based on amount paid
    payment_state = fields.Selection([
        ('not_paid', 'Not Paid'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overpaid', 'Over Paid'),
    ], string='Payment Status', compute='_compute_payment_state', store=True, copy=False)
    
    # Amount fields
    amount_paid = fields.Monetary(string='Paid Amount', compute='_compute_amount_paid', store=True)
    amount_residual = fields.Monetary(string='Residual Amount', compute='_compute_amount_residual', store=True)
    
    payment_count = fields.Integer(
        compute="_compute_payment_count",
        string="Payments"
    )

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('buz.account.receipt.voucher') or '/'
        if 'date' not in vals or not vals['date']:
            vals['date'] = fields.Date.context_today(self)
        return super().create(vals)

    def write(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('buz.account.receipt.voucher') or '/'
        return super().write(vals)

    @api.depends("line_ids.amount_to_receive")
    def _compute_amount_total(self):
        for voucher in self:
            voucher.amount_total = sum(line.amount_to_receive for line in voucher.line_ids)

    @api.depends('line_ids.payment_ids')
    def _compute_payment_count(self):
        for rec in self:
            rec.payment_count = len(rec.mapped('line_ids.payment_ids'))

    @api.depends('amount_total')
    def _compute_payment_state(self):
        for voucher in self:
            if voucher.state == 'draft':
                voucher.payment_state = 'not_paid'
            elif voucher.amount_paid == 0:
                voucher.payment_state = 'not_paid'
            elif voucher.amount_paid < voucher.amount_total:
                voucher.payment_state = 'partial'
            elif voucher.amount_paid == voucher.amount_total:
                voucher.payment_state = 'paid'
            else:
                voucher.payment_state = 'overpaid'

    @api.depends('line_ids.payment_ids.state', 'line_ids.payment_ids.amount')
    def _compute_amount_paid(self):
        for voucher in self:
            total_paid = 0
            for line in voucher.line_ids:
                for payment in line.payment_ids:
                    if payment.state == 'posted':
                        total_paid += payment.amount
            voucher.amount_paid = total_paid

    def _compute_amount_residual(self):
        for voucher in self:
            voucher.amount_residual = voucher.amount_total - voucher.amount_paid

    def action_confirm(self):
        """Confirm the voucher - only change the document status to confirmed without creating payments"""
        for voucher in self:
            if voucher.state != 'draft':
                continue
                
            # Set voucher state to confirmed
            voucher.state = 'confirmed'
            
            # Add confirmation message to chatter
            voucher.message_post(body=_("Voucher confirmed. Payments must be registered separately."))
        return True

    def _reconcile_payment_with_invoices(self, payment, invoices):
        """Reconcile the payment with the provided invoices"""
        import logging
        _logger = logging.getLogger(__name__)
        
        if not payment or not invoices:
            _logger.warning("Payment or invoices missing for reconciliation")
            return
        
        # Get the payment's move lines (both outstanding and receivable)
        payment_move_lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type in ('asset_receivable', 'liability_payable') or
                        line.account_id.reconcile is True
        )
        
        if not payment_move_lines:
            _logger.warning("No reconcilable lines found for payment %s" % payment.name)
            return
        
        # Get the invoice move lines that are receivable and not fully reconciled
        invoice_move_lines = self.env['account.move.line']
        for invoice in invoices:
            # Get receivable lines for customer invoices
            inv_lines = invoice.line_ids.filtered(
                lambda line: line.account_id.account_type == 'asset_receivable' and 
                            not line.reconciled and
                            line.account_id.reconcile is True
            )
            invoice_move_lines |= inv_lines
            
            # Also check for customer refunds (credit notes)
            if invoice.move_type == 'out_refund':
                refund_lines = invoice.line_ids.filtered(
                    lambda line: line.account_id.account_type == 'liability_payable' and
                                not line.reconciled and
                                line.account_id.reconcile is True
                )
                invoice_move_lines |= refund_lines
        
        if not invoice_move_lines:
            _logger.info("No unreconciled invoice lines found to reconcile with payment %s" % payment.name)
            return
        
        # Try to reconcile
        try:
            # Get all unreconciled lines from both payment and invoices
            lines_to_reconcile = (payment_move_lines + invoice_move_lines).filtered(
                lambda line: not line.reconciled
            )
            
            # Group by account and partner for reconciliation
            if len(lines_to_reconcile) > 1:
                # Filter to only lines on the same account and partner
                accounts = lines_to_reconcile.mapped('account_id')
                for account in accounts:
                    if not account.reconcile:
                        continue
                    
                    account_lines = lines_to_reconcile.filtered(lambda l: l.account_id == account)
                    if len(account_lines) > 1:
                        _logger.info("Attempting to reconcile %d lines on account %s" % (len(account_lines), account.code))
                        account_lines.reconcile()
                        _logger.info("Successfully reconciled lines on account %s" % account.code)
        except Exception as e:
            _logger.error("Error during reconciliation: %s" % str(e))
            # Don't raise the error, just log it so the voucher can still be confirmed

    def action_register_payments(self):
        """Button action to confirm and register payments"""
        return self.action_confirm()
    
    def action_open_related_payments(self):
        """
        Smart button action to show related payments for this voucher
        """
        self.ensure_one()
        
        # Get all payments linked to lines under this voucher
        payments = self.mapped('line_ids.payment_ids')
        
        action = {
            'name': _('Payments'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', payments.ids)],
        }
        
        # If there's only one payment, open it directly in form view
        if len(payments) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': payments.id,
            })
        
        return action

    def action_reset_to_draft(self):
        """Reset the voucher to draft and reverse any linked payments"""
        for voucher in self:
            if voucher.state != "confirmed":
                continue
                
            # Find payments related to this voucher by looking at the reference
            # Payments are created with ref = f"RV {voucher.name}"
            payments = self.env["account.payment"].search([("ref", "like", f"RV {voucher.name}")])
            
            # Also find payments linked to voucher lines via payment_ids
            line_payments = self.env["account.payment"]
            for line in voucher.line_ids:
                line_payments |= line.payment_ids
            
            # Combine both sets of payments
            all_payments = payments | line_payments
            
            # Process each payment to unreconcile and cancel it
            for payment in all_payments:
                if payment.state == "posted":
                    # Try to unreconcile first
                    try:
                        # Find all move lines that are reconciled with this payment
                        reconciled_lines = self.env["account.move.line"]
                        for line in payment.move_id.line_ids:
                            if line.reconciled:
                                reconciled_lines |= line
                                
                        # Unreconcile if any lines are reconciled
                        if reconciled_lines:
                            reconciled_lines.remove_move_reconcile()
                    except Exception:
                        # If unreconciliation fails, just continue
                        pass
                    
                    # Cancel the payment
                    try:
                        # Reset journal entry to draft first
                        if payment.move_id.state == "posted":
                            # First unreconcile again to ensure we can cancel
                            for line in payment.move_id.line_ids:
                                if line.reconciled:
                                    line.remove_move_reconcile()
                            # Now cancel the move
                            payment.move_id.button_draft()
                            payment.move_id.button_cancel()
                        # Cancel the payment
                        payment.action_cancel()
                    except Exception as e:
                        # Add error message to chatter
                        voucher.message_post(body=_("Could not cancel payment %s: %s") % (payment.name, str(e)))
            
            # Find all related journal entries and cancel them
            related_moves = self.env["account.move"].search([("ref", "like", f"RV {voucher.name}")])
            for move in related_moves:
                if move.state == "posted":
                    try:
                        move.button_draft()
                        move.button_cancel()
                    except Exception as e:
                        voucher.message_post(body=_("Could not cancel journal entry %s: %s") % (move.name, str(e)))
                        
            # Reset voucher state to draft
            voucher.state = "draft"
            
            # Post a message about the reset
            voucher.message_post(body=_("Voucher reset to draft. All related payments and journal entries have been cancelled."))
        
        return True

    def unlink(self):
        """Clear related payment M2M links on voucher lines before deleting the voucher.

        Deleting a voucher may cascade-delete its voucher lines at the database level,
        which can cause a FK constraint if the M2M relation table still references
        those lines. We proactively clear the M2M rows using direct SQL.
        """
        # Collect all line IDs from all vouchers being deleted
        line_ids = self.mapped('line_ids').ids
        if line_ids:
            # Use SQL to directly clear the M2M relation table
            self.env.cr.execute("""
                DELETE FROM account_receipt_voucher_line_payment_rel 
                WHERE voucher_line_id IN %s
            """, (tuple(line_ids),))
        return super(AccountReceiptVoucher, self).unlink()

    def action_view_payments(self):
        """
        Smart button action to show related payments for this voucher
        """
        self.ensure_one()
        
        # Find payments related to this voucher by looking at the reference
        # Payments are created with ref = f"RV {voucher.name}"
        payments = self.env['account.payment'].search([('ref', 'like', f"RV {self.name}")])
        
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


class AccountReceiptVoucherLine(models.Model):
    _name = "account.receipt.voucher.line"
    _description = "AR Receipt Voucher Line"

    voucher_id = fields.Many2one("account.receipt.voucher", string="Receipt Voucher", required=True, ondelete="cascade")
    receipt_id = fields.Many2one("account.receipt", string="Receipt", required=True, domain="[('state', '=', 'posted')]", ondelete='cascade')
    partner_id = fields.Many2one("res.partner", string="Partner", related="receipt_id.partner_id", store=True)
    
    # Amount to receive for this receipt in the voucher
    amount_to_receive = fields.Monetary(
        string="Amount to Receive",
        currency_field="currency_id",
        default=lambda self: 0.0,
        help="Amount to receive from this receipt in the voucher"
    )
    currency_id = fields.Many2one(related="voucher_id.currency_id", store=True, readonly=True)
    
    # Link to related payments
    payment_ids = fields.Many2many(
        'account.payment',
        'account_receipt_voucher_line_payment_rel',
        'voucher_line_id', 'payment_id',
        string='Related Payments',
        readonly=True,
    )
    
    # Payment status for the line
    payment_state = fields.Selection([
        ('not_paid', 'Not Paid'),
        ('in_payment', 'In Payment'),
        ('paid', 'Paid')
    ], compute="_compute_payment_state", store=True)
    
    @api.onchange('receipt_id')
    def _onchange_receipt_id(self):
        """Set the default amount to receive equal to the receipt's total amount"""
        if self.receipt_id:
            # Set to the receipt's total amount initially
            self.amount_to_receive = self.receipt_id.amount_total

    @api.constrains('receipt_id')
    def _check_receipt_company(self):
        """Ensure receipt belongs to the same company as the voucher"""
        for line in self:
            if line.receipt_id and line.voucher_id:
                if line.receipt_id.company_id != line.voucher_id.company_id:
                    raise UserError(
                        _("Receipt %s belongs to company %s, but voucher is for company %s. "
                          "All receipts in a voucher must belong to the same company as the voucher.") % 
                         (line.receipt_id.name, line.receipt_id.company_id.name, line.voucher_id.company_id.name)
                    )

    @api.onchange('partner_id')
    def _onchange_partner_id_set_domain(self):
        """Dynamically set domain for move_id field to filter by partner and company"""
        # This method is just to provide a visual hint; actual validation happens in constraints
        domain = [('partner_id', '=', self.partner_id.id), 
                  ('move_type', 'in', ['in_invoice', 'in_refund']), 
                  ('state', '=', 'posted')]
        if self.voucher_id.company_id:
            domain.append(('company_id', '=', self.voucher_id.company_id.id))
        return {'domain': {'move_id': domain}}

    @api.depends('payment_ids.state')
    def _compute_payment_state(self):
        for line in self:
            if line.payment_ids:
                # Check if all linked payments are posted/reconciled
                if all(payment.state == 'posted' for payment in line.payment_ids):
                    line.payment_state = 'paid'
                elif any(payment.state == 'draft' for payment in line.payment_ids):
                    line.payment_state = 'in_payment'
                else:
                    line.payment_state = 'paid'  # Default to paid if all are confirmed/posted
            else:
                line.payment_state = 'not_paid'

    def action_register_payment_line(self):
        """Open the standard payment wizard for invoices in the related receipt, or show existing payments."""
        self.ensure_one()
        
        # Retrieve the related account.receipt record
        receipt = self.receipt_id
        if not receipt:
            raise UserError(_("No receipt found for this line."))
    
        # Extract all invoices from that receipt that are posted and still have residual amounts
        invoices = receipt.line_ids.filtered(
            lambda line: line.move_id.state == 'posted' and abs(line.move_id.amount_residual_signed) >= 0.01
        ).mapped('move_id')
    
        # Check if payments already exist for this receipt or voucher line
        existing_payments = self.env['account.payment'].search([
            ('partner_id', '=', receipt.partner_id.id),
            ('state', '=', 'posted'),
            ('payment_type', '=', 'inbound'),
            '|',
            ('receipt_ids', 'in', [receipt.id]),
            ('id', 'in', self.payment_ids.ids)
        ])
    
        # If no unpaid invoices but payments exist, try to reconcile them automatically
        if not invoices and existing_payments:
            # Get all invoices from the receipt (even if partially paid)
            all_invoices = receipt.line_ids.filtered(
                lambda line: line.move_id.state == 'posted'
            ).mapped('move_id')
        
            if all_invoices:
                # Try to reconcile existing payments with invoices
                reconciled_any = False
                for payment in existing_payments:
                    try:
                        self.voucher_id._reconcile_payment_with_invoices(payment, all_invoices)
                        reconciled_any = True
                    except Exception as e:
                        _logger.warning("Failed to auto-reconcile payment %s: %s" % (payment.name, str(e)))
            
                if reconciled_any:
                    # Link payments to this voucher line if not already linked
                    self.write({'payment_ids': [(6, 0, existing_payments.ids)]})
                
                    # Force recompute payment_state on all invoices
                    all_invoices._compute_amount()
                
                    # Flush to database to ensure payment state is updated
                    all_invoices.flush_recordset()
                
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Success'),
                            'message': _('Payments reconciled successfully'),
                            'type': 'success',
                            'sticky': False,
                        }
                    }
        
            # If reconciliation failed or no invoices, show the payments
            return {
                'name': _('Existing Payments'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', existing_payments.ids)],
                'context': {'create': False},
                'target': 'current',
            }
    
        # If no unpaid invoices and no existing payments, raise error
        if not invoices and not existing_payments:
            raise UserError(_("There are no posted invoices with outstanding amounts in this receipt and no existing payments found."))
    
        # If there are unpaid invoices, open payment wizard
        # Prepare context for the payment register wizard
        ctx = {
            'active_model': 'account.move',
            'active_ids': invoices.ids,
            'default_communication': f"Receipt {receipt.name}",
            'default_payment_date': self.voucher_id.date,
            'default_payment_type': 'inbound',
            # Pass the voucher line ID so we can link the payment after creation
            'buz_voucher_line_id': self.id,
            # Pass the receipt ID as well, so payment can be linked to receipt too
            'buz_receipt_id': receipt.id,
        }
    
        # Try to get and set default journal if available
        default_journal = self.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', self.voucher_id.company_id.id)
        ], limit=1)
    
        if default_journal:
            ctx['default_journal_id'] = default_journal.id
            
        # Prepare the action to open the payment register wizard
        action = {
            'name': _('Register Payment'),
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'view_id': self.env.ref('account.view_account_payment_register_form').id,
            'target': 'new',
            'type': 'ir.actions.act_window',
            'context': ctx,
        }
    
        return action

    def action_reconcile_existing_payments(self):
        """Reconcile existing outstanding payments with invoices in the receipt."""
        self.ensure_one()
    
        # Get the receipt
        receipt = self.receipt_id
        if not receipt:
            raise UserError(_("No receipt found for this line."))
    
        # Get existing payments
        existing_payments = self.payment_ids.filtered(lambda p: p.state == 'posted')
    
        if not existing_payments:
            raise UserError(_("No posted payments found to reconcile."))
    
        # Get all invoices from the receipt
        invoices = receipt.line_ids.mapped('move_id').filtered(
            lambda m: m.state == 'posted' and m.move_type in ('out_invoice', 'out_refund')
        )
    
        if not invoices:
            raise UserError(_("No posted invoices found in this receipt to reconcile."))
    
        # Reconcile each payment with the invoices
        reconciled_count = 0
        for payment in existing_payments:
            try:
                # Use the existing reconciliation method from voucher
                self.voucher_id._reconcile_payment_with_invoices(payment, invoices)
                reconciled_count += 1
                
                # Log in chatter
                self.voucher_id.message_post(
                    body=_("Payment %s reconciled with invoices from receipt %s") % (payment.name, receipt.name)
                )
            except Exception as e:
                _logger.warning("Failed to reconcile payment %s: %s" % (payment.name, str(e)))
    
        if reconciled_count > 0:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('%d payment(s) reconciled successfully.') % reconciled_count,
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            raise UserError(_("Failed to reconcile payments. Please check the payment and invoice details."))

    @api.constrains('receipt_id', 'voucher_id')
    def _check_duplicate_receipt(self):
        """Ensure that the same receipt is not added multiple times to the same voucher"""
        for line in self:
            if line.receipt_id and line.voucher_id:
                duplicate_lines = self.search([
                    ('receipt_id', '=', line.receipt_id.id),
                    ('voucher_id', '=', line.voucher_id.id),
                    ('id', '!=', line.id)
                ])
                if duplicate_lines:
                    raise UserError(_("Receipt %s is already included in this voucher.") % line.receipt_id.name)

    def unlink(self):
        """Ensure Many2many links to payments are removed before deleting voucher lines.

        Postgres will prevent deleting a record that is referenced by a foreign key
        from the M2M relation table. We explicitly clear the relation rows so the
        voucher line can be removed.
        """
        # Store IDs and clear M2M relations before deletion
        if self:
            # Use SQL to directly clear the M2M relation table
            self.env.cr.execute("""
                DELETE FROM account_receipt_voucher_line_payment_rel 
                WHERE voucher_line_id IN %s
            """, (tuple(self.ids),))
        return super(AccountReceiptVoucherLine, self).unlink()