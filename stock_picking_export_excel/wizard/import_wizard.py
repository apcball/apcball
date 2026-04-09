from odoo import models, fields

class StockPickingImportWizard(models.TransientModel):
    _name = 'stock.picking.import.wizard'
    _description = 'Stock Picking Import Wizard'

    file_data = fields.Binary('Excel File', required=True)
    filename = fields.Char('Filename')
    
    def action_import(self):
        active_id = self._context.get('active_id')
        if not active_id:
            return
            
        picking = self.env['stock.picking'].browse(active_id)
        
        self.env['import.engine'].import_excel_to_picking(picking, self.file_data)
        
        return {'type': 'ir.actions.act_window_close'}
