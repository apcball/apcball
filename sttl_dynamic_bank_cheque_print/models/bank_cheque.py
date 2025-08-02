from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class BankCheque(models.Model):
    _name = 'bank.cheque'
    _description = "Bank Cheque Configuration"

    @api.constrains('phone')
    def _check_mobile_number_numeric(self):
        for record in self:
            if record.phone and not record.phone.isdigit():
                raise ValidationError("phone number must contain only digits.")

    name = fields.Char(string="Name", required=True)
    bank_identifier_code = fields.Char(string="Bank Identifier Code")
    bank_address = fields.Text(string="Bank Address")
    phone = fields.Char(string="Phone Number")
    email = fields.Char(string="Email")
    font_size = fields.Float(string="Font Size", default=20)
    cheque_image = fields.Binary(string="Cheque Image", required=True, attachment=True)
    cheque_no_lm = fields.Float(string="Cheque No Left Margin")
    cheque_no_tm = fields.Float(string="Cheque No Top Margin")
    amount_word_lm = fields.Float(string="Amount in Words Left Margin")
    amount_word_tm = fields.Float(string="Amount in Words Top Margin")

    cheque_height = fields.Float(string="Cheque Height")
    cheque_width = fields.Float(string="Cheque Width")
    maximum_characters = fields.Integer(string="Maximum Characters")

    cheque_attribute_ids = fields.One2many("cheque.attribute", "cheque_id", string="Cheque Attributes")

    report_preview = fields.Html("Live Cheque Preview", compute="_compute_preview_fields", store=True)
    cheque_background = fields.Binary("Cheque Background Image", compute="_compute_preview_fields", store=False)

    @api.depends('cheque_image', 'font_size')
    def _compute_preview_fields(self):
        for record in self:
            record.cheque_background = record.cheque_image
            record.report_preview = record.env['ir.ui.view']._render_template(
                'sttl_dynamic_bank_cheque_print.bank_cheque_preview_template',
                {'docs': record}
            )

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)

        print('$$$$$$$$$$$$$$4', self.font_size)
        default_lines = []
        attributes = [
            ('cheque_date', 'Cheque Date'),
            ('pay_to', 'Pay To'),
            ('amount_words1', 'Amount In Words Line1'),
            ('amount_words2', 'Amount In Words Line2'),
            ('amount_box', 'Amount Box'),
            ('account_number', 'Account Number'),
            ('a_c_label', 'A/C Label')
        ]

        for attr_name, _ in attributes:
            default_lines.append((0, 0, {
                'attribute_name': attr_name,
                'x1': 0,
                'x2': 0,
                'y1': 0,
                'y2': 0,
                'top_displacement': 0.0,
                'left_displacement': 0.0,
                'width': 0.0,
                'height': 0.0,
                'letter_space': 0,
            }))

        res['cheque_attribute_ids'] = default_lines
        return res

    def get_amount_category(self):
        for record in self:
            record.amount_category = "Small" if record.amount and record.amount < 1000 else "Large"

    def action_configure_attributes(self):
        """ Open a wizard to configure cheque attributes """
        return {
            'type': 'ir.actions.client',
            'tag': 'cheque.configure.popup',
            'params': {'cheque_id': self.id},
        }
