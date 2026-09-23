from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Cancel quotations imported from Shopee orders that are CANCELLED."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["sale.order"].search([
        ("is_shopee_order", "=", True),
        ("shopee_order_status", "=", "CANCELLED"),
        ("state", "in", ("draft", "sent")),
    ])._shopee_cancel_if_cancelled()
