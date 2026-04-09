from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools.translate import _

class StockPickingExportWizard(models.TransientModel):
    _name = 'stock.picking.export.wizard'
    _description = 'Stock Picking Export Wizard'

    date_from = fields.Datetime("Date From")
    date_to = fields.Datetime("Date To")
    picking_type_id = fields.Many2one('stock.picking.type', string="Operation Type")
    picking_ids = fields.Many2many('stock.picking', string="Pickings")
    
    state = fields.Selection([
        ('choose', 'Choose'),
        ('download', 'Download')
    ], default='choose')
    
    file_data = fields.Binary('File', readonly=True)
    filename = fields.Char('Filename', readonly=True)

    def action_export(self):
        domain = []
        if self.date_from:
            domain.append(('scheduled_date', '>=', self.date_from))
        if self.date_to:
            domain.append(('scheduled_date', '<=', self.date_to))
        if self.picking_type_id:
            domain.append(('picking_type_id', '=', self.picking_type_id.id))
            
        if self.picking_ids:
            pickings = self.picking_ids
        else:
            pickings = self.env['stock.picking'].search(domain)
            
        if not pickings:
            raise UserError(_("No stock pickings found matching the given criteria."))
            
        file_data, filename = self.env['export.engine'].generate_excel(pickings.ids)
        
        self.write({
            'state': 'download',
            'file_data': file_data,
            'filename': filename,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
