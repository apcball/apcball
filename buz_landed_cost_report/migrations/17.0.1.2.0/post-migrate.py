from odoo import SUPERUSER_ID, api

from odoo.addons.buz_landed_cost_report.hooks import backfill_cost_type


def migrate(cr, version):
    backfill_cost_type(api.Environment(cr, SUPERUSER_ID, {}))
