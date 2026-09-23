def migrate(cr, version):
    """Customer Reference of Shopee orders = Shopee order number."""
    cr.execute("""
        UPDATE sale_order
           SET client_order_ref = shopee_order_sn
         WHERE is_shopee_order
           AND shopee_order_sn IS NOT NULL
           AND client_order_ref IS DISTINCT FROM shopee_order_sn
    """)
