from odoo import SUPERUSER_ID, api

from odoo.addons.buz_sales_dashboard.hooks import exclude_products


def migrate(cr, version):
    # only the newly excluded product: switches set by users stay as they are
    exclude_products(api.Environment(cr, SUPERUSER_ID, {}), [14271])
