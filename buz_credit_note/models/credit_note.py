from odoo import models, fields, api
from num2words import num2words

class AccountMove(models.Model):
    _inherit = 'account.move'

    # Existing fields
    custom_document_number = fields.Char(string='Custom Document Number', readonly=True)
    custom_return_number = fields.Char(string='Custom Return Number', readonly=True)
    original_tax_invoice_number = fields.Char(string='Original Tax Invoice Number', readonly=True)
    original_tax_invoice_date = fields.Date(string='Original Tax Invoice Date', readonly=True)

    # New fields for calculations
    original_amount = fields.Float(string='มูลค่าสินค้าตามใบกำกับภาษีเดิม', compute='_compute_original_amount')
    correct_amount = fields.Float(string='มูลค่าของสินค้าที่ถูกต้อง', compute='_compute_correct_amount')
    difference_amount = fields.Float(string='ผลต่าง', compute='_compute_difference_amount')
    vat_amount = fields.Float(string='ภาษีมูลค่าเพิ่ม 7%', compute='_compute_vat_amount')
    net_total = fields.Float(string='รวมยอดสุทธิ', compute='_compute_net_total')

    @api.model
    def create(self, vals):
        if vals.get('move_type') == 'out_refund':
            sequence = self.env['ir.sequence'].next_by_code('credit.note.sequence')
            vals['custom_document_number'] = sequence
            return_sequence = self.env['ir.sequence'].next_by_code('return.note.sequence')
            vals['custom_return_number'] = return_sequence
        return super(AccountMove, self).create(vals)

    def amount_to_text_thai(self):
        self.ensure_one()
        amount_text = num2words(self.amount_total, lang='th')
        return amount_text + 'บาทถ้วน'

    @api.depends('invoice_line_ids')
    def _compute_original_amount(self):
        for record in self:
            record.original_amount = sum(line.price_unit * line.quantity for line in record.invoice_line_ids)

    @api.depends('invoice_line_ids')
    def _compute_correct_amount(self):
        for record in self:
            record.correct_amount = sum((line.price_unit * line.quantity) * (1 - (line.discount or 0.0) / 100.0)
                                      for line in record.invoice_line_ids)

    @api.depends('original_amount', 'correct_amount')
    def _compute_difference_amount(self):
        for record in self:
            record.difference_amount = record.original_amount - record.correct_amount

    @api.depends('difference_amount')
    def _compute_vat_amount(self):
        for record in self:
            record.vat_amount = record.difference_amount * 0.07

    @api.depends('difference_amount', 'vat_amount')
    def _compute_net_total(self):
        for record in self:
            record.net_total = record.difference_amount + record.vat_amount

    def action_print_credit_note(self):
        """ Print the credit note report """
        return self.env.ref('buz_credit_note.action_report_credit_note').report_action(self)

    # Additional helper methods for formatting
    def format_currency_amount(self, amount):
        return "{:,.2f}".format(amount)

    def get_thai_date(self, date):
        if not date:
            return ''
        # Convert date to Thai Buddhist calendar format
        thai_year = date.year + 543
        return date.strftime('%d/%m/') + str(thai_year)