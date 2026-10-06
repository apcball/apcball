def backfill_cost_type(env):
    """Fill cost_type_id on existing lines: product type first, then legacy selection."""
    env.cr.execute("""
        UPDATE stock_landed_cost_lines l
           SET cost_type_id = pt.landed_cost_type_id
          FROM product_product pp
          JOIN product_template pt ON pt.id = pp.product_tmpl_id
         WHERE l.cost_type_id IS NULL
           AND pp.id = l.product_id
           AND pt.landed_cost_type_id IS NOT NULL
    """)
    env.cr.execute("""
        UPDATE stock_landed_cost_lines l
           SET cost_type_id = t.id
          FROM buz_landed_cost_type t
         WHERE l.cost_type_id IS NULL
           AND t.code = COALESCE(l.cost_line_type, 'expense')
    """)


def post_init_hook(env):
    backfill_cost_type(env)
