from odoo import models, fields, api


class ChequeAttribute(models.Model):
    _name = 'cheque.attribute'
    _description = "Cheque Attributes"

    # Selection field for predefined cheque attributes
    attribute_name = fields.Selection([
        ('cheque_date', 'Cheque Date'),
        ('pay_to', 'Pay To'),
        ('amount_words1', 'Amount In Words Line1'),
        ('amount_words2', 'Amount In Words Line2'),
        ('amount_box', 'Amount Box'),
        ('account_number', 'Account Number'),
        ('a_c_label', 'A/C Label')
    ], string="Attribute Name", required=True)

    name = fields.Char(string="Attribute")

    # Styling fields for cheque attributes
    font_size = fields.Integer(string="Font Size", default=20)
    letter_space = fields.Integer(string="Letter Space", default=0)
    top_displacement = fields.Float(string="Top Displacement", default=0.0)
    left_displacement = fields.Float(string="Left Displacement", default=0.0)
    height = fields.Float(string="Height", default=0.0)
    width = fields.Float(string="Width", default=0.0)

    cheque_id = fields.Many2one("bank.cheque", string="Cheque", ondelete="cascade")
    background_image = fields.Binary("Cheque Background Image")

    bank_cheque_id = fields.Many2one("bank.cheque", string="Cheque Attributes")

    # Fields for dynamic positioning (Bounding Box)
    x1 = fields.Integer("X1")
    y1 = fields.Integer("Y1")
    x2 = fields.Integer("X2")
    y2 = fields.Integer("Y2")

    @api.model
    def update_coordinates(self, attribute_id, x1, y1, x2, y2):
        """Update the coordinates of the attribute"""
        record = self.browse(attribute_id)
        if record:
            record.write({'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2})
            return {"status": "success"}
        return {"status": "error"}

    def action_print_test(self):
        """
        Print a test cheque to make corrections for the user in cheque format.
        """
        data = {
            'width': self.width,
            'height': self.height,
            'font_size': self.font_size,
            'number': self.cheque_id.number if self.cheque_id else '',
            'cheque_no_tm': self.top_displacement,
            'cheque_no_lm': self.left_displacement,
            'is_account_payee': True,
            'a_c_payee_top_margin': self.top_displacement,
            'a_c_payee_left_margin': self.left_displacement,
            'a_c_payee_width': self.width,
            'a_c_payee_height': self.height,
            'date_top_margin': self.top_displacement,
            'date_left_margin': self.left_displacement,
            'date_letter_spacing': self.letter_space,
            'beneficiary_top_margin': self.top_displacement,
            'beneficiary_left_margin': self.left_displacement,
            'amount_word_tm': self.top_displacement,
            'amount_word_lm': self.left_displacement,
            'amount_word_ls': self.letter_space,
            'amount_digit_tm': self.top_displacement,
            'amount_digit_lm': self.left_displacement,
            'amount_digit_ls': self.letter_space,
            'amount_digit_size': self.font_size,
            'print_currency': True,
            'currency_symbol': self.env.company.currency_id.symbol,
            'date_remove_slashes': False
        }

        account_attr = data.cheque_book_id.bank_id.cheque_attribute_ids.filtered(
            lambda a: a.attribute_name == 'account_number')
        if account_attr:
            data.update({
                'account_number': data.account_number,
                'account_number_lm': 100,  # replace with attribute.x1
                'account_number_tm': 200,  # replace with attribute.y1
                'account_number_ls': 0.1,
                'account_number_size': 14,
            })

        return self.env.ref(
            'sttl_dynamic_bank_cheque_print.action_print_test'
        ).report_action(None, data=data)

    @api.onchange('x1', 'y1', 'x2', 'y2')
    def render_preview(self):
        print('*****************************************')
        print(self.bank_cheque_id)
        print('*****************************************')
