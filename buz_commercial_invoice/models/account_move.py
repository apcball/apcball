from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    commercial_invoice_number = fields.Char(
        string='Commercial Invoice No.',
        readonly=True,
        copy=False,
        tracking=True,
    )
    incoterms_id = fields.Many2one(
        'account.incoterms',
        string='Incoterms',
        tracking=True,
    )
    loading_date = fields.Date(
        string='Loading Date',
        tracking=True,
    )
    shipping_mark = fields.Char(
        string='Shipping Mark',
        tracking=True,
    )
    shipping_by = fields.Selection([
        ('air', 'By Air'),
        ('sea', 'By Sea'),
        ('land', 'By Land'),
    ], string='Shipping By', tracking=True)
    bank_info = fields.Text(
        string='Bank Information',
        tracking=True,
    )
    amount_text = fields.Char(
        string='Amount in Words',
        compute='_compute_amount_text',
        store=True,
    )

    @api.depends('amount_total', 'currency_id')
    def _compute_amount_text(self):
        """Compute the total amount in words."""
        for record in self:
            record.amount_text = record.currency_id.amount_to_text(record.amount_total)

    @api.model_create_multi
    def create(self, vals_list):
        """Override create method to add commercial invoice number."""
        for vals in vals_list:
            if vals.get('move_type') == 'out_invoice' and not vals.get('commercial_invoice_number'):
                vals['commercial_invoice_number'] = self._get_commercial_invoice_number()
        return super().create(vals_list)

    def _get_commercial_invoice_number(self):
        """Get next commercial invoice number from sequence."""
        return self.env['ir.sequence'].next_by_code('commercial.invoice.sequence')

    def action_post(self):
        """Override post method to check required fields."""
        for move in self:
            if move.move_type == 'out_invoice':
                if not move.commercial_invoice_number:
                    move.commercial_invoice_number = move._get_commercial_invoice_number()
        return super().action_post()