def migrate(cr, version):
    """Convert etax_transaction.selected_delivery_id from a dispatch document
    name (varchar) to a buz.dispatch.document id (int4).

    The field used to store the dispatch number string (e.g. 'DP-260610339')
    and is now a Many2one to buz.dispatch.document, so the column must hold
    the matching record id. Orphan names (deleted dispatches) are nulled.
    """
    cr.execute("""
        SELECT data_type
        FROM information_schema.columns
        WHERE table_name = 'etax_transaction'
          AND column_name = 'selected_delivery_id'
    """)
    row = cr.fetchone()
    if not row or row[0] == 'integer':
        return

    cr.execute("""
        UPDATE etax_transaction t
        SET selected_delivery_id = d.id::text
        FROM buz_dispatch_document d
        WHERE d.name = t.selected_delivery_id
    """)
    cr.execute("""
        UPDATE etax_transaction
        SET selected_delivery_id = NULL
        WHERE selected_delivery_id IS NOT NULL
          AND selected_delivery_id !~ '^[0-9]+$'
    """)
    cr.execute("""
        ALTER TABLE etax_transaction
        ALTER COLUMN selected_delivery_id TYPE integer
        USING NULLIF(selected_delivery_id, '')::integer
    """)
