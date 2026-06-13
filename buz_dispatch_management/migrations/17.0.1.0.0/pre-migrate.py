def migrate(cr, version):
    cr.execute("""
        UPDATE buz_dispatch_document
        SET state = CASE
            WHEN state = 'draft' THEN 'draft'
            WHEN state = 'confirmed' THEN 'printed'
            WHEN state = 'done' THEN 'posted'
            ELSE state
        END
        WHERE state IN ('draft', 'confirmed', 'done')
    """)