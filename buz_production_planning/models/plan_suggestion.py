# pylint: disable=prefer-env-translation  # Odoo 17 has no env._ (that is Odoo 18 API)
from odoo import _, fields, models
from odoo.exceptions import UserError


class PlanSuggestion(models.Model):
    _name = 'buz.plan.suggestion'
    _description = 'Plan Suggestion (Make / Buy)'
    _inherit = ['mail.thread']
    _check_company_auto = True
    _order = 'run_id, level, date_release, product_id'

    run_id = fields.Many2one('buz.plan.run', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(
        related='run_id.company_id', store=True, index=True, readonly=True)
    product_id = fields.Many2one(
        'product.product', required=True, index=True, check_company=True)
    action = fields.Selection([('make', "Make"), ('buy', "Buy")], required=True)
    qty = fields.Float(digits='Product Unit of Measure', required=True)
    uom_id = fields.Many2one('uom.uom', string="Unit", required=True)
    date_need = fields.Date(required=True)
    date_release = fields.Date(required=True)
    is_late = fields.Boolean(readonly=True)
    bom_id = fields.Many2one('mrp.bom', check_company=True)
    picking_type_id = fields.Many2one(
        'stock.picking.type', string="Production Line", check_company=True,
        domain=[('code', '=', 'mrp_operation')])
    vendor_id = fields.Many2one('res.partner', domain=[('supplier_rank', '>', 0)])
    level = fields.Integer(string="BoM Level", readonly=True)
    onhand_qty = fields.Float(digits='Product Unit of Measure', readonly=True)
    incoming_qty = fields.Float(digits='Product Unit of Measure', readonly=True)
    demand_qty = fields.Float(digits='Product Unit of Measure', readonly=True)
    projected_qty = fields.Float(digits='Product Unit of Measure', readonly=True)
    shortage_qty = fields.Float(digits='Product Unit of Measure', readonly=True)
    parent_suggestion_id = fields.Many2one(
        'buz.plan.suggestion', string="Pegged To", ondelete='set null', index=True)
    state = fields.Selection([
        ('proposed', "Proposed"),
        ('approved', "Approved"),
        ('rejected', "Rejected"),
        ('done', "Done"),
    ], default='proposed', required=True, index=True, tracking=True)
    production_id = fields.Many2one('mrp.production', readonly=True, copy=False, check_company=True)
    purchase_line_id = fields.Many2one(
        'purchase.order.line', readonly=True, copy=False, check_company=True)

    _sql_constraints = [
        ('qty_positive', 'check(qty > 0)', "Suggested quantity must be greater than zero."),
    ]

    def _check_actionable(self, states):
        bad = self.filtered(lambda s: s.state not in states)
        if bad:
            raise UserError(_(
                "These suggestions are not in a state that allows this action: %s",
                ", ".join(bad.mapped('product_id.display_name'))))

    def action_approve(self):
        self._check_actionable(('proposed', 'rejected'))
        self.write({'state': 'approved'})

    def action_reject(self):
        self._check_actionable(('proposed', 'approved'))
        self.write({'state': 'rejected'})

    def action_reset(self):
        self._check_actionable(('approved', 'rejected'))
        self.write({'state': 'proposed'})
