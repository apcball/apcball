"""Convert the former Software Product selection to master records."""

from odoo import SUPERUSER_ID, api


TYPE_BY_SELECTION = {
    'operating_system': 'software_type_operating_system',
    'office': 'software_type_office',
    'specialized': 'software_type_specialized',
    'other': 'software_type_other',
}


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute(
        'SELECT id, software_type_legacy '
        'FROM buz_it_software_product '
        'WHERE software_type_legacy IS NOT NULL',
    )
    type_ids = {
        value: env.ref(f'buz_it_asset.{xmlid}').id
        for value, xmlid in TYPE_BY_SELECTION.items()
    }
    for product_id, selection_value in cr.fetchall():
        type_id = type_ids.get(selection_value, type_ids['other'])
        cr.execute(
            'UPDATE buz_it_software_product SET software_type = %s WHERE id = %s',
            (type_id, product_id),
        )
    cr.execute(
        'ALTER TABLE buz_it_software_product '
        'ALTER COLUMN software_type SET NOT NULL',
    )
