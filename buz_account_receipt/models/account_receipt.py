
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _action_create_receipt_from_partner(self):
        """
        Creates a receipt from this partner's invoices 
        """
        self.ensure_one()
        # Create a receipt for this partner with no initial lines
        receipt = self.env["account.receipt"].create({
            "partner_id": self.id,
            "date": fields.Date.context_today(self),
        })
        
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
        
        # Filter invoices to include only posted ones (removing payment_state restriction to allow receipts before payment)
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
        
        # Create receipt
        receipt = self.env["account.receipt"].create({
            "partner_id": valid_moves[0].partner_id.id,
            "date": fields.Date.context_today(self),
            "line_ids": [],
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

    line_ids = fields.One2many("account.receipt.line", "receipt_id", string="Lines")
    amount_total = fields.Monetary(string="Total Paid", currency_field="currency_id", compute="_compute_amount_total", store=True)
    amount_total_words = fields.Char(
        string="Amount in Words",
        compute="_compute_amount_total_words",
        store=True,
        readonly=True,
    )

    state = fields.Selection([
        ("draft", "Draft"),
        ("posted", "Posted"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True)

    @api.depends("line_ids.amount_paid")
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped("amount_paid"))

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

    def action_reset_to_draft(self):
        self.write({"state": "draft"})
        return True

    def action_print_receipt(self):
        self.ensure_one()
        return self.env.ref("buz_account_receipt.action_report_buz_account_receipt").report_action(self)


class AccountReceiptLine(models.Model):
    _name = "account.receipt.line"
    _description = "Account Receipt Line"
    _order = "invoice_date, id"

    receipt_id = fields.Many2one("account.receipt", string="Receipt", required=True, ondelete="cascade")
    move_id = fields.Many2one("account.move", string="Invoice", domain=[("move_type", "in", ["out_invoice", "out_refund"])], required=True)

    move_name = fields.Char(string="Invoice Number", related="move_id.name", store=True)
    invoice_date = fields.Date(string="Invoice Date", related="move_id.invoice_date", store=True)
    currency_id = fields.Many2one(related="receipt_id.currency_id", store=True, readonly=True)

    amount_total = fields.Monetary(string="Amount Total", currency_field="currency_id")
    amount_residual = fields.Monetary(string="Residual", currency_field="currency_id")
    amount_paid = fields.Monetary(string="Amount Paid", currency_field="currency_id", compute="_compute_paid", store=True)

    @api.depends("amount_total", "amount_residual")
    def _compute_paid(self):
        for line in self:
            line.amount_paid = (line.amount_total or 0.0) - (line.amount_residual or 0.0)
