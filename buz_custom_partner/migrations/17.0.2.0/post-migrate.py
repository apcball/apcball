# -*- coding: utf-8 -*-
"""17.0.2.0: Convert res.partner partner_group / partner_type (Char)
to Many2one buz.partner.group / buz.partner.type.

- Create master records from distinct existing values (apply_to = 'both')
- Link existing partners to the new master records
- Drop the old varchar columns
"""


def _migrate_column(cr, old_col, table):
    # 1) create master records from distinct non-empty values
    cr.execute(
        f"""
        INSERT INTO {table} (name, sequence, active, apply_to,
                             create_uid, write_uid, create_date, write_date)
        SELECT DISTINCT ON (p.{old_col})
               p.{old_col}, 10, TRUE, 'both',
               1, 1, now() AT TIME ZONE 'utc', now() AT TIME ZONE 'utc'
        FROM res_partner p
        WHERE p.{old_col} IS NOT NULL AND p.{old_col} <> ''
        ON CONFLICT DO NOTHING
        """
    )
    # 2) link partners
    cr.execute(
        f"""
        UPDATE res_partner p
        SET {table.replace('buz_partner_', 'partner_')}_id = m.id
        FROM {table} m
        WHERE p.{old_col} = m.name
        """
    )
    # 3) drop old column
    cr.execute(f"ALTER TABLE res_partner DROP COLUMN IF EXISTS {old_col}")


def migrate(cr, version):
    _migrate_column(cr, 'partner_group', 'buz_partner_group')
    _migrate_column(cr, 'partner_type', 'buz_partner_type')
