from odoo import models, fields, api

class ChequeAttributeWizard(models.TransientModel):
    _name = 'cheque.attribute.wizard'
    _description = "Configure Cheque Attributes"

    bank_cheque_id = fields.Many2one('bank.cheque', string="Cheque Format", required=True)
    cheque_image = fields.Binary(related='bank_cheque_id.cheque_image')

    width = fields.Float(string="Width", related='bank_cheque_id.cheque_width', readonly=False)
    height = fields.Float(string="Height", related='bank_cheque_id.cheque_height', readonly=False)
    font_size = fields.Float(string="Font Size", related='bank_cheque_id.font_size', readonly=False)

    # Fields for positioning
    cheque_no_lm = fields.Float(string="Cheque No Left Margin", related='bank_cheque_id.cheque_no_lm', readonly=False)
    cheque_no_tm = fields.Float(string="Cheque No Top Margin", related='bank_cheque_id.cheque_no_tm', readonly=False)
    amount_word_lm = fields.Float(string="Amount in Words Left Margin", related='bank_cheque_id.amount_word_lm',
                                  readonly=False)
    amount_word_tm = fields.Float(string="Amount in Words Top Margin", related='bank_cheque_id.amount_word_tm',
                                  readonly=False)

    @api.model
    def default_get(self, fields):
        """ Preload cheque data into the wizard. """
        res = super().default_get(fields)
        active_id = self.env.context.get('active_id')
        if active_id:
            res['bank_cheque_id'] = active_id
        return res

    def action_save_attributes(self):
        """ Saves the user-modified cheque attributes into `bank.cheque` """
        if self.bank_cheque_id:
            self.bank_cheque_id.write({
                'cheque_width': self.width or self.bank_cheque_id.cheque_width,
                'cheque_height': self.height or self.bank_cheque_id.cheque_height,
                'font_size': self.font_size or self.bank_cheque_id.font_size,
                'cheque_no_lm': self.cheque_no_lm or self.bank_cheque_id.cheque_no_lm,
                'cheque_no_tm': self.cheque_no_tm or self.bank_cheque_id.cheque_no_tm,
                'amount_word_lm': self.amount_word_lm or self.bank_cheque_id.amount_word_lm,
                'amount_word_tm': self.amount_word_tm or self.bank_cheque_id.amount_word_tm
            })
        return {'type': 'ir.actions.act_window_close'}

