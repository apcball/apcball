
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
    
    buz_enforce_single_currency_per_receipt = fields.Boolean(
        string="Enforce Single Currency per Receipt",
        default=True,
        config_parameter='buz_account_receipt.enforce_single_currency_per_receipt',
        help="If checked, all invoices in a receipt must have the same currency"
    )
    
    buz_allow_outstanding_fallback = fields.Boolean(
        string="Allow Outstanding Payment Fallback",
        default=True,
        config_parameter='buz_account_receipt.allow_outstanding_fallback',
        help="If checked, when there are no unpaid invoices, allow creating on-account payments"
    )
    
    buz_default_bank_journal_id = fields.Many2one(
        'account.journal',
        string='Default Bank Journal',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        config_parameter='buz_account_receipt.default_bank_journal_id',
        help="Default journal to use for creating on-account payments"
    )


class AccountPayment(models.Model):
    _inherit = "account.payment"

    receipt_ids = fields.Many2many(
        'account.receipt',
        'account_receipt_payment_rel',
        'payment_id',
        'receipt_id',
        string='Receipts',
        help="Receipts linked to this payment"
    )

    def action_post(self):
        # Store receipt reference before posting
        receipts = self.receipt_ids
        res = super(AccountPayment, self).action_post()
        
        # Update receipt's related invoices' amount_residuals to trigger recompute
        for receipt in receipts:
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
        if receipts and self.state == 'posted':
            for receipt in receipts:
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

        # Also check if payment should be linked to a receipt directly (from context)
        receipt_id = self.env.context.get('buz_receipt_id')
        if receipt_id:
            try:
                receipt = self.env['account.receipt'].browse(receipt_id)
                if receipt.exists():
                    # Link the payment to the receipt using M2M
                    receipt.write({
                        'payment_ids': [(4, self.id)]
                    })
                    # Update receipt's related invoices' amount_residuals to trigger recompute
                    receipt.line_ids._compute_paid()
                    # Trigger recompute of receipt's total amount
                    receipt._compute_amount_total()
                    receipt._compute_amount_invoice_total()
                    # Also update the payment count
                    receipt._compute_payment_count()
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
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "date desc, id desc"

    name = fields.Char(string="Receipt Number", readonly=True, copy=False, default="/")
    date = fields.Date(string="Receipt Date", default=fields.Date.context_today, required=True)
    partner_id = fields.Many2one("res.partner", string="Customer", required=True, domain=[("customer_rank", ">", 0)])
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency", required=True, compute="_compute_currency_id", store=True, readonly=False, precompute=True)
    
    @api.depends('company_id')
    def _compute_currency_id(self):
        for receipt in self:
            receipt.currency_id = receipt.company_id.currency_id
    note = fields.Text(string="Notes")
    delivery_partner_id = fields.Many2one('res.partner', string='Delivery Address', help='Delivery address from first invoice used to create this receipt')

    line_ids = fields.One2many("account.receipt.line", "receipt_id", string="Lines")
    # Amount to collect this round (computed from lines)
    amount_total = fields.Monetary(
        string="Amount to Collect (This Receipt)", 
        currency_field="currency_id", 
        compute="_compute_amount_total", 
        store=True,
        help="Sum of amount_to_collect from all lines - represents what should be collected in this receipt"
    )
    amount_total_words = fields.Char(
        string="Amount in Words (Thai)",
        compute="_compute_amount_total_words",
        store=True,
        readonly=True,
        help="Amount in Thai words (e.g., 'หนึ่งพันบาทถ้วน')"
    )
    # Sum of invoice amounts included in this receipt (regardless of paid)
    amount_invoice_total = fields.Monetary(string="Invoice Total", currency_field="currency_id", compute="_compute_amount_invoice_total", store=True)
    amount_invoice_total_words = fields.Char(
        string="Invoice Amount in Words (Thai)",
        compute="_compute_amount_invoice_total_words",
        store=True,
        readonly=True,
        help="Invoice total amount in Thai words"
    )

    # Moves already used in receipts (to help filter selection)
    used_move_ids = fields.Many2many('account.move', string='Used Invoices', compute='_compute_used_moves')

    # Link to related payments (M2M for RV-ready approach)
    payment_ids = fields.Many2many(
        'account.payment', 
        'account_receipt_payment_rel', 
        'receipt_id',
        'payment_id', 
        string='Payments',
        readonly=True,
        help="Payments linked to this receipt"
    )
    
    # Computed field for payment count
    payment_count = fields.Integer(
        compute="_compute_payment_count",
        string="Payment Count",
        store=True
    )
    
    state = fields.Selection([
        ("draft", "Draft"),
        ("posted", "Posted"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True)
    
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

    @api.depends('amount_total', 'amount_paid', 'line_ids.move_id.payment_state')
    def _compute_payment_state(self):
        for receipt in self:
            if receipt.state == 'draft':
                receipt.payment_state = 'not_paid'
            elif not receipt.line_ids:
                # If no lines in receipt, consider as not paid
                receipt.payment_state = 'not_paid'
            else:
                # Determine the receipt's payment state based on the underlying invoices' statuses
                # This approach prioritizes matching the invoice status as requested by the user
                
                invoice_payment_states = receipt.line_ids.mapped('move_id.payment_state')
                
                # If all invoices are 'overpaid', show as 'paid' to match their effective status
                if all(state == 'overpaid' for state in invoice_payment_states):
                    receipt.payment_state = 'paid'
                # If all invoices are at least fully paid (paid or overpaid), receipt is paid
                elif all(state in ['paid', 'overpaid'] for state in invoice_payment_states):
                    receipt.payment_state = 'paid'
                # If all invoices are not paid
                elif all(state == 'not_paid' for state in invoice_payment_states if state):
                    receipt.payment_state = 'not_paid'
                # If there's a mix or some are partially paid
                else:
                    receipt.payment_state = 'partial'

    @api.depends('line_ids.amount_paid')
    def _compute_amount_paid(self):
        for receipt in self:
            receipt.amount_paid = sum(receipt.line_ids.mapped('amount_paid'))

    def _compute_amount_residual(self):
        for receipt in self:
            receipt.amount_residual = receipt.amount_total - receipt.amount_paid

    @api.depends('payment_ids')
    def _compute_payment_count(self):
        for receipt in self:
            receipt.payment_count = len(receipt.payment_ids)

    @api.constrains('line_ids', 'currency_id')
    def _check_receipt_lines_currency(self):
        """Enforce single currency per receipt if setting is enabled"""
        single_currency_enabled = self.env['ir.config_parameter'].sudo().get_param(
            'buz_account_receipt.enforce_single_currency_per_receipt', default=True
        )
        if single_currency_enabled:
            for receipt in self:
                for line in receipt.line_ids:
                    if line.move_id and line.move_id.currency_id != receipt.currency_id:
                        raise UserError(
                            _("The invoice %s is in currency %s, but the receipt is in currency %s. "
                              "All invoices in a receipt must be in the same currency as the receipt.") % 
                             (line.move_id.name, line.move_id.currency_id.name, receipt.currency_id.name))

    def action_post(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("No lines to post."))
            if rec.name == "/":
                rec.name = self.env["ir.sequence"].next_by_code("buz.account.receipt") or "/"
            rec.state = "posted"
        return True

    def _amount_to_thai_text(self, amount):
        """
        Convert number to Thai text for baht and satang
        Example: 1250.50 -> 'หนึ่งพันสองร้อยห้าสิบบาทห้าสิบสตางค์'
        """
        if amount == 0:
            return 'ศูนย์บาทถ้วน'
        
        # Thai number words
        ones = ['', 'หนึ่ง', 'สอง', 'สาม', 'สี่', 'ห้า', 'หก', 'เจ็ด', 'แปด', 'เก้า']
        
        def _convert_group(num):
            """Convert a number less than 1000000 to Thai text"""
            if num == 0:
                return ''
            
            result = ''
            
            # แสน (hundred thousands)
            if num >= 100000:
                hundreds_thousands = num // 100000
                if hundreds_thousands == 1:
                    result += 'หนึ่งแสน'
                elif hundreds_thousands == 2:
                    result += 'สองแสน'
                else:
                    result += ones[hundreds_thousands] + 'แสน'
                num %= 100000
            
            # หมื่น (ten thousands)
            if num >= 10000:
                ten_thousands = num // 10000
                if ten_thousands == 1:
                    result += 'หนึ่งหมื่น'
                elif ten_thousands == 2:
                    result += 'สองหมื่น'
                else:
                    result += ones[ten_thousands] + 'หมื่น'
                num %= 10000
            
            # พัน (thousands)
            if num >= 1000:
                thousands = num // 1000
                if thousands == 1:
                    result += 'หนึ่งพัน'
                elif thousands == 2:
                    result += 'สองพัน'
                else:
                    result += ones[thousands] + 'พัน'
                num %= 1000
            
            # ร้อย (hundreds)
            if num >= 100:
                hundreds = num // 100
                if hundreds == 1:
                    result += 'หนึ่งร้อย'
                elif hundreds == 2:
                    result += 'สองร้อย'
                else:
                    result += ones[hundreds] + 'ร้อย'
                num %= 100
            
            # สิบ (tens)
            if num >= 10:
                tens = num // 10
                if tens == 1:
                    result += 'สิบ'
                elif tens == 2:
                    result += 'ยี่สิบ'
                else:
                    result += ones[tens] + 'สิบ'
                num %= 10
            
            # หน่วย (ones)
            if num > 0:
                if num == 1 and len(result) > 0:
                    result += 'เอ็ด'
                else:
                    result += ones[num]
            
            return result
        
        # Split into baht and satang
        baht = int(amount)
        satang = int(round((amount - baht) * 100))
        
        result = ''
        
        # Process millions
        if baht >= 1000000:
            millions = baht // 1000000
            result += _convert_group(millions) + 'ล้าน'
            baht %= 1000000
        
        # Process remaining baht
        if baht > 0:
            result += _convert_group(baht)
        
        result += 'บาท'
        
        # Process satang
        if satang > 0:
            result += _convert_group(satang) + 'สตางค์'
        else:
            result += 'ถ้วน'
        
        return result

    @api.depends('amount_total', 'currency_id')
    def _compute_amount_total_words(self):
        for rec in self:
            if rec.amount_total and rec.currency_id:
                if rec.currency_id.name == 'THB':
                    rec.amount_total_words = rec._amount_to_thai_text(rec.amount_total)
                else:
                    # For other currencies, use English
                    try:
                        from num2words import num2words
                        rec.amount_total_words = num2words(rec.amount_total, lang='en').title() + ' ' + rec.currency_id.name
                    except Exception:
                        rec.amount_total_words = f"{rec.amount_total:.2f} {rec.currency_id.name}"
            else:
                rec.amount_total_words = ''

    @api.depends('line_ids.amount_total', 'currency_id')
    def _compute_amount_invoice_total(self):
        for rec in self:
            rec.amount_invoice_total = sum(rec.line_ids.mapped('amount_total'))

    @api.depends('amount_invoice_total', 'currency_id')
    def _compute_amount_invoice_total_words(self):
        for rec in self:
            if rec.amount_invoice_total and rec.currency_id:
                if rec.currency_id.name == 'THB':
                    rec.amount_invoice_total_words = rec._amount_to_thai_text(rec.amount_invoice_total)
                else:
                    # For other currencies, use English
                    try:
                        from num2words import num2words
                        rec.amount_invoice_total_words = num2words(rec.amount_invoice_total, lang='en').title() + ' ' + rec.currency_id.name
                    except Exception:
                        rec.amount_invoice_total_words = f"{rec.amount_invoice_total:.2f} {rec.currency_id.name}"
            else:
                rec.amount_invoice_total_words = ''

    def action_reset_to_draft(self):
        self.write({"state": "draft"})
        return True

    def action_print_receipt(self):
        self.ensure_one()
        return self.env.ref("buz_account_receipt.action_report_buz_account_receipt").report_action(self)

    @api.model
    def action_create_receipt_voucher_from_receipts(self):
        """
        Creates a receipt voucher from selected receipts
        """
        # Check if we're dealing with selected records from the context
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')
        
        if active_model == 'account.receipt' and active_ids and len(active_ids) > 0:
            # Multiple receipts selected from the list view
            receipts = self.browse(active_ids)
        else:
            # Single receipt or called directly
            receipts = self

        # Filter to only valid receipts (posted receipts)
        valid_receipts = receipts.filtered(lambda r: r.state == 'posted')
        
        if not valid_receipts:
            raise UserError(_("No valid receipts selected. Please select posted receipts."))

        # Check if all receipts belong to the same company
        companies = set(valid_receipts.mapped('company_id'))
        if len(companies) > 1:
            raise UserError(_("You can only create a receipt voucher for receipts from the same company."))

        # Check if all receipts have the same currency
        currencies = set(valid_receipts.mapped('currency_id'))
        if len(currencies) > 1:
            raise UserError(_("You can only create a receipt voucher for receipts with the same currency."))

        # Check if any of the selected receipts are already used in a voucher
        existing_voucher_lines = self.env['account.receipt.voucher.line'].search([('receipt_id', 'in', valid_receipts.ids)])
        if existing_voucher_lines:
            used_receipt_names = [line.receipt_id.name for line in existing_voucher_lines]
            raise UserError(_("The following receipts are already used in receipt vouchers and cannot be added again: %s") % ", ".join(used_receipt_names))

        # Create a receipt voucher
        voucher = self.env['account.receipt.voucher'].create({
            'line_ids': []
        })
        
        # Add each selected receipt as a line in the voucher
        for receipt in valid_receipts:
            voucher_line_vals = {
                'receipt_id': receipt.id,
                'amount_to_receive': receipt.amount_total
            }
            
            voucher.write({
                'line_ids': [(0, 0, voucher_line_vals)]
            })

        # Open the created receipt voucher
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.receipt.voucher',
            'view_mode': 'form',
            'res_id': voucher.id,
            'target': 'current'
        }

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


    def receipt_get_unpaid_moves(self):
        """
        RV-ready helper method: return posted invoices in this receipt with residual > 0.
        """
        self.ensure_one()
        return self.line_ids.filtered(lambda line: line.amount_residual != 0).mapped('move_id')

    def receipt_build_payment_context(self, journal_id=None, memo_suffix=None):
        """
        RV-ready helper method: return standard context for account.payment.register.
        """
        self.ensure_one()
        communication = f"Receipt {self.name}"
        if memo_suffix:
            communication += f" {memo_suffix}"
        
        ctx = {
            'active_model': 'account.move',
            'active_ids': self.receipt_get_unpaid_moves().ids,
            'default_partner_id': self.partner_id.id,
            'default_payment_type': 'inbound',
            'default_payment_date': self.date,
            'default_communication': communication,
            'default_is_batch_payment': True,
            'default_is_multiline_batch': True,
            'buz_receipt_id': self.id,
            'default_buz_receipt_id': self.id,
        }
        
        if journal_id:
            ctx['default_journal_id'] = journal_id
        
        # Check if account_payment_batch_process module is installed
        has_batch_process = 'account.payment.batch' in self.env.registry
        if has_batch_process:
            ctx['from_batch_receipt'] = True
            ctx['batch_receipt_id'] = self.id
            ctx['default_batch_receipt_id'] = self.id
            
        return ctx
    
    def receipt_link_payments(self, payments):
        """
        RV-ready helper method: persist links for audit.
        Links payments to this receipt using the M2M relation.
        """
        self.ensure_one()
        # Link the payments to the receipt using the M2M field
        if payments:
            self.write({
                'payment_ids': [(4, payment.id) for payment in payments]
            })
        
        # Update receipt's related invoices' amount_residuals to trigger recompute
        if self.line_ids:
            self.line_ids._compute_paid()
            # Trigger recompute of receipt's total amount
            self._compute_amount_total()
            self._compute_amount_invoice_total()
            self._compute_payment_count()  # Update the payment count as well
        
        # Force a write to trigger all computed fields
        self.write({
            'amount_total': self.amount_total,
            'amount_invoice_total': self.amount_invoice_total
        })
        
        # Log in chatter if tracking is enabled
        if hasattr(self, 'message_post'):
            payment_names = ', '.join(payments.mapped('name'))
            self.message_post(
                body=_("Payments linked: %s") % payment_names,
                message_type='notification'
            )

    def receipt_reconcile_with_payment(self, payment):
        """
        RV-ready helper method: auto-reconcile payment receivable line with receivable lines from underlying invoices (partial-friendly).
        """
        self.ensure_one()
        
        # Get the payment's receivable move line
        payment_move_line = payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable'
        )
        
        if not payment_move_line:
            raise UserError(_("No receivable line found for payment %s") % payment.name)
        
        # Get all the invoice move lines that are receivable from this receipt
        invoice_move_lines = self.env['account.move.line']
        for line in self.line_ids:
            if line.move_id:
                invoice_move_lines |= line.move_id.line_ids.filtered(
                    lambda line: line.account_id.account_type == 'asset_receivable'
                )
        
        # Also include customer refunds (which have a different account type)
        for line in self.line_ids:
            if line.move_id and line.move_id.move_type == 'out_refund':
                invoice_move_lines |= line.move_id.line_ids.filtered(
                    lambda line: line.account_id.account_type == 'liability_payable'
                )
        
        # Add the payment reconciliation to each invoice line
        lines_to_reconcile = (payment_move_line + invoice_move_lines).filtered(
            lambda line: not line.reconciled
        )
        
        # Perform the reconciliation if possible
        if len(lines_to_reconcile) > 1:
            try:
                lines_to_reconcile.reconcile()
            except Exception as e:
                raise UserError(_("Could not reconcile payment %s with invoices: %s") % (payment.name, str(e)))

    def action_register_batch_payment(self):
        """
        Open the standard account.payment.register wizard to register batch payment for all invoices in this receipt.
        """
        self.ensure_one()
        
        # Check state condition
        if self.state != 'posted':
            raise UserError(_("Register Batch Payment is only available for posted receipts."))
        
        # Get all invoices linked to this receipt that have residual amounts (not fully paid)
        invoices = self.line_ids.filtered(lambda line: line.amount_residual != 0).mapped('move_id')
        
        # Check if there are unpaid invoices
        if invoices:
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
                    'default_payment_date': self.date,
                    'default_communication': f"Receipt {self.name}",
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
        else:
            # No unpaid invoices - check if outstanding fallback is enabled
            allow_outstanding_fallback = self.env['ir.config_parameter'].sudo().get_param(
                'buz_account_receipt.allow_outstanding_fallback', default=True
            )
            
            if allow_outstanding_fallback and self.amount_total > 0:
                # Create an on-account inbound payment for this partner
                # Find default journal if specified in settings
                default_journal_id = self.env['ir.config_parameter'].sudo().get_param(
                    'buz_account_receipt.default_bank_journal_id'
                )
                journal = None
                if default_journal_id:
                    try:
                        journal = self.env['account.journal'].browse(int(default_journal_id))
                        if not journal.exists():
                            journal = None
                    except ValueError:
                        journal = None
                
                # If no default journal or it doesn't exist, let user select
                if not journal:
                    journal = self.env['account.journal'].search([
                        ('type', 'in', ('bank', 'cash')),
                        ('company_id', '=', self.company_id.id)
                    ], limit=1)
                
                # Create the payment record
                payment_vals = {
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                    'partner_id': self.partner_id.id,
                    'amount': self.amount_total,
                    'date': self.date,
                    'ref': f"Receipt {self.name}",
                    'company_id': self.company_id.id,
                    'currency_id': self.currency_id.id,
                    'payment_method_line_id': journal.inbound_payment_method_line_ids[0].id if journal and journal.inbound_payment_method_line_ids else None,
                }
                
                if journal:
                    payment_vals['journal_id'] = journal.id
                
                payment = self.env['account.payment'].create(payment_vals)
                
                # Link the payment to the receipt using M2M
                self.write({
                    'payment_ids': [(4, payment.id)]
                })
                
                # Open the payment form view for user to finalize
                return {
                    'name': _('Register Payment'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'account.payment',
                    'view_mode': 'form',
                    'res_id': payment.id,
                    'target': 'new',
                    'context': {
                        'default_buz_receipt_id': self.id,
                        'buz_receipt_id': self.id
                    }
                }
            else:
                raise UserError(_("There are no invoices with outstanding amounts linked to this receipt to register payment for."))

    @api.depends()
    def _compute_used_in_voucher(self):
        """Compute whether a receipt has been used in any receipt voucher"""
        for receipt in self:
            existing_line = self.env['account.receipt.voucher.line'].search([('receipt_id', '=', receipt.id)], limit=1)
            receipt.used_in_voucher = bool(existing_line)

    used_in_voucher = fields.Boolean(
        string="Used in Voucher",
        compute="_compute_used_in_voucher",
        store=True,
        help="Indicates if this receipt has been used in a receipt voucher"
    )


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

    # Use signed amounts for proper multi-currency and refund handling
    amount_total_signed = fields.Monetary(
        string="Invoice Total (Signed)", 
        related="move_id.amount_total_signed",
        currency_field="currency_id",
        store=True,
        help="Signed total amount of the invoice (negative for refunds)"
    )
    amount_residual_signed = fields.Monetary(
        string="Invoice Residual (Signed)", 
        related="move_id.amount_residual_signed",
        currency_field="currency_id",
        store=True,
        help="Signed residual amount of the invoice (negative for refunds)"
    )
    
    # Legacy fields for compatibility
    amount_total = fields.Monetary(
        string="Amount Total", 
        currency_field="currency_id",
        compute="_compute_amount_total",
        store=True
    )
    amount_residual = fields.Monetary(
        string="Residual", 
        currency_field="currency_id",
        compute="_compute_amount_residual",
        store=True
    )
    
    # Computed paid-to-date field
    amount_paid_to_date = fields.Monetary(
        string="Paid to Date", 
        currency_field="currency_id",
        compute="_compute_amount_paid_to_date",
        store=True,
        help="Amount already paid on this invoice (Total - Residual)"
    )
    
    amount_paid = fields.Monetary(
        string="Amount Paid", 
        currency_field="currency_id", 
        compute="_compute_paid", 
        store=True,
        help="For this receipt line, represents the amount_to_collect"
    )
    amount_to_collect = fields.Monetary(
        string="To Collect (This Receipt)", 
        currency_field="currency_id",
        help="Amount expected to be received in this receipt (default: residual amount)",
        default=0.0
    )
    
    @api.depends('move_id', 'move_id.amount_total', 'move_id.amount_total_signed')
    def _compute_amount_total(self):
        """Compute amount_total using signed amounts for refunds"""
        for line in self:
            if line.move_id:
                if line.move_id.move_type == 'out_refund':
                    line.amount_total = line.move_id.amount_total_signed
                else:
                    line.amount_total = line.move_id.amount_total
            else:
                line.amount_total = 0.0
    
    @api.depends('move_id', 'move_id.amount_residual', 'move_id.amount_residual_signed')
    def _compute_amount_residual(self):
        """Compute amount_residual using signed amounts for refunds"""
        for line in self:
            if line.move_id:
                if line.move_id.move_type == 'out_refund':
                    line.amount_residual = line.move_id.amount_residual_signed
                else:
                    line.amount_residual = line.move_id.amount_residual
            else:
                line.amount_residual = 0.0
    
    @api.depends('amount_total_signed', 'amount_residual_signed')
    def _compute_amount_paid_to_date(self):
        """Compute the amount paid to date: Total - Residual"""
        for line in self:
            line.amount_paid_to_date = line.amount_total_signed - line.amount_residual_signed

    @api.onchange('move_id')
    def _onchange_move_id_set_amounts(self):
        """When invoice is selected on the line, set amount_to_collect to residual by default."""
        for line in self:
            if line.move_id:
                # The signed fields are related and will be computed automatically
                # We just need to set amount_to_collect to the residual
                if line.move_id.move_type == 'out_refund':
                    line.amount_to_collect = line.move_id.amount_residual_signed
                else:
                    line.amount_to_collect = line.move_id.amount_residual
            else:
                line.amount_to_collect = 0.0

    @api.model
    def create(self, vals):
        """Override create to set amount_to_collect = residual if not provided"""
        res = super(AccountReceiptLine, self).create(vals)
        # If amount_to_collect wasn't provided, set it to residual
        if res.move_id and (not vals.get('amount_to_collect') or vals.get('amount_to_collect') == 0.0):
            if res.move_id.move_type == 'out_refund':
                res.amount_to_collect = res.move_id.amount_residual_signed
            else:
                res.amount_to_collect = res.move_id.amount_residual
        return res

    @api.constrains('amount_to_collect', 'amount_residual_signed')
    def _check_amount_to_collect_not_greater_than_residual(self):
        """Prevent amount_to_collect > amount_residual_signed per line (with small tolerance)"""
        for line in self:
            if line.move_id and line.amount_residual_signed != 0:
                # Use signed residual amount for correct handling of both invoices and refunds
                residual = abs(line.amount_residual_signed)
                to_collect = abs(line.amount_to_collect)
                # Small tolerance for floating point comparison
                tolerance = 0.01
                if to_collect > (residual + tolerance):
                    raise UserError(
                        _("Amount to collect (%s) cannot be greater than residual amount (%s) for invoice %s.")
                        % (line.amount_to_collect, line.amount_residual_signed, line.move_id.name)
                    )

    @api.constrains('move_id', 'receipt_id')
    def _check_duplicate_invoice_in_receipt(self):
        """Prevent adding the same invoice multiple times to the same receipt"""
        for line in self:
            if line.move_id and line.receipt_id:
                # Count how many times this invoice appears in the receipt
                duplicate_lines = self.search([
                    ('receipt_id', '=', line.receipt_id.id),
                    ('move_id', '=', line.move_id.id),
                    ('id', '!=', line.id)  # Exclude current line to allow updates
                ])
                
                if duplicate_lines:
                    raise UserError(
                        _("Invoice %s is already included in this receipt. You cannot add the same invoice multiple times to a single receipt.")
                        % line.move_id.name
                    )

    @api.depends("amount_total", "amount_residual", "amount_to_collect", "move_id.amount_residual", "move_id.amount_residual_signed", "move_id.amount_total", "move_id.amount_total_signed", "move_id.payment_state")
    def _compute_paid(self):
        """Compute the paid amount for each receipt line based on the actual payment status of the underlying invoice.
        The amount_paid represents what has been paid on the invoice itself, not just in this receipt."""
        for line in self:
            if line.move_id:
                # Calculate the amount already paid on the underlying invoice
                # For refunds, use signed amounts
                total = line.move_id.amount_total_signed if line.move_id.move_type == 'out_refund' else line.move_id.amount_total
                residual = line.move_id.amount_residual_signed if line.move_id.move_type == 'out_refund' else line.move_id.amount_residual
                # The actual amount paid on the invoice (total - residual)
                actual_paid_on_invoice = total - residual
                line.amount_paid = actual_paid_on_invoice
            else:
                line.amount_paid = (line.amount_total or 0.0) - (line.amount_residual or 0.0)

    def action_register_payment_line(self):
        """Open invoice in popup window for verification."""
        self.ensure_one()
        
        if not self.move_id:
            raise UserError(_("Please select an invoice first."))
            
        # Validate the invoice
        if self.move_id.state != 'posted':
            raise UserError(_("Invoice %s is not in 'Posted' state.") % self.move_id.name)
        
        if self.move_id.move_type not in ['out_invoice', 'out_refund']:
            raise UserError(_("Selected document is not a customer invoice or refund."))
            
        # Open the invoice in popup window
        return {
            'name': _('Invoice Details - %s') % self.move_id.name,
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
                    # Also update the payment state to reflect changes in underlying invoices
                    receipt._compute_payment_state()
        
        return res
