"""Move the single product of each warranty card into a warranty.card.line."""


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        INSERT INTO warranty_card_line (
            card_id, sequence, partner_id, product_id, lot_id, product_description,
            start_date, warranty_duration, warranty_period_unit, end_date,
            create_uid, create_date, write_uid, write_date
        )
        SELECT wc.id, 10, wc.partner_id, wc.product_id, wc.lot_id, wc.product_description,
               wc.start_date, wc.warranty_duration, wc.warranty_period_unit, wc.end_date,
               wc.create_uid, wc.create_date, wc.write_uid, wc.write_date
        FROM warranty_card wc
        WHERE wc.product_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM warranty_card_line wl WHERE wl.card_id = wc.id)
    """)
