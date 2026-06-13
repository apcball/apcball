def _post_init_hook(env):
    """Map old state values from buz_dispatch_document if upgrading in-place."""
    env.cr.execute("""
        UPDATE buz_dispatch_document
        SET state = CASE
            WHEN state = 'confirmed' THEN 'printed'
            WHEN state = 'done' THEN 'posted'
            ELSE state
        END
        WHERE state IN ('confirmed', 'done')
    """)
