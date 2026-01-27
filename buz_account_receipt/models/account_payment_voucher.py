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
        ("prepared", "Prepared"),
        ("checked1", "Checked (1)"),
        ("checked2", "Checked (2)"),
        ("approved", "Approved (1)"),
        ("approved2", "Approved (2)"),
        ("posted", "Posted"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True)

    # Tracking Fields
    prepared_by = fields.Many2one('res.users', string="Prepared By", tracking=True, copy=False)
    prepared_date = fields.Date(string="Prepared Date", tracking=True, copy=False)
    
    checked1_by = fields.Many2one('res.users', string="Checked (1) By", tracking=True, copy=False)
    checked1_date = fields.Date(string="Checked (1) Date", tracking=True, copy=False)
    
    checked2_by = fields.Many2one('res.users', string="Checked (2) By", tracking=True, copy=False)
    checked2_date = fields.Date(string="Checked (2) Date", tracking=True, copy=False)
    
    approved_by = fields.Many2one('res.users', string="Approved (1) By", tracking=True, copy=False)
    approved_date = fields.Date(string="Approved (1) Date", tracking=True, copy=False)
    
    approved2_by = fields.Many2one('res.users', string="Approved (2) By", tracking=True, copy=False)
    approved2_date = fields.Date(string="Approved (2) Date", tracking=True, copy=False)

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
    check_number = fields.Char(string="Check Number", tracking=True)
    check_date = fields.Date(string="Check Date", tracking=True)
    check_pay_to = fields.Char(string="Pay to in name of", tracking=True)

    # Computed fields for user visibility (not stored, just for UI)
    is_current_user_checker1 = fields.Boolean(compute='_compute_user_visibility')
    is_current_user_checker2 = fields.Boolean(compute='_compute_user_visibility')
    is_current_user_approver = fields.Boolean(compute='_compute_user_visibility')
    is_current_user_approver2 = fields.Boolean(compute='_compute_user_visibility')

    # Computed fields for totals
    amount_total_gross = fields.Monetary(string="Total Gross", currency_field="currency_id", compute="_compute_amount_totals", store=True)
    amount_total_wht = fields.Monetary(string="Total WHT", currency_field="currency_id", compute="_compute_amount_totals", store=True)
    amount_total_net = fields.Monetary(string="Total Net", currency_field="currency_id", compute="_compute_amount_totals", store=True)
    
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

    @api.depends("line_ids.amount_to_pay_gross", "line_ids.wht_amount")
    def _compute_amount_totals(self):
        for voucher in self:
            voucher.amount_total_gross = sum(line.amount_to_pay_gross for line in voucher.line_ids)
            voucher.amount_total_wht = sum(line.wht_amount for line in voucher.line_ids)
            voucher.amount_total_net = sum(line.amount_to_pay_net for line in voucher.line_ids)

    @api.depends('amount_total_net', 'line_ids.payment_state')
    def _compute_payment_state(self):
        for voucher in self:
            if voucher.state == 'draft':
                voucher.payment_state = 'not_paid'
            else:
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
                    # Default to paid if all lines are paid
                    voucher.payment_state = 'paid'

    @api.depends('company_id.payment_voucher_checker1_id',
                 'company_id.payment_voucher_checker2_id',
                 'company_id.payment_voucher_approver_id',
                 'company_id.payment_voucher_approver2_id',
                 'company_id.payment_voucher_enable_approval2')
    def _compute_user_visibility(self):
        current_user = self.env.user
        for voucher in self:
            # Checker 1
            if voucher.company_id.payment_voucher_checker1_id:
                voucher.is_current_user_checker1 = (current_user == voucher.company_id.payment_voucher_checker1_id)
            else:
                voucher.is_current_user_checker1 = True
                
            # Checker 2
            if voucher.company_id.payment_voucher_checker2_id:
                voucher.is_current_user_checker2 = (current_user == voucher.company_id.payment_voucher_checker2_id)
            else:
                voucher.is_current_user_checker2 = True
                
            # Approver 1
            if voucher.company_id.payment_voucher_approver_id:
                voucher.is_current_user_approver = (current_user == voucher.company_id.payment_voucher_approver_id)
            else:
                voucher.is_current_user_approver = True
            
            # Approver 2
            if voucher.company_id.payment_voucher_enable_approval2:
                if voucher.company_id.payment_voucher_approver2_id:
                    voucher.is_current_user_approver2 = (current_user == voucher.company_id.payment_voucher_approver2_id)
                else:
                    voucher.is_current_user_approver2 = True
            else:
                voucher.is_current_user_approver2 = False
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
            rec.payment_count = self.env['account.payment'].search_count([('ref', 'like', f"PV {rec.name}")])

    def action_open_related_payments(self):
        """
        Smart button action to show related payments for this voucher
        """
        self.ensure_one()
        
        # Get payments linked to this voucher via reference
        payments = self.env['account.payment'].search([('ref', 'like', f"PV {self.name}")])
        
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
        """Submit the voucher for approval (Draft -> Prepared)"""
        for voucher in self:
            if voucher.state != 'draft':
                continue
            voucher.write({
                'state': 'prepared',
                'prepared_by': self.env.user.id,
                'prepared_date': fields.Date.context_today(self)
            })
            voucher.message_post(body=_("Voucher submitted for approval (Prepared)."))
            
            # Create activity for Checker 1 if configured
            if voucher.company_id.payment_voucher_checker1_id:
                voucher.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=voucher.company_id.payment_voucher_checker1_id.id,
                    summary=_("Payment Voucher Check (1) Required"),
                    note=_("Please check payment voucher %s") % voucher.name
                )
        return True

    def action_check1(self):
        """Approve step 1 (Prepared -> Checked 1)"""
        for voucher in self:
            if voucher.state != 'prepared':
                continue
            voucher.write({
                'state': 'checked1',
                'checked1_by': self.env.user.id,
                'checked1_date': fields.Date.context_today(self)
            })
            voucher.message_post(body=_("Voucher checked (step 1)."))
            
            # Mark Checker 1 activity as done
            voucher._mark_activity_done(voucher.company_id.payment_voucher_checker1_id)
            
            # Create activity for Checker 2 if configured
            if voucher.company_id.payment_voucher_checker2_id:
                voucher.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=voucher.company_id.payment_voucher_checker2_id.id,
                    summary=_("Payment Voucher Check (2) Required"),
                    note=_("Please check payment voucher %s") % voucher.name
                )
        return True

    def action_check2(self):
        """Approve step 2 (Checked 1 -> Checked 2)"""
        for voucher in self:
            if voucher.state != 'checked1':
                continue
            voucher.write({
                'state': 'checked2',
                'checked2_by': self.env.user.id,
                'checked2_date': fields.Date.context_today(self)
            })
            voucher.message_post(body=_("Voucher checked (step 2)."))
            
            # Mark Checker 2 activity as done
            voucher._mark_activity_done(voucher.company_id.payment_voucher_checker2_id)
            
            # Create activity for Final Approver if configured
            if voucher.company_id.payment_voucher_approver_id:
                voucher.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=voucher.company_id.payment_voucher_approver_id.id,
                    summary=_("Payment Voucher Approval Required"),
                    note=_("Please approve payment voucher %s") % voucher.name
                )
        return True

    def action_approve(self):
        """First Approval (Checked 2 -> Approved (1))"""
        for voucher in self:
            if voucher.state != 'checked2':
                continue
            
            vals = {
                'state': 'approved',
                'approved_by': self.env.user.id,
                'approved_date': fields.Date.context_today(self)
            }
            
            voucher.write(vals)
            
            # Mark Final Approver activity as done (Approver 1)
            voucher._mark_activity_done(voucher.company_id.payment_voucher_approver_id, feedback=_("Approved (1)"))

            # Determine next step
            if voucher.company_id.payment_voucher_enable_approval2:
                # Schedule activity for Approver 2
                approver2 = voucher.company_id.payment_voucher_approver2_id
                if approver2:
                    voucher.activity_schedule(
                        'mail.mail_activity_data_todo',
                        user_id=approver2.id,
                        summary=_('Please approve payment voucher (Step 2)'),
                        note=_('Voucher %s requires your approval.') % voucher.name,
                    )
                voucher.message_post(body=_("Voucher passed first approval. Waiting for second approval."))
            else:
                voucher.message_post(body=_("Voucher approved. Ready for payment."))
            
        return True

    def action_approve2(self):
        """Second Approval (Approved (1) -> Approved (2))"""
        for voucher in self:
            if voucher.state != 'approved':
                continue
            
            if not voucher.company_id.payment_voucher_enable_approval2:
                # Should not happen if button visibility is correct, but safety check
                continue

            voucher.write({
                'state': 'approved2',
                'approved2_by': self.env.user.id,
                'approved2_date': fields.Date.context_today(self)
            })
            voucher.message_post(body=_("Voucher passed second approval. Ready for payment."))
            
            # Mark Approver 2 activity as done
            voucher._mark_activity_done(voucher.company_id.payment_voucher_approver2_id, feedback=_("Approved (2)"))
            
        return True
        
    def _mark_activity_done(self, user, feedback=None):
        """Helper to mark activity as done for a specific user"""
        if not user:
            return
            
        activity_domain = [
            ('res_id', '=', self.id),
            ('res_model', '=', self._name),
            ('activity_type_id', '=', self.env.ref('mail.mail_activity_data_todo').id),
            ('user_id', '=', user.id)
        ]
        
        activities = self.env['mail.activity'].search(activity_domain)
        if activities:
            activities.action_feedback(feedback=feedback)
    
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
        
        # Check permission based on approval flow
        allowed_states = ['posted']
        if self.company_id.payment_voucher_enable_approval2:
            allowed_states.append('approved2')
            if self.state == 'approved':
                raise UserError(_("Voucher requires second approval before registering payment."))
        else:
            allowed_states.append('approved')
            
        if self.state not in allowed_states:
             raise UserError(_("Voucher must be fully approved before registering payment."))
             
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
             
             if first_wht_line and first_wht_line.wht_tax_id:
                 # Use WHT config directly from voucher line
                 wht_tax_config = first_wht_line.wht_tax_id
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

            # Don't block the payment process, just log the error


    
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

    def action_reset_to_draft(self):
        """Reset the voucher to draft and reverse any linked payments"""
        for voucher in self:
            if voucher.state == "draft":
                continue
                
            # Find payments related to this voucher by looking at the reference
            # Payments are created with ref = f"PV {voucher.name}"
            payments = self.env["account.payment"].search([("ref", "like", f"PV {voucher.name}")])
            
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
            related_moves = self.env["account.move"].search([("ref", "like", f"PV {voucher.name}")])
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

        # 3. Credit Line (Bank/Cash)
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
                'credit': total_net,
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
    wht_tax_id = fields.Many2one(
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

    @api.onchange('wht_tax_id')
    def _onchange_wht_tax(self):
        """Update WHT rate when tax is selected"""
        if self.wht_tax_id:
            # account.withholding.tax uses 'amount' as percentage (e.g., 3 for 3%)
            self.wht_rate = self.wht_tax_id.amount / 100.0
        else:
            self.wht_rate = 0.0

    @api.depends('wht_base_amount', 'wht_rate', 'wht_tax_id')
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