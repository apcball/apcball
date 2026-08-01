"""Prepare the old category table for the global taxonomy."""


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = 'buz_it_asset_category'
    """)
    if not cr.fetchone():
        return
    cr.execute('ALTER TABLE buz_it_asset_category DROP CONSTRAINT IF EXISTS name_company_uniq')
    cr.execute(
        'ALTER TABLE buz_it_asset_category '
        'ALTER COLUMN company_id DROP NOT NULL',
    )
    cr.execute(
        'ALTER TABLE buz_it_asset ADD COLUMN IF NOT EXISTS legacy_category_id integer',
    )
    cr.execute(
        'UPDATE buz_it_asset SET legacy_category_id = category_id '
        'WHERE legacy_category_id IS NULL',
    )
    cr.execute("""
        CREATE TEMP TABLE it_asset_category_merge (duplicate_id integer, keep_id integer)
        ON COMMIT DROP
    """)
    cr.execute("""
        INSERT INTO it_asset_category_merge (duplicate_id, keep_id)
        SELECT duplicate.id, keep.id
        FROM buz_it_asset_category duplicate
        JOIN buz_it_asset_category keep
          ON keep.name = duplicate.name AND keep.id < duplicate.id
    """)
    cr.execute("""
        UPDATE buz_it_asset
           SET category_id = merge.keep_id,
               legacy_category_id = merge.keep_id
          FROM it_asset_category_merge merge
         WHERE buz_it_asset.category_id = merge.duplicate_id
    """)
    cr.execute("""
        DELETE FROM buz_it_asset_category category
         USING it_asset_category_merge merge
         WHERE category.id = merge.duplicate_id
    """)
