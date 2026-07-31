# Part of buz addons for Mogen Co. See LICENSE file.
from odoo import fields, models


class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'

    default_return_location_id = fields.Many2one(
        'stock.location',
        string='Default Return Location',
        domain="[('usage', '=', 'internal')]",
        check_company=True,
        help='Default destination location for this component when the '
             'finished product is unbuilt. Leave empty to use the unbuild '
             'order destination location.',
    )
