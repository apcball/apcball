from odoo import SUPERUSER_ID, api

from odoo.addons.buz_sales_dashboard.hooks import revoke_automatic_access


def migrate(cr, version):
    # once: access granted per user from now on stays as it is
    revoke_automatic_access(api.Environment(cr, SUPERUSER_ID, {}))
