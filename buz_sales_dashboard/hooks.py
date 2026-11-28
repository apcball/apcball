# Products that are not sales: deposits, the card surcharge and the retention
# money returned by customers. The ids are the production ones; the name must
# match too, so another database that reuses an id for a real product is left
# alone.
EXCLUDED_PRODUCTS = {
    14112: "มัดจำ",
    14113: "มัดจำ",
    14658: "ธรรมเนียม",
    14271: "ประกันผลงาน",
}


def exclude_products(env, ids):
    products = env["product.product"].with_context(active_test=False).browse(
        list(ids)).exists()
    products.filtered(
        lambda p: any(
            EXCLUDED_PRODUCTS[p.id] in (name or "")
            for name in (p.with_context(lang="th_TH").name,
                         p.with_context(lang="en_US").name))
    ).exclude_from_sales_dashboard = True


def post_init_hook(env):
    exclude_products(env, EXCLUDED_PRODUCTS)
