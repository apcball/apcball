# Part of buz addons for Mogen Co. See LICENSE file.
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.osv.expression import AND

ALLOCATION_METHODS = [
    ('bom_cost', 'BOM Cost Ratio'),
    ('percentage', 'Percentage'),
    ('quantity', 'Quantity'),
    ('weight', 'Weight'),
    ('manual', 'Manual Amount'),
]


class MrpBom(models.Model):
    """Add the Reverse Manufacturing BOM type.

    A reverse BOM describes a disassembly: the BOM product is the *input*
    (the finished product to take apart) and the BOM lines are the
    components expected to be *recovered*. Operations on the BOM drive the
    work orders of the Reverse Manufacturing Order exactly like a normal
    manufacturing routing.
    """

    _inherit = 'mrp.bom'

    type = fields.Selection(
        selection_add=[('reverse', 'Reverse Manufacturing')],
        ondelete={'reverse': 'cascade'},
    )
    allocation_method = fields.Selection(
        ALLOCATION_METHODS,
        string='Cost Allocation Method',
        default='bom_cost',
        help='Default method used to distribute the input cost (finished '
             'product value + labor + operations + extra cost) across the '
             'recovered components on Reverse Manufacturing Orders.',
    )

    def _bom_find_domain(self, products, picking_type=None, company_id=False,
                         bom_type=False):
        """Never let normal manufacturing flows pick a reverse BOM.

        Core only filters on ``type`` when ``bom_type`` is explicitly
        passed. Without this guard a reverse BOM could be selected by
        normal MOs, kit explosion or replenishment.
        """
        domain = super()._bom_find_domain(
            products, picking_type=picking_type, company_id=company_id,
            bom_type=bom_type)
        if not bom_type:
            domain = AND([domain, [('type', '!=', 'reverse')]])
        return domain

    @api.onchange('type')
    def _onchange_type_reverse(self):
        # Disassembly consumption is flexible by nature: the single input
        # product is always consumed in full, and the consumption warning
        # wizard makes no sense for recovered outputs.
        if self.type == 'reverse':
            self.consumption = 'flexible'

    @api.constrains('type', 'byproduct_ids')
    def _check_reverse_no_byproducts(self):
        for bom in self:
            if bom.type == 'reverse' and bom.byproduct_ids:
                raise ValidationError(_(
                    'A Reverse Manufacturing BOM cannot have by-products: '
                    'the BOM lines already are the recovered outputs.'))


class MrpBomLine(models.Model):
    """Reverse BOM line = one component expected to be recovered."""

    _inherit = 'mrp.bom.line'

    bom_type = fields.Selection(related='bom_id.type')
    recovery_percent = fields.Float(
        string='Recovery %',
        default=100.0,
        digits=(5, 2),
        help='Percentage of the BOM quantity expected to be recovered in '
             'good condition. The shortfall is scrapped automatically '
             'when the scrap policy is "Auto Scrap Shortfall".',
    )
    dest_location_id = fields.Many2one(
        'stock.location',
        string='Destination Location',
        domain="[('usage', '=', 'internal')]",
        check_company=True,
        help='Default internal location where this recovered component is '
             'put away. Falls back to the location of the Reverse '
             'Manufacturing Order when empty.',
    )
    scrap_policy = fields.Selection(
        [('auto', 'Auto Scrap Shortfall'), ('none', 'No Scrap')],
        string='Scrap Policy',
        default='auto',
        help='Auto Scrap Shortfall: the difference between the expected '
             'and the actually recovered quantity is scrapped when the '
             'order is done.',
    )
    allocation_percent = fields.Float(
        string='Allocation %',
        digits=(5, 2),
        help='Cost allocation percentage used when the allocation method '
             'of the order is "Percentage".',
    )

    @api.constrains('recovery_percent')
    def _check_recovery_percent(self):
        for line in self:
            if line.bom_type == 'reverse' and not 0 <= line.recovery_percent <= 100:
                raise ValidationError(_(
                    'Recovery % must be between 0 and 100.'))
