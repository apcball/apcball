from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockPickingBatch(models.Model):
    _inherit = 'stock.picking.batch'
    
    # Computed fields to track related internal transfers created from this batch
    transfer_ids = fields.One2many(
        'stock.picking',
        'source_batch_id',
        string='Internal Transfers',
        help="Internal transfers created from this batch"
    )
    
    transfer_count = fields.Integer(
        string='Transfer Count',
        compute='_compute_transfer_count',
        help="Number of internal transfers created from this batch"
    )

    all_picks_done = fields.Boolean(
        string='All Pickings Done',
        compute='_compute_all_picks_done',
        store=True,
        help="True if all pickings in the batch are in state 'done'"
    )
    
    @api.depends('transfer_ids')
    def _compute_transfer_count(self):
        """Compute the number of internal transfers created from this batch"""
        for batch in self:
            batch.transfer_count = len(batch.transfer_ids)

    @api.depends('picking_ids.state')
    def _compute_all_picks_done(self):
        """Compute whether all related pickings are in 'done' state"""
        for batch in self:
            if not batch.picking_ids:
                batch.all_picks_done = False
            else:
                batch.all_picks_done = all(p.state == 'done' for p in batch.picking_ids)
    
    def action_view_transfers(self):
        """Open the list of internal transfers created from this batch"""
        self.ensure_one()
        return {
            'name': _('Internal Transfers'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'tree,form',
            'domain': [('source_batch_id', '=', self.id)],
            'context': {
                'default_source_batch_id': self.id,
                'search_default_draft': 1,
                'search_default_assigned': 1,
                'search_default_confirmed': 1,
            },
        }

    def action_create_transfer(self):
        """Open wizard to create transfer from batch"""
        self.ensure_one()
        
        # Check if batch has any pickings
        if not self.picking_ids:
            raise UserError(_('The batch does not contain any transfers to create from.'))
        
        # Create wizard context with the batch ID
        wizard_context = {
            'default_batch_id': self.id,
            'default_origin': 'Batch Transfer - %s' % self.name,
        }
        
        # Open the wizard to select destination location
        return {
            'name': _('Create Transfer from Batch'),
            'type': 'ir.actions.act_window',
            'res_model': 'transfer.from.batch.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'context': wizard_context,
        }