from odoo import fields, models


class ShareCertificateWizard(models.TransientModel):
    _name = 'buz.share.certificate.wizard'
    _description = 'Share Certificate Print Options'

    certificate_id = fields.Many2one('buz.share.certificate', required=True, ondelete='cascade')

    def _pdf_action(self, mode):
        self.ensure_one()
        certificate = self.certificate_id
        certificate.check_access_rights('read')
        certificate.check_access_rule('read')
        if mode == 'print' and certificate.state == 'draft':
            certificate.write({'state': 'done'})
        return {
            'type': 'ir.actions.client', 'tag': 'buz_share_certificate.pdf',
            'params': {
                'mode': mode,
                'certificate_id': certificate.id,
                'url': '/report/pdf/buz_share_certificate.report_share_certificate/%s' % certificate.id,
            },
        }

    def action_open_pdf(self):
        return self._pdf_action('open')

    def action_download_pdf(self):
        return self._pdf_action('download')

    def action_print_pdf(self):
        return self._pdf_action('print')
