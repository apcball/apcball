from collections import defaultdict
from datetime import date

from odoo import SUPERUSER_ID, api
from odoo.exceptions import UserError


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    type_model = env['buz.it.asset.type'].sudo()
    asset_model = env['buz.it.asset'].sudo()
    companies = env['res.company'].sudo().search([])
    types = type_model.search([])
    missing = types.filtered(lambda record: not record.asset_prefix)
    if missing:
        raise UserError(
            'Cannot migrate IT Asset tags: missing Asset Prefix for %s.'
            % ', '.join(missing.mapped('display_name'))
        )

    for company in companies:
        for asset_type in types:
            company._ensure_it_asset_sequence(asset_type)

    cr.execute(
        """
        SELECT id, asset_tag, company_id, type_id, create_date
          FROM buz_it_asset
         ORDER BY company_id, type_id, create_date, id
        """
    )
    counters = defaultdict(int)
    sequence_counts = defaultdict(int)
    rows = cr.fetchall()
    for asset_id, old_tag, company_id, type_id, create_date in rows:
        if not type_id:
            raise UserError(
                'Cannot migrate IT Asset %s: Hardware Type is missing.' % asset_id
            )
        asset_type = type_model.browse(type_id)
        if not asset_type.exists() or not asset_type.asset_prefix:
            raise UserError(
                'Cannot migrate IT Asset %s: Hardware Type is invalid.' % asset_id
            )
        created = create_date.date() if create_date else date.today()
        year = created.year
        month = created.month
        bucket = (company_id, type_id, year)
        counters[bucket] += 1
        sequence_counts[bucket] = counters[bucket]
        new_tag = '%s/%04d/%02d/%04d' % (
            asset_type.asset_prefix, year, month, counters[bucket],
        )
        cr.execute(
            'UPDATE buz_it_asset SET legacy_asset_tag = %s, asset_tag = %s '
            'WHERE id = %s',
            (old_tag, new_tag, asset_id),
        )

    date_range_model = env['ir.sequence.date_range'].sudo()
    for (company_id, type_id, year), count in sequence_counts.items():
        asset_type = type_model.browse(type_id)
        sequence = env['res.company'].browse(company_id)._ensure_it_asset_sequence(asset_type)
        date_from = date(year, 1, 1)
        date_to = date(year, 12, 31)
        date_range = date_range_model.search([
            ('sequence_id', '=', sequence.id),
            ('date_from', '=', date_from),
            ('date_to', '=', date_to),
        ], limit=1)
        if date_range:
            date_range.write({'number_next': max(date_range.number_next, count + 1)})
        else:
            date_range_model.create({
                'sequence_id': sequence.id,
                'date_from': date_from,
                'date_to': date_to,
                'number_next': count + 1,
            })

    env['ir.sequence'].sudo().search([
        ('code', '=', 'buz.it.asset'),
    ]).write({'active': False})
