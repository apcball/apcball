# Part of buz addons for Mogen Co. See LICENSE file.
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    type = fields.Selection(
        selection_add=[('unbuild', 'Unbuild Only')],
        ondelete={'unbuild': 'set default'},
    )
    unbuild_cost_share_total = fields.Float(
        string='Total Cost Share (%)',
        compute='_compute_unbuild_cost_share_total',
        digits=(5, 2),
        help='Sum of the Cost Share (%) of all BOM lines. Must equal 100 '
             'when the BOM Type is "Unbuild Only".',
    )

    @api.depends('type', 'bom_line_ids.cost_share')
    def _compute_unbuild_cost_share_total(self):
        for bom in self:
            if bom.type == 'unbuild':
                bom.unbuild_cost_share_total = sum(
                    bom.bom_line_ids.mapped('cost_share'))
            else:
                bom.unbuild_cost_share_total = 0.0

    @api.constrains('type', 'bom_line_ids.cost_share')
    def _check_unbuild_cost_share_total(self):
        precision = self.env['decimal.precision'].precision_get(
            'Product Price')
        for bom in self:
            if bom.type != 'unbuild':
                continue
            total = sum(bom.bom_line_ids.mapped('cost_share'))
            if float_compare(total, 100.0,
                              precision_digits=precision) != 0:
                raise ValidationError(_(
                    'BOM %(name)s: Cost Share (%%) of BOM lines must add '
                    'up to 100%% when BOM Type is "Unbuild Only" (currently '
                    '%(total)s%%).',
                    name=bom.display_name, total=total))


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
    cost_share = fields.Float(
        string='Cost Share (%)',
        digits=(5, 2),
        help='Default percentage of the unbuilt product\'s value allocated '
             'to this component. Prefills the Cost Share (%) on the '
             'Unbuild Order component line (still editable there). Only '
             'enforced to sum to 100 across all lines when the BOM Type is '
             '"Unbuild Only".',
    )
