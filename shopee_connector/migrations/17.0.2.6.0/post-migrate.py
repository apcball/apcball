from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Backfill Trade Channel = Shopee on orders imported before 17.0.2.6.0."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["sale.order"]._shopee_backfill_trade_channel()
