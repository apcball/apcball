from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Show existing Shopee buyer phones in the Thai 0XXXXXXXXX form."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["res.partner"]._shopee_normalise_phones()
