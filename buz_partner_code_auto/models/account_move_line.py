from odoo import models, fields, api


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    partner_code = fields.Char(
        string='Partner Code',
        help='Partner code for this journal item',
        store=True
    )

    @api.onchange('partner_code')
    def _onchange_partner_code_line(self):
        for line in self:
            if line.partner_code:
                code = line.partner_code.strip().upper()
                partner = self.env['res.partner'].search(
                    [('partner_code', '=ilike', code)], limit=1
                )
                if partner:
                    line.partner_id = partner.id

    @api.onchange('partner_id')
    def _onchange_partner_id_code_line(self):
        for line in self:
            if line.partner_id and line.partner_id.partner_code:
                line.partner_code = line.partner_id.partner_code
