from odoo import fields, models


class PlanDemandLine(models.Model):
    _name = 'buz.plan.demand.line'
    _description = 'Plan Demand Line'
    _check_company_auto = True
    _order = 'run_id, product_id, bucket_start'

    run_id = fields.Many2one('buz.plan.run', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(
        related='run_id.company_id', store=True, index=True, readonly=True)
    product_id = fields.Many2one(
        'product.product', required=True, index=True, check_company=True)
    bucket_start = fields.Date(required=True, index=True)
    source = fields.Selection([
        ('delivery', "Delivery"),
        ('forecast', "Forecast"),
        ('safety', "Safety Stock"),
        ('dependent', "Dependent"),
    ], required=True)
    qty = fields.Float(digits='Product Unit of Measure')
    qty_manual = fields.Float(
        string="Manual Qty", digits='Product Unit of Measure',
        help="When set, replaces the computed quantity on the next compute.")
    origin_ref = fields.Char(string="Origin")

    _sql_constraints = [
        ('qty_nonneg', 'check(qty >= 0 and qty_manual >= 0)', "Quantities cannot be negative."),
    ]
