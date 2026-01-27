from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AddToBatchWizard(models.TransientModel):
    _name = 'add.to.batch.wizard'
    _description = 'Wizard to Add Receipt to Batch'

    picking_id = fields.Many2one('stock.picking', string='Receipt', readonly=True)
    batch_option = fields.Selection([
        ('existing', 'Add to Existing Batch'),
        ('new', 'Create New Batch')
    ], string='Batch Option', default='existing', required=True)
    
    existing_batch_id = fields.Many2one(
        'stock.picking.batch', 
        string='Existing Batch',
        domain="[('state', 'in', ['draft', 'in_progress'])]"
    )
    
    new_batch_name = fields.Char(string='New Batch Name')
    
    @api.onchange('batch_option')
    def _onchange_batch_option(self):
        """Clear fields when batch option changes"""
        if self.batch_option == 'new':
            self.existing_batch_id = False
            if not self.new_batch_name:
                self.new_batch_name = _('Batch from %s') % self.picking_id.name
        else:
            self.new_batch_name = False
    
    def add_to_batch(self):
        """Add the receipt to the selected or newly created batch"""
        self.ensure_one()
        
        # Check if picking is already in a batch
        if self.picking_id.batch_id:
            raise UserError(_('This receipt is already part of batch %s.') % self.picking_id.batch_id.name)
        
        # Check if picking is in an appropriate state for batching
        if self.picking_id.state in ['done', 'cancel']:
            raise UserError(_('You cannot add a receipt that is already done or cancelled to a batch.'))
        
        batch = None
        
        if self.batch_option == 'existing':
            # Use existing batch
            if not self.existing_batch_id:
                raise UserError(_('Please select an existing batch.'))
            batch = self.existing_batch_id
        else:
            # Create new batch
            if not self.new_batch_name:
                raise UserError(_('Please provide a name for the new batch.'))
            
            batch_vals = {
                'name': self.new_batch_name,
                'user_id': self.env.user.id,
                'state': 'draft',
            }
            batch = self.env['stock.picking.batch'].create(batch_vals)
        
        # Add the current picking to the batch
        self.picking_id.write({'batch_id': batch.id})
        
        # Return action to open the batch form
        return {
            'name': _('Batch Transfer'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking.batch',
            'view_mode': 'form',
            'res_id': batch.id,
            'target': 'current',
        }