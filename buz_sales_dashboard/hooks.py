from odoo import Command

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


def revoke_automatic_access(env):
    """Take the dashboard back from everybody who does not see everything.

    Up to 17.0.1.5.x every sales user got the narrow level through an implied
    group, and removing that link leaves the memberships in place. Archived
    users and the new-user template are included.
    """
    own = env.ref("buz_sales_dashboard.group_own")
    see_all = env.ref("buz_sales_dashboard.group_all")
    env.ref("sales_team.group_sale_salesman").write(
        {"implied_ids": [Command.unlink(own.id)]})
    users = env["res.users"].with_context(active_test=False)
    revoke = (users.search([("groups_id", "in", own.id)])
              - users.search([("groups_id", "in", see_all.id)]))
    revoke.write({"groups_id": [Command.unlink(own.id)]})


def post_init_hook(env):
    exclude_products(env, EXCLUDED_PRODUCTS)
