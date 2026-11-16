import logging

from odoo import SUPERUSER_ID, api
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)

FILTER_NAME = "Invoices Analysis All"


def _leaf_ids(domain, field, operator):
    for leaf in domain:
        if (isinstance(leaf, (list, tuple)) and len(leaf) == 3
                and leaf[0] == field and leaf[1] == operator):
            return [int(i) for i in leaf[2]]
    return []


def migrate(cr, version):
    """Seed the dashboard scope from the saved Invoices Analysis filter so
    the dashboard starts out matching the report the business already uses."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Team = env["crm.team"].with_context(active_test=False)
    Product = env["product.product"].with_context(active_test=False)

    team_ids, product_ids = [], []
    saved = env["ir.filters"].with_context(active_test=False).search(
        [("name", "=", FILTER_NAME),
         ("model_id", "=", "account.invoice.report")], limit=1)
    if saved:
        domain = safe_eval(saved.domain or "[]")
        team_ids = _leaf_ids(domain, "team_id", "in")
        product_ids = _leaf_ids(domain, "product_id", "not in")

    if team_ids:
        Team.search([("id", "not in", team_ids)]).write(
            {"spe_count_in_sales": False})
        Team.browse(team_ids).exists().write({"spe_count_in_sales": True})
    if product_ids:
        products = Product.browse(product_ids).exists()
    else:
        products = Product.search([("name", "ilike", "เงินมัดจำ")])
    products.product_tmpl_id.write({"spe_exclude_from_sales": True})

    _logger.info(
        "SPE scope seeded (filter %r %s): %d counted teams %s, "
        "%d excluded products %s",
        FILTER_NAME, "found" if saved else "NOT found",
        Team.search_count([("spe_count_in_sales", "=", True)]),
        sorted(team_ids) or "(all)",
        len(products), products.mapped("default_code"),
    )
