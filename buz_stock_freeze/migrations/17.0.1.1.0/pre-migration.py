def migrate(cr, version):
    """warehouse_id (M2o) -> warehouse_ids (M2m): keep existing scope."""
    cr.execute("SELECT 1 FROM information_schema.columns "
               "WHERE table_name='stock_freeze_period' AND column_name='warehouse_id'")
    if not cr.fetchone():
        return
    cr.execute("""
        CREATE TABLE IF NOT EXISTS stock_freeze_period_warehouse_rel (
            period_id integer NOT NULL REFERENCES stock_freeze_period(id) ON DELETE CASCADE,
            warehouse_id integer NOT NULL REFERENCES stock_warehouse(id) ON DELETE CASCADE,
            PRIMARY KEY (period_id, warehouse_id)
        )""")
    cr.execute("""
        INSERT INTO stock_freeze_period_warehouse_rel (period_id, warehouse_id)
        SELECT id, warehouse_id FROM stock_freeze_period
        WHERE warehouse_id IS NOT NULL
        ON CONFLICT DO NOTHING""")
