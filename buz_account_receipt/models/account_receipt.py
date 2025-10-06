
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.addons.base.models.res_config import ResConfigSettings


class BuzAccountReceiptSettings(ResConfigSettings):
    _inherit = 'res.config.settings'

    buz_receipt_autopost = fields.Boolean(
        string="Auto-Post Receipts",
        default=True,
        config_parameter='buz_account_receipt.auto_post_receipts',
        help="If checked, receipts will be automatically posted upon creation"
    )


class AccountPayment(models.Model):
    _inherit = "account.payment"

    buz_receipt_id = fields.Many2one('account.receipt', string='Receipt', copy=False)

    def action_post(self):
        # Store receipt reference before posting
        receipt = self.buz_receipt_id
        res = super(AccountPayment, self).action_post()
        
        # Update receipt's related invoices' amount_residuals to trigger recompute
        if receipt:
            # Update receipt amount by recomputing its lines
            receipt.line_ids._compute_paid()
            # Trigger recompute of receipt's total amount
            receipt._compute_amount_total()
            receipt._compute_amount_invoice_total()
            
            # Force a write to trigger all computed fields
            receipt.write({
                'amount_total': receipt.amount_total,
                'amount_invoice_total': receipt.amount_invoice_total
            })
            
        # After posting the payment, we need to ensure the related invoices are reconciled
        # and the receipt lines are updated accordingly
        if receipt and self.state == 'posted':
            # Update the receipt line values based on current invoice state
            for line in receipt.line_ids:
                if line.move_id:
                    # Refresh the amounts based on the current state of the invoice
                    total = line.move_id.amount_total_signed if line.move_id.move_type == "out_refund" else line.move_id.amount_total
                    residual = line.move_id.amount_residual_signed if line.move_id.move_type == "out_refund" else line.move_id.amount_residual
                    line.write({
                        'amount_total': total,
                        'amount_residual': residual,
                    })
        
        # Check if payment was created from a receipt voucher line or payment voucher line
        voucher_line_id = self.env.context.get('buz_voucher_line_id')
        if voucher_line_id:
            # First try account.receipt.voucher.line (AR)
            try:
                voucher_line = self.env['account.receipt.voucher.line'].browse(voucher_line_id)
                if voucher_line.exists():
                    # Link the payment to the voucher line
                    voucher_line.write({
                        'payment_ids': [(4, self.id, 0)]  # Add the payment to the many2many field
                    })
            except Exception:
                # If there's an error with the first model, try the second one
                try:
                    # Try account.payment.voucher.line (AP)
                    voucher_line = self.env['account.payment.voucher.line'].browse(voucher_line_id)
                    if voucher_line.exists():
                        # Link the payment to the voucher line
                        voucher_line.write({
                            'payment_ids': [(4, self.id, 0)]  # Add the payment to the many2many field
                        })
                except Exception:
                    # If there's an error, just continue (don't break the payment process)
                    pass

        # Also check if payment should be linked to a receipt directly
        receipt_id = self.env.context.get('buz_receipt_id')
        if receipt_id:
            try:
                receipt = self.env['account.receipt'].browse(receipt_id)
                if receipt.exists():
                    # Link the payment to the receipt
                    self.write({
                        'buz_receipt_id': receipt.id
                    })
                    # Update receipt's related invoices' amount_residuals to trigger recompute
                    receipt.line_ids._compute_paid()
                    # Trigger recompute of receipt's total amount
                    receipt._compute_amount_total()
                    receipt._compute_amount_invoice_total()
            except Exception:
                # If there's an error, just continue (don't break the payment process)
                pass
            
        return res


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _action_create_receipt_from_partner(self):
        """
        Creates a receipt from this partner's invoices 
        """
        self.ensure_one()
        # Get all posted invoices for this partner
        invoices = self.env['account.move'].search([
            ('partner_id', '=', self.id),
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('state', '=', 'posted'),
            ('company_id', '=', self.env.company.id),  # Ensure invoices are from the same company as the current session
        ])
        
        # Create a receipt for this partner
        receipt = self.env["account.receipt"].create({
            "partner_id": self.id,
            "date": fields.Date.context_today(self),
            "company_id": self.env.company.id,
        })
        
        # Add invoices to the receipt as lines
        lines_vals = []
        for invoice in invoices:
            if invoice.move_type == 'out_refund':
                total = invoice.amount_total_signed
                residual = invoice.amount_residual_signed
            else:
                total = invoice.amount_total
                residual = invoice.amount_residual
            lines_vals.append((0, 0, {
                "move_id": invoice.id,
                "amount_total": total,
                "amount_residual": residual,
                "amount_to_collect": residual,  # Default to residual amount
            }))
        receipt.write({"line_ids": lines_vals})
        
        # Check if auto-post is enabled via configuration
        auto_post_enabled = self.env['ir.config_parameter'].sudo().get_param('buz_account_receipt.auto_post_receipts', default=True)
        if auto_post_enabled:
            receipt.action_post()
        
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.receipt",
            "view_mode": "form",
            "res_id": receipt.id,
            "context": {"form_view_initial_mode": "edit"},
        }


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_create_receipt_from_invoices(self):
        """
        Creates a receipt from selected invoices that have the same partner
        """
        # Check if we're dealing with selected records from the context
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')
        
        if active_model == 'account.move' and active_ids and len(active_ids) > 1:
            # Multiple invoices selected from the list view
            moves = self.browse(active_ids)
        else:
            # Single invoice or called directly
            moves = self

        # Check if all invoices belong to the same partner
        partners = set(moves.mapped('partner_id'))
        if len(partners) > 1:
            raise UserError(_("You can only create a receipt for invoices from the same customer."))
        
        # Check if all invoices belong to the same company
        companies = set(moves.mapped('company_id'))
        if len(companies) > 1:
            raise UserError(_("You can only create a receipt for invoices from the same company."))
        
        # Filter invoices to include only posted ones with proper types
        # NOTE: We do NOT filter by payment_state to allow receipts for partially paid or unpaid invoices
        # This enables batch payment registration for invoices that are not fully paid yet
        valid_moves = moves.filtered(lambda m: m.state == 'posted' and 
                                     m.move_type in ['out_invoice', 'out_refund'])
        
        # Check if any of the selected invoices are already used in another receipt (any state: draft, posted, or cancelled)
        existing_receipt_lines = self.env['account.receipt.line'].search([('move_id', 'in', valid_moves.ids)])
        if existing_receipt_lines:
            used_invoice_numbers = [line.move_id.name for line in existing_receipt_lines]
            raise UserError(_("The following invoices are already used in receipts and cannot be added again: %s") % ", ".join(used_invoice_numbers))

        if not valid_moves:
            # Filter to see what types of invoices were selected
            invalid_state_moves = moves.filtered(lambda m: m.state != 'posted')
            invalid_type_moves = moves.filtered(lambda m: m.move_type not in ['out_invoice', 'out_refund'])
            
            error_message = _("No valid invoices found for receipt creation. ")
            
            if invalid_state_moves:
                error_message += _("%d invoice(s) are not in 'Posted' state. ") % len(invalid_state_moves)
            if invalid_type_moves:
                error_message += _("%d invoice(s) are not of type 'Customer Invoice' or 'Customer Credit Note'. ") % len(invalid_type_moves)
                
            error_message += _("Please select only posted invoices of type 'Customer Invoice' or 'Customer Credit Note'.")
            
            raise UserError(error_message)
        
        # Create receipt, set delivery_partner_id from first invoice's shipping partner if available
        first_move = valid_moves[0]
        delivery_partner = first_move.partner_shipping_id or first_move.partner_id
        receipt = self.env["account.receipt"].create({
            "partner_id": first_move.partner_id.id,
            "date": fields.Date.context_today(self),
            "line_ids": [],
            "delivery_partner_id": delivery_partner.id if delivery_partner else False,
        })

        lines_vals = []
        for mv in valid_moves:
            # sign handling for refunds: show signed totals consistently
            total = mv.amount_total_signed if mv.move_type == "out_refund" else mv.amount_total
            residual = mv.amount_residual_signed if mv.move_type == "out_refund" else mv.amount_residual
            lines_vals.append((0, 0, {
                "move_id": mv.id,
                "amount_total": total,
                "amount_residual": residual,
            }))
        receipt.write({"line_ids": lines_vals})

        # Check if auto-post is enabled via configuration
        auto_post_enabled = self.env['ir.config_parameter'].sudo().get_param('buz_account_receipt.auto_post_receipts', default=True)
        if auto_post_enabled:
            receipt.action_post()
        
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.receipt",
            "view_mode": "form",
            "res_id": receipt.id,
        }


