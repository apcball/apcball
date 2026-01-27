from odoo import models, fields, api

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    custom_note = fields.Text(string='Custom Note')
    operation_date = fields.Datetime(string='Operation Date', default=fields.Datetime.now)
    supervisor_id = fields.Many2one('res.users', string='Supervisor')

    def get_report_data(self):
        self.ensure_one()
        return {
            'picking': self,
            'company': self.company_id,
            'move_ids': self.move_ids,  # Updated from move_lines to move_ids
            'custom_note': self.custom_note,
            'supervisor': self.supervisor_id.name,
        }