# pylint: disable=prefer-env-translation  # Odoo 17 has no env._ (that is Odoo 18 API)
from odoo import _, fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    buz_plan_suggestion_ids = fields.One2many(
        'buz.plan.suggestion', 'production_id', string="Plan Suggestions", readonly=True)
    buz_plan_run_id = fields.Many2one(
        'buz.plan.run', string="Production Plan", compute='_compute_buz_plan_run_id')

    def _compute_buz_plan_run_id(self):
        for mo in self:
            mo.buz_plan_run_id = mo.buz_plan_suggestion_ids[:1].run_id

    def action_open_buz_plan(self):
        self.ensure_one()
        if not self.buz_plan_run_id:
            return False
        return {
            'type': 'ir.actions.act_window', 'name': _("Production Plan"),
            'res_model': 'buz.plan.run', 'res_id': self.buz_plan_run_id.id, 'view_mode': 'form',
        }
