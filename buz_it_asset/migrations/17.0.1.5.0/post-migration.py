"""Normalize the specification profile of the built-in hardware types."""

from odoo import SUPERUSER_ID, api


PROFILE_BY_XMLID = {
    'type_desktop_pc': 'desktop',
    'type_laptop': 'laptop',
    'type_tablet': 'mobile',
    'type_smartphone': 'mobile',
    'type_router': 'network',
    'type_switch': 'network',
    'type_access_point': 'network',
    'type_hardware_firewall': 'network',
    'type_server': 'server',
    'type_nas_san': 'storage',
    'type_hdd_ssd': 'storage',
    'type_monitor': 'monitor',
    'type_printer_scanner': 'printer',
    'type_ups': 'ups',
    'type_keyboard_mouse': 'input',
}


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    asset_type_model = env['buz.it.asset.type'].sudo()
    for xmlid, profile in PROFILE_BY_XMLID.items():
        asset_type = env.ref(
            f'buz_it_asset.{xmlid}', raise_if_not_found=False,
        )
        if asset_type and asset_type_model.browse(asset_type.id).exists():
            asset_type.write({'spec_profile': profile})
