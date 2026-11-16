from odoo import fields, models, tools


class PlanOperationTime(models.Model):
    """Actual vs expected minutes per produced unit, per operation/workcenter.

    Uses done workorders finished since 2026-04-01 (the data cut-off; the
    date is literal because a SQL view cannot read ir.config_parameter).
    """
    _name = 'buz.plan.operation.time'
    _description = 'Operation Time History'
    _auto = False
    _order = 'wo_count desc'

    operation_id = fields.Many2one('mrp.routing.workcenter', readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', readonly=True)
    wo_count = fields.Integer(string="Done Workorders", readonly=True)
    actual_minutes_per_unit = fields.Float(
        string="Actual min/unit", readonly=True, digits=(16, 3))
    expected_minutes_per_unit = fields.Float(
        string="Expected min/unit", readonly=True, digits=(16, 3))
    ratio = fields.Float(string="Actual / Expected", readonly=True, digits=(16, 2))

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT row_number() OVER ()::int AS id,
                       operation_id, workcenter_id, wo_count,
                       actual_minutes_per_unit, expected_minutes_per_unit,
                       CASE WHEN expected_minutes_per_unit > 0
                            THEN actual_minutes_per_unit / expected_minutes_per_unit
                            ELSE 0 END AS ratio
                  FROM (
                    SELECT wo.operation_id, wo.workcenter_id,
                           COUNT(*) AS wo_count,
                           percentile_cont(0.5) WITHIN GROUP (
                               ORDER BY wo.duration / wo.qty_produced) AS actual_minutes_per_unit,
                           percentile_cont(0.5) WITHIN GROUP (
                               ORDER BY wo.duration_expected / NULLIF(mo.product_qty, 0)
                           ) AS expected_minutes_per_unit
                      FROM mrp_workorder wo
                      JOIN mrp_production mo ON mo.id = wo.production_id
                     WHERE wo.state = 'done'
                       AND wo.date_finished >= DATE '2026-04-01'
                       AND wo.duration > 0
                       AND wo.qty_produced > 0
                       AND wo.operation_id IS NOT NULL
                     GROUP BY wo.operation_id, wo.workcenter_id
                  ) t
            )
        """ % self._table)
