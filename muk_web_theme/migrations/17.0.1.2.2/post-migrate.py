from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    legacy_view = env.ref(
        'muk_web_enterprise_theme.view_res_config_settings_colors_form',
        raise_if_not_found=False,
    )
    if legacy_view:
        legacy_view.write({'active': False})
