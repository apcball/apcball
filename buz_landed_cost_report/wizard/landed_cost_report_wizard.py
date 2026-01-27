from odoo import models, fields, api, _

class LandedCostReportWizard(models.TransientModel):
    _name = 'buz.landed.cost.report.wizard'
    _description = 'Landed Cost Report Wizard'

    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    landed_cost_ids = fields.Many2many('stock.landed.cost', string='Landed Costs')
    product_categ_id = fields.Many2one('product.category', string='Product Category')

    def _get_domain(self):
        domain = []
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        if self.date_to:
            domain.append(('date', '<=', self.date_to))
        if self.landed_cost_ids:
            domain.append(('landed_cost_id', 'in', self.landed_cost_ids.ids))
        if self.product_categ_id:
            domain.append(('product_categ_id', 'child_of', self.product_categ_id.id))
        return domain

    def action_open_pivot(self):
        self.ensure_one()
        domain = self._get_domain()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Landed Cost Report'),
            'res_model': 'buz.landed.cost.report',
            'view_mode': 'pivot,tree,form',
            'domain': domain,
            # 'context': {'search_default_group_by_product': 1}, # Maybe not needed if Tree is default or Pivot is nice.
        }

    def action_export_excel(self):
        self.ensure_one()
        data = {
            'wizard_id': self.id,
            'domain': self._get_domain() # helpful to pass explicit domain just in case
        }
        return self.env.ref('buz_landed_cost_report.action_report_landed_cost_xlsx').report_action(self, data=data)
