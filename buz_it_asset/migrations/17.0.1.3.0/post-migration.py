"""Migrate the former company-specific asset categories to global types."""

from odoo import SUPERUSER_ID, api


ALIASES = {
    'desktop': 'type_desktop_pc', 'laptop': 'type_laptop',
    'notebook': 'type_laptop', 'tablet': 'type_tablet',
    'smartphone': 'type_smartphone', 'router': 'type_router',
    'switch': 'type_switch', 'access point': 'type_access_point',
    'firewall': 'type_hardware_firewall', 'server': 'type_server',
    'nas': 'type_nas_san', 'san': 'type_nas_san', 'hdd': 'type_hdd_ssd',
    'ssd': 'type_hdd_ssd', 'monitor': 'type_monitor',
    'printer': 'type_printer_scanner', 'scanner': 'type_printer_scanner',
    'ups': 'type_ups', 'keyboard': 'type_keyboard_mouse',
    'mouse': 'type_keyboard_mouse',
}


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    category_model = env['buz.it.asset.category']
    type_model = env['buz.it.asset.type']
    legacy_category = category_model.search([
        ('name', '=', 'อื่น ๆ / ข้อมูลเดิม (Other / Legacy)'),
    ], limit=1)
    cr.execute(
        'SELECT DISTINCT legacy_category_id FROM buz_it_asset '
        'WHERE legacy_category_id IS NOT NULL AND type_id IS NULL',
    )
    old_category_ids = [row[0] for row in cr.fetchall()]
    for old_category in category_model.browse(old_category_ids).exists():
        name = (old_category.name or '').lower()
        xmlid = next((value for key, value in ALIASES.items() if key in name), None)
        asset_type = env.ref(
            'buz_it_asset.' + xmlid, raise_if_not_found=False,
        ) if xmlid else False
        if not asset_type:
            if not legacy_category:
                legacy_category = category_model.create({
                    'name': 'อื่น ๆ / ข้อมูลเดิม (Other / Legacy)',
                    'sequence': 90,
                })
            asset_type = type_model.search([
                ('category_id', '=', legacy_category.id),
                ('name', '=', old_category.name),
            ], limit=1) or type_model.create({
                'name': old_category.name,
                'category_id': legacy_category.id,
                'description': 'Migrated from the previous asset category.',
            })
        cr.execute(
            '''UPDATE buz_it_asset
                  SET type_id = %s, category_id = %s
                WHERE legacy_category_id = %s''',
            (asset_type.id, asset_type.category_id.id, old_category.id),
        )
    cr.execute('ALTER TABLE buz_it_asset DROP COLUMN IF EXISTS legacy_category_id')
