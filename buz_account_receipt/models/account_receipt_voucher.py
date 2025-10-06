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

    def action_confirm(self):
        """Confirm the voucher and create payments for each partner"""
        for voucher in self:
            if voucher.state != 'draft':
                continue
                
            # Group lines by partner
            partner_groups = {}
            for line in voucher.line_ids:
                partner_id = line.partner_id.id
                if partner_id not in partner_groups:
                    partner_groups[partner_id] = []
                partner_groups[partner_id].append(line)

            # For each partner, create a single inbound payment
            for partner_id, lines in partner_groups.items():
                partner = self.env['res.partner'].browse(partner_id)
                
                # Collect all invoices from receipts associated with this partner
                moves = self.env['account.move']
                for line in lines:
                    moves |= line.receipt_id.line_ids.move_id
                
                # Filter to only invoices that still have unpaid amounts
                unpaid_moves = moves.filtered(lambda m: m.amount_residual != 0)
                
                if not unpaid_moves:
                    raise UserError(_("No unpaid invoices found for partner %s in this voucher") % partner.name)
                
                # Calculate total amount to receive for this partner
                total_amount = sum(line.amount_to_receive for line in lines)
                
                # Create inbound payment for this partner
                payment = self.env['account.payment'].create({
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                    'partner_id': partner.id,
                    'amount': total_amount,
                    'date': voucher.date,
                    'journal_id': self.env['account.journal'].search([
                        ('type', 'in', ('bank', 'cash')), 
                        ('company_id', '=', voucher.company_id.id)
                    ], limit=1).id,
                    'ref': f"RV {voucher.name}",
                    'company_id': voucher.company_id.id,
                    'currency_id': voucher.currency_id.id,
                })
                
                # Post the payment
                payment.action_post()
                
                # Reconcile the payment with the invoices
                self._reconcile_payment_with_invoices(payment, unpaid_moves)
                
                # Add payment to chatter
                voucher.message_post(body=_("Payment %s created for partner %s") % (payment.name, partner.name))

            # Set voucher state to confirmed
            voucher.state = 'confirmed'
        return True

    def _reconcile_payment_with_invoices(self, payment, invoices):
        """Reconcile the payment with the provided invoices"""
        # This is a simplified reconciliation approach
        # In a real implementation, you would need to handle partial payments properly
        
        # Get the payment's receivable move line
        payment_move_line = payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable'
        )
        
        if not payment_move_line:
            _logger.warning("No receivable line found for payment %s" % payment.name)
            return
        
        # Get the invoice move lines that are receivable 
        invoice_move_lines = self.env['account.move.line']
        for invoice in invoices:
            invoice_move_lines |= invoice.line_ids.filtered(
                lambda line: line.account_id.account_type == 'asset_receivable'
            )
        # Also include customer refunds (which have a different account type)
        for invoice in invoices:
            invoice_move_lines |= invoice.line_ids.filtered(
                lambda line: line.account_id.account_type == 'liability_payable'
            )
        
        # Add the payment reconciliation to each invoice line
        lines_to_reconcile = (payment_move_line + invoice_move_lines).filtered(
            lambda line: line.reconciled is False
        )
        
        # Perform the reconciliation
        if len(lines_to_reconcile) > 1:
            lines_to_reconcile.reconcile()

    def action_register_payments(self):
        """Button action to confirm and register payments"""
        return self.action_confirm()
    
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
    receipt_id = fields.Many2one("account.receipt", string="Receipt", required=True, domain="[('state', '=', 'posted')]")
    partner_id = fields.Many2one("res.partner", string="Partner", related="receipt_id.partner_id", store=True)
    
    # Amount to receive for this receipt in the voucher
    amount_to_receive = fields.Monetary(
        string="Amount to Receive",
        currency_field="currency_id",
        default=lambda self: 0.0,
        help="Amount to receive from this receipt in the voucher"
    )
    currency_id = fields.Many2one(related="voucher_id.currency_id", store=True, readonly=True)
    
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