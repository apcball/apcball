from odoo import fields, models, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    use_pdf_quote_builder = fields.Boolean(
        string="Use Custom PDF Quote Builder",
        config_parameter='buz_custom_quotation.use_pdf_quote_builder'
    )

    sale_header = fields.Binary(
        string='Header Template',
        attachment=True,
    )
    sale_header_name = fields.Char()

    sale_footer = fields.Binary(
        string='Footer Template',
        attachment=True,
    )
    sale_footer_name = fields.Char()

    def get_values(self):
        res = super().get_values()
        ICPSudo = self.env['ir.config_parameter'].sudo()

        # Get binary field values from attachments
        header_attachment = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'res.config.settings'),
            ('name', '=', 'sale_header')
        ], limit=1)

        footer_attachment = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'res.config.settings'),
            ('name', '=', 'sale_footer')
        ], limit=1)

        res.update({
            'use_pdf_quote_builder': ICPSudo.get_param('buz_custom_quotation.use_pdf_quote_builder', False),
            'sale_header': header_attachment.datas if header_attachment else False,
            'sale_header_name': header_attachment.name if header_attachment else '',
            'sale_footer': footer_attachment.datas if footer_attachment else False,
            'sale_footer_name': footer_attachment.name if footer_attachment else '',
        })
        return res

    def set_values(self):
        super().set_values()
        ICPSudo = self.env['ir.config_parameter'].sudo()

        ICPSudo.set_param('buz_custom_quotation.use_pdf_quote_builder', self.use_pdf_quote_builder)

        # Update attachments
        AttachmentSudo = self.env['ir.attachment'].sudo()

        if self.sale_header:
            header_attachment = AttachmentSudo.search([
                ('res_model', '=', 'res.config.settings'),
                ('name', '=', 'sale_header')
            ], limit=1)

            vals = {
                'datas': self.sale_header,
                'name': self.sale_header_name or 'sale_header',
                'res_model': 'res.config.settings',
                'res_field': 'sale_header'
            }

            if header_attachment:
                header_attachment.write(vals)
            else:
                AttachmentSudo.create(vals)

        if self.sale_footer:
            footer_attachment = AttachmentSudo.search([
                ('res_model', '=', 'res.config.settings'),
                ('name', '=', 'sale_footer')
            ], limit=1)

            vals = {
                'datas': self.sale_footer,
                'name': self.sale_footer_name or 'sale_footer',
                'res_model': 'res.config.settings',
                'res_field': 'sale_footer'
            }

            if footer_attachment:
                footer_attachment.write(vals)
            else:
                AttachmentSudo.create(vals)