from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        # Expose dark mode config to JS session
        ICP = self.env['ir.config_parameter'].sudo()
        result['buz_theme_odoo19_dark_mode'] = ICP.get_param(
            'buz_theme_odoo19.dark_mode', 'os'
        )
        result['buz_theme_odoo19_color_variant'] = ICP.get_param(
            'buz_theme_odoo19.color_variant', 'teal'
        )
        return result
