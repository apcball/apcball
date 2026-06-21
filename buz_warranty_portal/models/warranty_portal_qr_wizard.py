import base64
import io

try:
    import qrcode
except ImportError:
    qrcode = None

from odoo import api, fields, models


class WarrantyPortalQrWizard(models.TransientModel):
    _name = 'warranty.qr.wizard'
    _description = 'Customer Registration QR'

    registration_url = fields.Char(string='Portal URL')
    qr_code = fields.Binary(string='QR Code')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        url = f"{base_url}/warranty/register"
        res['registration_url'] = url
        if qrcode:
            qr = qrcode.QRCode(
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=15, border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            buf = io.BytesIO()
            qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
            res['qr_code'] = base64.b64encode(buf.getvalue()).decode()
        return res

    def action_done(self):
        return {'type': 'ir.actions.act_window_close'}