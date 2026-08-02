import re


PREFIX_BY_XMLID = {
    'type_desktop_pc': 'ITPC',
    'type_laptop': 'ITNB',
    'type_tablet': 'ITTB',
    'type_smartphone': 'ITSP',
    'type_router': 'ITRT',
    'type_switch': 'ITSW',
    'type_access_point': 'ITAP',
    'type_hardware_firewall': 'ITFW',
    'type_server': 'ITSV',
    'type_nas_san': 'ITNS',
    'type_hdd_ssd': 'ITHD',
    'type_monitor': 'ITMN',
    'type_printer_scanner': 'ITPS',
    'type_ups': 'ITUP',
    'type_keyboard_mouse': 'ITKM',
}


def _candidate(name, used):
    letters = re.sub(r'[^A-Z0-9]', '', (name or '').upper())
    value = ('IT' + (letters[:4] or 'TYPE'))[:16]
    if value not in used:
        return value
    index = 2
    while True:
        suffix = str(index)
        candidate = value[:16 - len(suffix)] + suffix
        if candidate not in used:
            return candidate
        index += 1


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        'ALTER TABLE buz_it_asset_type ADD COLUMN IF NOT EXISTS asset_prefix varchar(16)'
    )
    cr.execute(
        'ALTER TABLE buz_it_asset ADD COLUMN IF NOT EXISTS legacy_asset_tag varchar'
    )

    used = set()
    for xmlid, prefix in PREFIX_BY_XMLID.items():
        cr.execute(
            """
            UPDATE buz_it_asset_type type
               SET asset_prefix = %s
              FROM ir_model_data data
             WHERE data.module = 'buz_it_asset'
               AND data.name = %s
               AND data.model = 'buz.it.asset.type'
               AND data.res_id = type.id
            """,
            (prefix, xmlid),
        )
        used.add(prefix)

    cr.execute(
        'SELECT id, name FROM buz_it_asset_type '
        'WHERE asset_prefix IS NULL OR asset_prefix = \'\' ORDER BY id'
    )
    for type_id, name in cr.fetchall():
        prefix = _candidate(name, used)
        used.add(prefix)
        cr.execute(
            'UPDATE buz_it_asset_type SET asset_prefix = %s WHERE id = %s',
            (prefix, type_id),
        )
