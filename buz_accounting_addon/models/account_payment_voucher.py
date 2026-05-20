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
        ("posted", "Posted"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True)

    billing_note = fields.Char(string="Billing Note", tracking=True)

    partner_id = fields.Many2one("res.partner", string="Vendor", required=True, domain=[("supplier_rank", ">", 0)], tracking=True)
    line_ids = fields.One2many("account.payment.voucher.line", "voucher_id", string="Lines")

    # Payment Planning Fields
    payment_type = fields.Selection([
        ('cash', 'Cash'),
        ('transfer', 'Transfer'),
        ('check', 'Check'),
    ], string="Payment Type", default='transfer', tracking=True)
    destination_journal_id = fields.Many2one(
        'account.journal', 
        string="Payment Journal", 
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        tracking=True
    )
    payment_method_line_id = fields.Many2one(
        'account.payment.method.line', 
        string="Payment Method",
        domain="[('payment_type', '=', 'outbound'), ('journal_id', '=', destination_journal_id)]",
        tracking=True
    )
    bank_free_dis = fields.Monetary(
        string="Bank Fee",
        currency_field="currency_id",
        help="Optional bank fee deducted by the bank."
    )
    check_number = fields.Char(string="Check Number", tracking=True)
    check_date = fields.Date(string="Check Date", tracking=True)
    check_pay_to = fields.Char(string="Pay to in name of", tracking=True)

    # Computed fields for totals
    amount_total_gross = fields.Monetary(string="Total Gross", currency_field="currency_id", compute="_compute_amount_totals", store=True)
    amount_total_wht = fields.Monetary(string="Total WHT", currency_field="currency_id", compute="_compute_amount_totals", store=True)
    amount_total_net = fields.Monetary(string="Total Net", currency_field="currency_id", compute="_compute_amount_totals", store=True)
    amount_total_bank_fee = fields.Monetary(string="Total Bank Fee", currency_field="currency_id", compute="_compute_amount_totals", store=True)
    
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
    
    # Payment count field
    payment_count = fields.Integer(
        compute="_compute_payment_count",
        string="Payments"
    )

    @api.constrains('line_ids', 'partner_id')
    def _check_partner_consistency(self):
        for voucher in self:
            if any(line.partner_id != voucher.partner_id for line in voucher.line_ids):
                raise UserError(_("All lines in a payment voucher must belong to the same vendor (%s).") % voucher.partner_id.name)

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('buz.account.payment.voucher') or '/'
        if 'date' not in vals or not vals['date']:
            vals['date'] = fields.Date.context_today(self)
        return super().create(vals)

    def write(self, vals):
        if vals.get('name') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('buz.account.payment.voucher') or '/'
        return super().write(vals)

    @api.depends("line_ids.amount_to_pay_gross", "line_ids.wht_amount", "bank_free_dis")
    def _compute_amount_totals(self):
        for voucher in self:
            voucher.amount_total_gross = sum(line.amount_to_pay_gross for line in voucher.line_ids)
            voucher.amount_total_wht = sum(line.wht_amount for line in voucher.line_ids)
            voucher.amount_total_net = sum(line.amount_to_pay_net for line in voucher.line_ids)
            voucher.amount_total_bank_fee = voucher.bank_free_dis or 0.0

    @api.depends('amount_total_net', 'line_ids.payment_state')
    def _compute_payment_state(self):
        for voucher in self:
            # Get the payment states of all lines in the voucher
            line_payment_states = voucher.line_ids.mapped('payment_state')
            
            # If all lines are 'paid', set the voucher as 'paid'
            if all(state == 'paid' for state in line_payment_states if state):
                voucher.payment_state = 'paid'
            # If all lines are 'not_paid', set the voucher as 'not_paid'  
            elif all(state == 'not_paid' for state in line_payment_states if state):
                voucher.payment_state = 'not_paid'
            # If there's a mix of states or some lines are partially paid, set as 'partial'
            elif 'partial' in line_payment_states or any(state not in ['paid', 'not_paid'] for state in line_payment_states):
                voucher.payment_state = 'partial'
            # Check if any line is in 'in_payment' state
            elif 'in_payment' in line_payment_states:
                voucher.payment_state = 'partial'
            else:
                # Default to not paid
                voucher.payment_state = 'not_paid'

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
            voucher.amount_residual = voucher.amount_total_net - voucher.amount_paid

    @api.depends('name')
    def _compute_payment_count(self):
        for rec in self:
            rec.payment_count = self.env['account.payment'].search_count([('ref', '=', f"PV {rec.name}")])

    def action_open_related_payments(self):
        """
        Smart button action to show related payments for this voucher
        """
        self.ensure_one()
        
        # Get payments linked to this voucher via reference
        payments = self.env['account.payment'].search([('ref', '=', f"PV {self.name}")])
        
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

    def action_confirm(self):
        """Confirm and post the voucher (Draft -> Posted)"""
        for voucher in self:
            if voucher.state != 'draft':
                continue
            voucher.write({
                'state': 'posted',
            })
            voucher.message_post(body=_("Voucher confirmed and posted."))
        return True
    
    @api.onchange('cheque_book_id')
    def _onchange_cheque_book_id(self):
        if self.cheque_book_id:
            self.check_number = self.cheque_book_id.next_number
    
    @api.onchange('partner_id')
    def _onchange_partner_id_check(self):
        if self.partner_id and not self.check_pay_to:
            self.check_pay_to = self.partner_id.name

    def action_register_batch_payment(self):
        """Open payment register wizard with WHT handling (Thai Localization support)"""
        self.ensure_one()
        
        # Check if voucher is posted
        if self.state != 'posted':
             raise UserError(_("Voucher must be posted before registering payment."))
             
        # Increment Cheque Book Next Number if used
        if self.payment_type == 'check' and hasattr(self, 'cheque_book_id') and self.cheque_book_id and self.check_number == self.cheque_book_id.next_number:
            try:
                next_num = int(self.cheque_book_id.next_number) + 1
                self.cheque_book_id.next_number = str(next_num).zfill(len(self.cheque_book_id.next_number))
            except (ValueError, TypeError):
                pass
             
        moves = self.line_ids.mapped('move_id')
        if not moves:
            raise UserError(_("No bills found to pay."))
            
        # Helper variables
        total_wht = self.amount_total_wht
        total_net = self.amount_total_net
        total_gross = self.amount_total_gross
        
        ctx = {
            'active_model': 'account.move',
            'active_ids': moves.ids,
            'default_group_payment': True,
        }
        
        # Set default journal from voucher
        if self.destination_journal_id:
            ctx['default_journal_id'] = self.destination_journal_id.id
        
        # If WHT exists, use Thai Localization WHT from voucher line directly
        if total_wht > 0:
             # Get WHT config directly from voucher line (already account.withholding.tax)
             first_wht_line = self.line_ids.filtered(lambda l: l.wht_amount > 0)[:1]
             
             if first_wht_line and first_wht_line.buz_wht_tax_id:
                 # Use WHT config directly from voucher line
                 wht_tax_config = first_wht_line.buz_wht_tax_id
                 ctx.update({
                     'default_wht_tax_id': wht_tax_config.id,
                     'default_wht_amount_base': sum(line.wht_base_amount for line in self.line_ids.filtered(lambda l: l.wht_amount > 0)),
                     'default_amount': total_net,
                     'default_payment_difference_handling': 'reconcile',
                     'default_writeoff_account_id': wht_tax_config.account_id.id,
                     'default_writeoff_label': wht_tax_config.name,
                     'force_amount': total_net,
                 })
             else:
                 # FALLBACK: Generic Write-off to Account 213102
                 wht_payable_account = self.env['account.account'].search([
                    ('code', '=', '213102'),
                    ('company_id', '=', self.company_id.id)
                 ], limit=1)
                 
                 if not wht_payable_account:
                     raise UserError(_("Configuration Error: No WHT Payable Account found (213102). Please configure your WHT Tax or Account."))
                     
                 ctx.update({
                     'default_amount': total_net,
                     'default_payment_difference_handling': 'reconcile_account',
                     'default_writeoff_account_id': wht_payable_account.id,
                     'default_writeoff_label': _('Withholding Tax'),
                     'force_amount': total_net,
                 })

        # Set communication/ref to link back to this voucher
        ctx['default_communication'] = f"PV {self.name}"

        return {
            'name': _('Register Payment'),
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'context': ctx,
            'target': 'new',
            'type': 'ir.actions.act_window',
        }


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


    def _create_wht_certificates(self, wht_lines, payment, partner):
        """
        Create WHT certificates for payment with withholding tax.
        
        This method bridges Payment Voucher with l10n_th_account_tax module's
        certificate creation mechanism.
        
        Args:
            wht_lines: Payment voucher lines with WHT
            payment: The account.payment record
            partner: The vendor partner
        """
        if not payment or not wht_lines:
            return self.env['withholding.tax.cert'].browse()
        
        # Ensure payment is posted
        if payment.state != 'posted':
            _logger.warning(f"Payment {payment.name} is not posted yet, cannot create WHT certificates")
            return self.env['withholding.tax.cert'].browse()
        
        # Check if WHT certificate already exists for this payment
        existing_certs = self.env['withholding.tax.cert'].search([
            ('payment_id', '=', payment.id)
        ])
        
        if existing_certs:
            _logger.info(f"WHT certificates already exist for payment {payment.name}: {existing_certs.mapped('name')}")
            self.message_post(
                body=_("WHT Certificate(s) already exist: %s") % ', '.join(existing_certs.mapped('name'))
            )
            return existing_certs
        
        # Check if withholding.tax.cert model is available
        try:
            self.env['withholding.tax.cert']
        except KeyError:
            _logger.error("Withholding tax models not available - l10n_th_account_tax module may not be installed")
            raise UserError(_("Withholding Tax Certificate feature is not available. Please install l10n_th_account_tax module."))
        
        # Get journal entry
        move = payment.move_id
        if not move:
            raise UserError(_("Payment %s has no journal entry.") % payment.name)
        
        voucher_lines = wht_lines.filtered(lambda line: line.wht_amount > 0 and line.buz_wht_tax_id)
        if not voucher_lines:
            raise UserError(_(
                "Cannot create WHT certificate for payment %s\n\n"
                "No voucher lines with WHT tax were found."
            ) % payment.name)
        
        # Now create certificates using standard method
        try:
            created_certs = self._create_wht_certs_from_voucher_lines(
                voucher_lines, payment, partner
            )
            if created_certs:
                _logger.info(
                    "Successfully created %d WHT certificate(s) for payment %s",
                    len(created_certs),
                    payment.name,
                )
                self.message_post(
                    body=_("WHT Certificate(s) created: %s") % ', '.join(created_certs.mapped('name'))
                )
                return created_certs

            raise UserError(_(
                "WHT certificate creation completed but no certificates were found.\n"
                "Please check payment %s manually."
            ) % payment.name)

        except UserError:
            raise
        except Exception as e:
            _logger.error("Error calling create_wht_cert(): %s", str(e), exc_info=True)
            raise UserError(_(
                "Failed to create WHT certificate for payment %s:\n%s\n\n"
                "Please check the system log for details."
            ) % (payment.name, str(e)))

    def _create_wht_certs_from_voucher_lines(self, voucher_lines, payment, partner):
        """Create WHT certificates directly from payment voucher lines."""
        self.ensure_one()
        if not voucher_lines:
            return self.env["withholding.tax.cert"].browse()

        income_type_labels = dict(self.env["withholding.tax.cert.line"]._fields["wht_cert_income_type"].selection)
        cert_line_vals = []
        wht_tax_set = set()
        for voucher_line in voucher_lines:
            wht_tax = voucher_line.buz_wht_tax_id
            income_type = wht_tax.wht_cert_income_type or "5"
            cert_line_vals.append(
                (0, 0, {
                    "wht_cert_income_type": income_type,
                    "wht_cert_income_desc": income_type_labels.get(income_type, wht_tax.display_name),
                    "base": abs(voucher_line.wht_base_amount or 0.0),
                    "amount": abs(voucher_line.wht_amount or 0.0),
                    "wht_tax_id": wht_tax.id,
                })
            )
            wht_tax_set.add(wht_tax.id)

        cert_vals = {
            "move_id": payment.move_id.id,
            "payment_id": payment.id,
            "partner_id": partner.id,
            "date": payment.date,
            "wht_line": cert_line_vals,
        }
        wht_tax = self.env["account.withholding.tax"].browse(list(wht_tax_set))
        income_tax_form = wht_tax.mapped("income_tax_form")
        if len(income_tax_form) == 1:
            cert_vals["income_tax_form"] = income_tax_form[0]

        cert = self.env["withholding.tax.cert"].create(cert_vals)
        return cert


    
    def action_view_payments(self):
        """
        Smart button action to show related payments for this voucher
        """
        self.ensure_one()
        
        # Find payments related to this voucher by looking at the reference
        # Payments are created with ref = f"PV {voucher.name}"
        payments = self.env['account.payment'].search([('ref', '=', f"PV {self.name}")])
        
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

    def action_reset_to_draft(self):
        """Reset the voucher to draft and cancel ONLY payments created by this voucher"""
        for voucher in self:
            if voucher.state == "draft":
                continue
            
            # Guard: skip payment cancellation if voucher has no proper name
            if not voucher.name or voucher.name == '/':
                _logger.warning("Voucher %s has no proper name, skipping payment cancellation", voucher.id)
                voucher.write({'state': 'draft'})
                voucher.message_post(body=_("Voucher reset to draft (no payments to cancel)."))
                continue
            
            pv_ref = f"PV {voucher.name}"
            _logger.info("=== RESET TO DRAFT: Voucher %s (ref=%s) ===", voucher.name, pv_ref)
            
            # Find payments related to this voucher by EXACT reference match
            all_payments = self.env["account.payment"].search([("ref", "=", pv_ref)])
            _logger.info("Found %d payment(s) with ref='%s': %s", 
                        len(all_payments), pv_ref, 
                        all_payments.mapped('name'))
            
            # Extra safety: only cancel payments that also match the voucher's journal
            payments_to_cancel = all_payments
            if voucher.destination_journal_id:
                payments_to_cancel = all_payments.filtered(
                    lambda p: p.journal_id == voucher.destination_journal_id
                )
                _logger.info("After journal filter (%s): %d payment(s) to cancel: %s", 
                            voucher.destination_journal_id.name,
                            len(payments_to_cancel), 
                            payments_to_cancel.mapped('name'))
            
            # Process each payment to unreconcile and cancel it
            cancelled_payments = []
            for payment in payments_to_cancel:
                if payment.state == 'cancel':
                    _logger.info("Payment %s already cancelled, skipping", payment.name)
                    continue
                try:
                    _logger.info("Cancelling payment %s (state=%s)", payment.name, payment.state)
                    
                    # 1. Unreconcile (remove links to invoices)
                    if payment.move_id:
                        reconciled_lines = payment.move_id.line_ids.filtered(lambda l: l.reconciled)
                        if reconciled_lines:
                            _logger.info("Unreconciling %d line(s) for payment %s", len(reconciled_lines), payment.name)
                            reconciled_lines.remove_move_reconcile()
                    
                    # 2. Reset to Draft (required before cancelling if posted)
                    if payment.state == 'posted':
                        payment.action_draft()
                    
                    # 3. Cancel
                    payment.action_cancel()
                    cancelled_payments.append(payment.name)
                    _logger.info("Successfully cancelled payment %s", payment.name)
                    
                except Exception as e:
                    _logger.error("Failed to cancel payment %s: %s", payment.name, str(e))
                    voucher.message_post(body=_("Could not cancel payment %s: %s") % (payment.name, str(e)))
            
            # Reset voucher state to draft
            voucher.write({'state': 'draft'})
            
            # Post a message about the reset
            if cancelled_payments:
                voucher.message_post(body=_("Voucher reset to draft. Cancelled payments: %s") % ', '.join(cancelled_payments))
            else:
                voucher.message_post(body=_("Voucher reset to draft. No payments found to cancel."))
            
            _logger.info("=== RESET TO DRAFT COMPLETE: Voucher %s ===", voucher.name)
        
        return True

    def get_preview_moves(self):
        """
        Compute simulated journal entry lines for the report.
        Returns a list of dicts: { 'code', 'name', 'ref', 'date', 'debit', 'credit' }
        """
        self.ensure_one()
        lines = []
        date = self.date
        voucher_name = self.name
        
        # Calculate totals
        total_gross = sum(line.amount_to_pay_gross for line in self.line_ids)
        total_wht = sum(line.wht_amount for line in self.line_ids)
        total_net = sum(line.amount_to_pay_net for line in self.line_ids)
        bank_fee = self.bank_free_dis or 0.0
        total_disbursement = total_net + bank_fee

        # 1. Debit Line (Payable) - Aggregated
        if total_gross > 0:
            # Attempt to find the correct payable account from the first bill
            # Since all bills must belong to the same vendor, the payable account acts as the GL control account
            if self.line_ids and self.line_ids[0].move_id:
                first_move = self.line_ids[0].move_id
                payable_line = first_move.line_ids.filtered(lambda l: l.account_type == 'liability_payable')[:1]
                account = payable_line.account_id or first_move.partner_id.property_account_payable_id
            else:
                account = self.partner_id.property_account_payable_id or self.env['account.account']
            
            lines.append({
                'code': account.code,
                'name': account.name,
                'ref': voucher_name,
                'date': date,
                'debit': total_gross,
                'credit': 0.0,
            })

        # 2. Credit Line (WHT)
        if total_wht > 0:
            # 1. Specific Account Code (213102)
            wht_account = self.env['account.account'].search([
                ('code', '=', '213102'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)

            # 2. Search by Name/Code pattern if not found
            if not wht_account:
                wht_account = self.env['account.account'].search([
                    ('code', '=ilike', '%wht%payable%'),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)
            
            # 3. Fallback to generic liability
            if not wht_account:
                wht_account = self.env['account.account'].search([
                    ('account_type', '=', 'liability_current'),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)
                
            lines.append({
                'code': wht_account.code if wht_account else '213102',
                'name': wht_account.name if wht_account else 'ภาษีหัก ณ ที่จ่ายค้างจ่าย',
                'ref': voucher_name,
                'date': date,
                'debit': 0.0,
                'credit': total_wht,
            })

        # 3. Debit Line (Bank Fee Expense)
        if bank_fee > 0:
            bank_fee_account = self.env['account.account'].search([
                ('code', '=', '533201'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            if not bank_fee_account:
                bank_fee_account = self.env['account.account'].search([
                    ('account_type', '=', 'expense'),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)

            lines.append({
                'code': bank_fee_account.code if bank_fee_account else '533201',
                'name': bank_fee_account.name if bank_fee_account else _('Bank Fee Expense'),
                'ref': voucher_name,
                'date': date,
                'debit': bank_fee,
                'credit': 0.0,
            })

        # 4. Credit Line (Bank/Cash)
        bank_journal = self.destination_journal_id
        if bank_journal:
            # Use default account of the journal
            bank_account = bank_journal.default_account_id
            if not bank_account: # Try to find from inbound/outbound payment method lines if complex
                 bank_account = bank_journal.outbound_payment_method_line_ids[:1].payment_account_id
            
            lines.append({
                'code': bank_account.code if bank_account else '???',
                'name': bank_account.name if bank_account else bank_journal.name,
                'ref': voucher_name,
                'date': date,
                'debit': 0.0,
                'credit': total_disbursement,
            })
            
        return lines

class AccountPaymentVoucherLine(models.Model):
    _name = "account.payment.voucher.line"
    _description = "AP Payment Voucher Line"

    voucher_id = fields.Many2one("account.payment.voucher", string="Payment Voucher", required=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", string="Vendor", domain=[("supplier_rank", ">", 0)], related="voucher_id.partner_id", store=True)
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
    
    # WHT fields (Thailand-specific) - using l10n_th_account_tax module
    buz_wht_tax_id = fields.Many2one(
        'account.withholding.tax',  # Thai localization WHT
        string="WHT Tax",
        check_company=True
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
    company_id = fields.Many2one(related="voucher_id.company_id", store=True, readonly=True)
    
    # Link to related payments
    payment_ids = fields.Many2many(
        'account.payment',
        string='Related Payments',
        compute='_compute_payment_ids',
        readonly=True,
    )
    
    @api.depends('move_id.payment_state')
    def _compute_payment_ids(self):
        for line in self:
            payments = self.env['account.payment']
            if line.move_id:
                # 1. Try standard helper
                payments |= line.move_id._get_reconciled_payments()
                # 2. Try inverse search on payments (robust for batch/grouped payments)
                payments |= self.env['account.payment'].search([('reconciled_invoice_ids', 'in', line.move_id.id)])
            
            line.payment_ids = payments
    
    # Payment status for the line
    payment_state = fields.Selection([
        ('not_paid', 'Not Paid'),
        ('in_payment', 'In Payment'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid')
    ], compute="_compute_payment_state", store=True)

    @api.onchange('move_id')
    def _onchange_move_id(self):
        """Set the default amount to pay equal to the bill's residual amount"""
        if self.move_id:
            # Use signed residual for correct handling of refunds
            self.amount_to_pay_gross = abs(self.move_id.amount_residual_signed)
            # Set WHT base amount to the Untaxed Amount (Base)
            # This handles cases where the bill includes VAT (we don't withhold on VAT)
            self.wht_base_amount = abs(self.move_id.amount_untaxed_signed)

    # Removed _onchange_amount_to_pay_gross to prevent overwriting correct base with gross (which might include VAT)

    @api.onchange('buz_wht_tax_id')
    def _onchange_wht_tax(self):
        """Update WHT rate when tax is selected"""
        if self.buz_wht_tax_id:
            # account.withholding.tax uses 'amount' as percentage (e.g., 3 for 3%)
            self.wht_rate = self.buz_wht_tax_id.amount / 100.0
        else:
            self.wht_rate = 0.0

    @api.depends('wht_base_amount', 'wht_rate', 'buz_wht_tax_id')
    def _compute_wht_amount(self):
        for line in self:
            # Ensure WHT amount is always positive to guarantee deduction
            line.wht_amount = abs(line.wht_base_amount * line.wht_rate)

    @api.depends('amount_to_pay_gross', 'wht_amount')
    def _compute_amount_to_pay_net(self):
        for line in self:
            # Ensure WHT is always deducted
            line.amount_to_pay_net = line.amount_to_pay_gross - abs(line.wht_amount)

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

    @api.depends('move_id.payment_state', 'payment_ids.state')
    def _compute_payment_state(self):
        for line in self:
            if line.move_id:
                # Derive payment state from the bill itself for accuracy
                bill_payment_state = line.move_id.payment_state
                if bill_payment_state:
                    # Map bill payment states to voucher line payment states
                    # account.move may have states like 'reversed', 'overpaid' that we need to handle
                    if bill_payment_state in ('not_paid', 'in_payment', 'partial', 'paid'):
                        line.payment_state = bill_payment_state
                    elif bill_payment_state == 'reversed':
                        line.payment_state = 'paid'  # Reversed bills are considered paid
                    elif bill_payment_state == 'overpaid':
                        line.payment_state = 'paid'  # Overpaid bills are considered paid
                    else:
                        # For any other unknown states, default to not_paid
                        line.payment_state = 'not_paid'
                else:
                    # Fallback to payment-based logic if bill state is not available
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
            else:
                # If no bill is associated, default to not_paid
                line.payment_state = 'not_paid'

    def action_register_payment_line(self):
        """Open bill in popup window for verification."""
        self.ensure_one()
        
        if not self.move_id:
            raise UserError(_("Please select a bill first."))
            
        # Validate the bill
        if self.move_id.state != 'posted':
            raise UserError(_("Bill %s is not in 'Posted' state.") % self.move_id.name)
        
        if self.move_id.move_type not in ['in_invoice', 'in_refund']:
            raise UserError(_("Selected document is not a vendor bill or refund."))
            
        # Open the bill in popup window
        return {
            'name': _('Bill Details - %s') % self.move_id.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
            'target': 'new',
            'context': {
                'default_move_type': self.move_id.move_type,
                'create': False,
                'edit': False,
            },
            'flags': {
                'mode': 'readonly',
            }
        }

    @api.constrains('wht_rate')
    def _check_wht_rate(self):
        """Ensure WHT rate is between 0 and 1"""
        for line in self:
            if line.wht_rate < 0 or line.wht_rate > 1:
                raise UserError(_("WHT rate must be between 0 and 1 (e.g., 0.03 for 3%)"))
