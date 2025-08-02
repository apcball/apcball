from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class ChequePrint(models.TransientModel):
    _name = 'cheque.print'
    _description = "Cheque Print Wizard"

    pay_to = fields.Char("Pay To")
    cheque_date = fields.Date("Cheque Date")
    amount = fields.Monetary("Amount")
    amount_in_words = fields.Char("Amount in Words")
    amount_in_words_2 = fields.Char("Amount in Words")
    amt_2_words = fields.Char("Amount in Words")
    account_number = fields.Char(related="cheque_book_id.account_number", string="Account Number")
    print_a_c_label = fields.Boolean(string="A/C Pay Label", default=False)

    report_preview = fields.Html()
    show_preview = fields.Boolean('Show Preview?')

    # MANY2ONE FIELDS
    cheque_book_id = fields.Many2one("cheque.book", 'Cheque Book')
    cheque_background = fields.Binary("Cheque Background Image")
    cheque_number_id = fields.Many2one(
        "cheque.leaf",
        string="Cheque Number",
        domain="[('cheque_book_id', '=', cheque_book_id),('is_used', '=', False)]"
    )

    customer_id = fields.Many2one("res.partner", 'Customer')
    date_on_cheque = fields.Date("Date on cheque")

    # CURRENCY FIELDS
    print_currency = fields.Boolean(string="Print Currency", default=True)
    currency_id = fields.Many2one('res.currency', string="Currency")
    currency_symbol = fields.Char(related="currency_id.symbol", string="Currency Symbol", readonly=True)

    # DYNAMIC FIELD POSITIONS FOR DRAG & DROP
    pay_to_x = fields.Integer(string="Payee X", default=100)
    pay_to_y = fields.Integer(string="Payee Y", default=50)

    amount_x = fields.Integer(string="Amount X", default=500)
    amount_y = fields.Integer(string="Amount Y", default=200)

    date_x = fields.Integer(string="Date X", default=600)
    date_y = fields.Integer(string="Date Y", default=50)

    @api.onchange('amount', 'currency_id', 'print_currency')
    def _onchange_amount_in_words(self):
        for record in self:
            if record.amount and record.currency_id:

                full_text = record.currency_id.amount_to_text(record.amount).replace(",", "").title()

                record.amt_2_words = full_text

                # Split the sentence into two lines
                words = full_text.split()
                first_line = ""
                second_line = ""
                for word in words:
                    if len(first_line) + len(word) + 1 <= 27:
                        if first_line:
                            first_line += " "
                        first_line += word
                    else:
                        if second_line:
                            second_line += " "
                        second_line += word

                record.amount_in_words = first_line
                record.amount_in_words_2 = second_line
            else:
                record.amount_in_words = ""
                record.amount_in_words_2 = ""
                record.amt_2_words = ""

    @api.depends('cheque_book_id')
    def _compute_cheque_background(self):
        for record in self:
            if record.cheque_book_id and record.cheque_book_id.bank_id:
                record.cheque_background = record.cheque_book_id.bank_id.cheque_image
            else:
                record.cheque_background = False

    def action_print_preview(self):
        for record in self:
            record.show_preview = True
            record.cheque_background = record.cheque_book_id.bank_id.cheque_image or False

            if record.amount and record.currency_id:
                amount_words = record.currency_id.amount_to_text(record.amount).replace(",", "").title()
                if record.print_currency:
                    amount_words = f"{amount_words} Only"

                # Save full text in amt_2_words
                record.amt_2_words = amount_words

                #     # Split amount_words into two lines
                words = amount_words.split()
                line1 = ""
                line2 = ""
                max_line1_length = 65

                for word in words:
                    if len(line1 + ' ' + word) <= max_line1_length:
                        if line1:
                            line1 += ' ' + word
                        else:
                            line1 = word
                    else:
                        # Once limit reached, put rest in line2
                        remaining_words = words[words.index(word):]
                        line2 = ' '.join(remaining_words)
                        break

                record.amount_in_words = line1
                record.amount_in_words_2 = line2

            if record.cheque_number_id:
                record.cheque_number_id.amount = record.amount

            self.report_preview = self.env['ir.ui.view']._render_template(
                f'sttl_dynamic_bank_cheque_print.cheque_print_preview_template',
                {
                    'docs': self
                })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_hide_preview(self):
        self.show_preview = False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_print_cheque(self):
        for record in self:
            record.cheque_background = record.cheque_book_id.bank_id.cheque_image or False

            if record.amount and record.currency_id:
                # Convert amount to words
                amount_words = record.currency_id.amount_to_text(record.amount).replace(",", "").title()
                if record.print_currency:
                    amount_words = f"{amount_words} Only"

                # Save full version to amt_2_words
                record.amt_2_words = amount_words

                # Split into two lines
                words = amount_words.split()
                first_line = ""
                second_line = ""
                for word in words:
                    if len(first_line) + len(word) + 1 <= 27:
                        if first_line:
                            first_line += " "
                        first_line += word
                    else:
                        if second_line:
                            second_line += " "
                        second_line += word

                record.amount_in_words = first_line
                record.amount_in_words_2 = second_line
            else:
                record.amount_in_words = ""
                record.amount_in_words_2 = ""
                record.amt_2_words = ""

            # Enforce usage check and mark cheque as used
            if record.cheque_number_id:
                if record.cheque_number_id.is_used:
                    raise ValidationError(
                        f"The cheque number '{record.cheque_number_id.number}' has already been used. Please select another cheque."
                    )
                record.cheque_number_id.is_used = True
                record.cheque_number_id.amount = record.amount
                record.cheque_number_id.payee_name = record.pay_to
                record.cheque_number_id.date = record.cheque_date or record.date_on_cheque

        return self.env.ref('sttl_dynamic_bank_cheque_print.cheque_print_preview_report').report_action(self)

    def action_open_cheque_attribute_page(self):
        """Redirects the user to the cheque attribute configuration page"""
        return {
            'type': 'ir.actions.act_url',
            'target': 'new'
        }

    @api.onchange('cheque_number_id')
    def _check_cheque_issue(self):
        for record in self:
            if record.cheque_number_id:
                print(record.cheque_number_id.is_used, "\n\n\nHello3")
                if record.cheque_number_id.is_used:
                    raise ValidationError(
                        f"The cheque number '{record.cheque_number_id.number}' has already been used. Please select another cheque."
                    )
