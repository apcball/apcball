from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    theme_o19_dark_mode = fields.Selection(
        selection=[
            ('system', 'Follow System'),
            ('os', 'Always Light'),
            ('always', 'Always Dark'),
        ],
        string='Dark Mode',
        default='system',
        config_parameter='buz_theme_odoo19.dark_mode',
    )

    theme_o19_color_variant = fields.Selection(
        selection=[
            ('teal', 'Teal (Default)'),
            ('blue', 'Ocean Blue'),
            ('slate', 'Dark Slate'),
        ],
        string='Color Variant',
        default='teal',
        config_parameter='buz_theme_odoo19.color_variant',
    )