class AccountReceipt(models.Model):
    _name = "account.receipt"
    _description = "Grouped Customer Receipt"
    _order = "date desc, id desc"

    name = fields.Char(string="Receipt Number", readonly=True, copy=False, default="/")
    date = fields.Date(string="Receipt Date", default=fields.Date.context_today, required=True)
    partner_id = fields.Many2one("res.partner", string="Customer", required=True, domain=[("customer_rank", ">", 0)])
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency", required=True, default=lambda self: self.env.company.currency_id)
    note = fields.Text(string="Notes")
    delivery_partner_id = fields.Many2one('res.partner', string='Delivery Address', help='Delivery address from first invoice used to create this receipt')

    line_ids = fields.One2many("account.receipt.line", "receipt_id", string="Lines")
    amount_total = fields.Monetary(string="Total Paid", currency_field="currency_id", compute="_compute_amount_total", store=True)
    amount_total_words = fields.Char(
        string="Amount in Words",
        compute="_compute_amount_total_words",
        store=True,
        readonly=True,
    )
    # Sum of invoice amounts included in this receipt (regardless of paid)
    amount_invoice_total = fields.Monetary(string="Invoice Total", currency_field="currency_id", compute="_compute_amount_invoice_total", store=True)
    amount_invoice_total_words = fields.Char(
        string="Invoice Amount in Words",
        compute="_compute_amount_invoice_total_words",
        store=True,
        readonly=True,
    )

    # Moves already used in receipts (to help filter selection)
    used_move_ids = fields.Many2many('account.move', string='Used Invoices', compute='_compute_used_moves')

    # Link to related payments
    payment_ids = fields.One2many('account.payment', 'buz_receipt_id', string='Payments')
    
    state = fields.Selection([
        ("draft", "Draft"),
        ("posted", "Posted"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True)

    @api.constrains('line_ids', 'company_id')
    def _check_receipt_lines_company(self):
        """Ensure all receipt lines belong to the same company as the receipt"""
        for receipt in self:
            for line in receipt.line_ids:
                if line.move_id and line.move_id.company_id != receipt.company_id:
                    raise UserError(
                        _("The invoice %s belongs to company %s, but the receipt is for company %s. "
                          "All invoice lines must belong to the same company as the receipt.") % 
                         (line.move_id.name, line.move_id.company_id.name, receipt.company_id.name))

    @api.depends("line_ids.amount_to_collect")
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped("amount_to_collect"))

    def action_post(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("No lines to post."))
            if rec.name == "/":
                rec.name = self.env["ir.sequence"].next_by_code("buz.account.receipt") or "/"
            rec.state = "posted"
        return True

    @api.depends('amount_total', 'currency_id')
    def _compute_amount_total_words(self):
        # Convert amount_total to words (Thai for THB, fallback to English)
        try:
            from num2words import num2words
        except Exception:
            num2words = None
        for rec in self:
            if rec.amount_total is not None and rec.currency_id:
                amount = "%.2f" % rec.amount_total
                int_part, dec_part = amount.split('.')
                baht = int(int_part)
                satang = int(dec_part)
                if num2words and rec.currency_id.name == 'THB':
                    baht_text = num2words(baht, lang='th').replace('เอ็ดบาท', 'หนึ่งบาท')
                    if satang > 0:
                        satang_text = num2words(satang, lang='th').replace('เอ็ด', 'หนึ่ง')
                        rec.amount_total_words = f"{baht_text}บาท {satang_text}สตางค์"
                    else:
                        rec.amount_total_words = f"{baht_text}บาทถ้วน"
                elif num2words:
                    rec.amount_total_words = num2words(rec.amount_total, lang='en').title()
                else:
                    # num2words not installed; fallback to empty string
                    rec.amount_total_words = ''
            else:
                rec.amount_total_words = ''

    @api.depends('line_ids.amount_total', 'currency_id')
    def _compute_amount_invoice_total(self):
        for rec in self:
            rec.amount_invoice_total = sum(rec.line_ids.mapped('amount_total'))

    @api.depends('amount_invoice_total', 'currency_id')
    def _compute_amount_invoice_total_words(self):
        try:
            from num2words import num2words
        except Exception:
            num2words = None
        for rec in self:
            if rec.amount_invoice_total is not None and rec.currency_id:
                amount = "%.2f" % rec.amount_invoice_total
                int_part, dec_part = amount.split('.')
                baht = int(int_part)
                satang = int(dec_part)
                if num2words and rec.currency_id.name == 'THB':
                    baht_text = num2words(baht, lang='th').replace('เอ็ดบาท', 'หนึ่งบาท')
                    if satang > 0:
                        satang_text = num2words(satang, lang='th').replace('เอ็ด', 'หนึ่ง')
                        rec.amount_invoice_total_words = f"{baht_text}บาท {satang_text}สตางค์"
                    else:
                        rec.amount_invoice_total_words = f"{baht_text}บาทถ้วน"
                elif num2words:
                    rec.amount_invoice_total_words = num2words(rec.amount_invoice_total, lang='en').title()
                else:
                    rec.amount_invoice_total_words = ''
            else:
                rec.amount_invoice_total_words = ''

    def action_reset_to_draft(self):
        self.write({"state": "draft"})
        return True

    def action_print_receipt(self):
        self.ensure_one()
        return self.env.ref("buz_account_receipt.action_report_buz_account_receipt").report_action(self)

    @api.model
    def create(self, vals):
        rec = super(AccountReceipt, self).create(vals)
        # If delivery_partner_id not provided, try to fill from first invoice in lines
        if not rec.delivery_partner_id and rec.line_ids:
            first_move = rec.line_ids[0].move_id
            if first_move:
                rec.delivery_partner_id = first_move.partner_shipping_id or first_move.partner_id
        
        # Check if auto-post is enabled via configuration
        auto_post_enabled = self.env['ir.config_parameter'].sudo().get_param('buz_account_receipt.auto_post_receipts', default=True)
        if auto_post_enabled and rec.line_ids:  # Only auto-post if there are lines
            rec.action_post()
        
        return rec

    def write(self, vals):
        res = super(AccountReceipt, self).write(vals)
        # After write, ensure receipts with empty delivery_partner_id get filled from first line
        for rec in self:
            if not rec.delivery_partner_id and rec.line_ids:
                first_move = rec.line_ids[0].move_id
                if first_move:
                    rec.delivery_partner_id = first_move.partner_shipping_id or first_move.partner_id
        return res

    def _compute_used_moves(self):
        """Compute account.move records that are already referenced by any receipt line.
        This lets the view filter out invoices that were already selected.
        """
        # collect all move_ids used in any receipt line
        all_line_moves = self.env['account.receipt.line'].search([]).mapped('move_id')
        for rec in self:
            rec.used_move_ids = all_line_moves

    def action_view_payments(self):
        """
        Smart button action to show related payments for this receipt
        """
        self.ensure_one()
        
        # Get all payments linked to this receipt
        payments = self.payment_ids
        
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

    def action_register_batch_payment(self):
        """
        Open the standard account.payment.register wizard to register batch payment for all invoices in this receipt.
        """
        self.ensure_one()
        
        # Get all invoices linked to this receipt that have residual amounts (not fully paid)
        invoices = self.line_ids.filtered(lambda line: line.amount_residual != 0).mapped('move_id')
        
        if not invoices:
            raise UserError(_("There are no invoices with outstanding amounts linked to this receipt to register payment for."))
        
        # Validate invoices
        for invoice in invoices:
            # Check if invoice is posted
            if invoice.state != 'posted':
                raise UserError(_("Invoice %s is not in 'Posted' state. All invoices must be posted to register payment.") % invoice.name)
            
            # Check if invoice belongs to the same partner as the receipt
            if invoice.partner_id != self.partner_id:
                raise UserError(_("Invoice %s belongs to a different partner than the receipt. All invoices must belong to the same partner as the receipt.") % invoice.name)
            
            # Check if invoice is a customer invoice/refund
            if invoice.move_type not in ['out_invoice', 'out_refund']:
                raise UserError(_("Invoice %s is not a customer invoice or refund. Only customer invoices and refunds can be used for payment registration.") % invoice.name)
            
            # Check if the invoice is not fully paid
            if invoice.payment_state == 'paid':
                raise UserError(_("Invoice %s is already fully paid. Cannot register payment for fully paid invoices.") % invoice.name)

        # Prepare context for the payment register wizard
        # Check if account_payment_batch_process module is installed
        has_batch_process = 'account.payment.batch' in self.env.registry
        
        # Prepare the action to open the payment register wizard
        action = {
            'name': _('Register Payment'),
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'view_id': self.env.ref('account.view_account_payment_register_form').id,
            'target': 'new',
            'type': 'ir.actions.act_window',
            'context': {
                'active_model': 'account.move',
                'active_ids': invoices.ids,
                'default_partner_id': self.partner_id.id,
                'default_payment_type': 'inbound',
                'default_journal_ids': self.env['account.journal'].search([('type', 'in', ('bank', 'cash'))]).ids,
                'default_is_batch_payment': True,  # Flag to indicate this is a batch payment from receipt
                'default_is_multiline_batch': True,  # Enable multiline batch processing if applicable
                # Pass receipt ID to link payments back to receipt. Use default_ so created payments inherit it.
                'buz_receipt_id': self.id,
                'default_buz_receipt_id': self.id,
            },
        }
        
        # If account_payment_batch_process module is available, set appropriate context
        if has_batch_process:
            action['context']['from_batch_receipt'] = True
            action['context']['batch_receipt_id'] = self.id
            action['context']['default_batch_receipt_id'] = self.id
        
        return action


class AccountReceiptLine(models.Model):
    _name = "account.receipt.line"
    _description = "Account Receipt Line"
    _order = "invoice_date, id"

    receipt_id = fields.Many2one("account.receipt", string="Receipt", required=True, ondelete="cascade")
    move_id = fields.Many2one("account.move", string="Invoice", domain="[('move_type', 'in', ['out_invoice', 'out_refund']), ('state', '=', 'posted')]", required=True)

    @api.constrains('move_id', 'receipt_id')
    def _check_invoice_partner_matches_receipt_partner(self):
        """Ensure that the invoice's partner matches the receipt's partner"""
        for line in self:
            if line.move_id and line.receipt_id:
                if line.move_id.partner_id != line.receipt_id.partner_id:
                    raise UserError(
                        _("The invoice %s belongs to partner %s, but the receipt is for partner %s. "
                          "Invoices must belong to the same partner as the receipt.") % 
                         (line.move_id.name, line.move_id.partner_id.name, line.receipt_id.partner_id.name))
                # Additional validation: ensure invoice and receipt are from the same company
                if line.move_id.company_id != line.receipt_id.company_id:
                    raise UserError(
                        _("The invoice %s belongs to company %s, but the receipt is for company %s. "
                          "Invoices and receipts must belong to the same company.") % 
                         (line.move_id.name, line.move_id.company_id.name, line.receipt_id.company_id.name))

    move_name = fields.Char(string="Invoice Number", related="move_id.name", store=True)
    invoice_date = fields.Date(string="Invoice Date", related="move_id.invoice_date", store=True)
    currency_id = fields.Many2one(related="receipt_id.currency_id", store=True, readonly=True)

    amount_total = fields.Monetary(string="Amount Total", currency_field="currency_id")
    amount_residual = fields.Monetary(string="Residual", currency_field="currency_id")
    amount_paid = fields.Monetary(string="Amount Paid", currency_field="currency_id", compute="_compute_paid", store=True)
    amount_to_collect = fields.Monetary(
        string="Amount to Collect", 
        currency_field="currency_id",
        help="Amount expected to be received in this receipt (default: residual amount)",
        default=lambda self: 0.0
    )

    @api.onchange('move_id')
    def _onchange_move_id_set_amounts(self):
        """When invoice is selected on the line, populate total and residual amounts from the invoice."""
        for line in self:
            if line.move_id:
                # Use signed amounts for refunds to keep consistent signs
                if line.move_id.move_type == 'out_refund':
                    line.amount_total = line.move_id.amount_total_signed
                    line.amount_residual = line.move_id.amount_residual_signed
                else:
                    line.amount_total = line.move_id.amount_total
                    line.amount_residual = line.move_id.amount_residual
                
                # Set amount_to_collect to the residual amount by default
                line.amount_to_collect = line.amount_residual
            else:
                line.amount_total = 0.0
                line.amount_residual = 0.0
                line.amount_to_collect = 0.0

    @api.depends("amount_total", "amount_residual", "amount_to_collect", "move_id.amount_residual", "move_id.amount_residual_signed")
    def _compute_paid(self):
        """Compute the paid amount for each receipt line. This uses the current invoice residual
        to derive the cumulative paid amount; for this receipt we expose the amount_to_collect
        as the paid amount for display and totals calculations."""
        for line in self:
            if line.move_id:
                # For refunds, use signed residuals/totals
                residual = line.move_id.amount_residual_signed if line.move_id.move_type == 'out_refund' else line.move_id.amount_residual
                total = line.move_id.amount_total_signed if line.move_id.move_type == 'out_refund' else line.move_id.amount_total
                # The amount_paid shown for the line is what's being collected in this receipt
                line.amount_paid = line.amount_to_collect
            else:
                line.amount_paid = (line.amount_total or 0.0) - (line.amount_residual or 0.0)


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_create_receipt_from_invoices(self):
        """
        Creates a receipt from selected invoices that have the same partner
        """
        # Check if we're dealing with selected records from the context
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')
        
        if active_model == 'account.move' and active_ids and len(active_ids) > 1:
            # Multiple invoices selected from the list view
            moves = self.browse(active_ids)
        else:
            # Single invoice or called directly
            moves = self

        # Check if all invoices belong to the same partner
        partners = set(moves.mapped('partner_id'))
        if len(partners) > 1:
            raise UserError(_("You can only create a receipt for invoices from the same customer."))
        
        # Check if all invoices belong to the same company
        companies = set(moves.mapped('company_id'))
        if len(companies) > 1:
            raise UserError(_("You can only create a receipt for invoices from the same company."))
        
        # Filter invoices to include only posted ones with proper types
        # NOTE: We do NOT filter by payment_state to allow receipts for partially paid or unpaid invoices
        # This enables batch payment registration for invoices that are not fully paid yet
        valid_moves = moves.filtered(lambda m: m.state == 'posted' and 
                                     m.move_type in ['out_invoice', 'out_refund'])
        
        # Check if any of the selected invoices are already used in another receipt (any state: draft, posted, or cancelled)
        existing_receipt_lines = self.env['account.receipt.line'].search([('move_id', 'in', valid_moves.ids)])
        if existing_receipt_lines:
            used_invoice_numbers = [line.move_id.name for line in existing_receipt_lines]
            raise UserError(_("The following invoices are already used in receipts and cannot be added again: %s") % ", ".join(used_invoice_numbers))

        if not valid_moves:
            # Filter to see what types of invoices were selected
            invalid_state_moves = moves.filtered(lambda m: m.state != 'posted')
            invalid_type_moves = moves.filtered(lambda m: m.move_type not in ['out_invoice', 'out_refund'])
            
            error_message = _("No valid invoices found for receipt creation. ")
            
            if invalid_state_moves:
                error_message += _("%d invoice(s) are not in 'Posted' state. ") % len(invalid_state_moves)
            if invalid_type_moves:
                error_message += _("%d invoice(s) are not of type 'Customer Invoice' or 'Customer Credit Note'. ") % len(invalid_type_moves)
                
            error_message += _("Please select only posted invoices of type 'Customer Invoice' or 'Customer Credit Note'.")
            
            raise UserError(error_message)
        
        # Create receipt, set delivery_partner_id from first invoice's shipping partner if available
        first_move = valid_moves[0]
        delivery_partner = first_move.partner_shipping_id or first_move.partner_id
        receipt = self.env["account.receipt"].create({
            "partner_id": first_move.partner_id.id,
            "date": fields.Date.context_today(self),
            "line_ids": [],
            "delivery_partner_id": delivery_partner.id if delivery_partner else False,
        })

        lines_vals = []
        for mv in valid_moves:
            # sign handling for refunds: show signed totals consistently
            total = mv.amount_total_signed if mv.move_type == "out_refund" else mv.amount_total
            residual = mv.amount_residual_signed if mv.move_type == "out_refund" else mv.amount_residual
            lines_vals.append((0, 0, {
                "move_id": mv.id,
                "amount_total": total,
                "amount_residual": residual,
            }))
        receipt.write({"line_ids": lines_vals})

        # Check if auto-post is enabled via configuration
        auto_post_enabled = self.env['ir.config_parameter'].sudo().get_param('buz_account_receipt.auto_post_receipts', default=True)
        if auto_post_enabled:
            receipt.action_post()
        
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.receipt",
            "view_mode": "form",
            "res_id": receipt.id,
        }

    def write(self, vals):
        """Override write to update related receipt lines when invoice payment status changes."""
        res = super(AccountMove, self).write(vals)
        
        # If payment state or residual amount changed, update related receipt lines
        if any(field in vals for field in ['payment_state', 'amount_residual', 'amount_residual_signed', 'amount_total', 'amount_total_signed']):
            # Find all receipt lines that reference this invoice
            receipt_lines = self.env['account.receipt.line'].search([('move_id', 'in', self.ids)])
            if receipt_lines:
                # Update the receipt lines to reflect the new payment status
                receipt_lines._compute_paid()
                
                # Update the receipts to reflect the new totals
                receipts = receipt_lines.mapped('receipt_id')
                for receipt in receipts:
                    receipt._compute_amount_total()
                    receipt._compute_amount_invoice_total()
        
        return res
