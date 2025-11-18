import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

class StockValuationLayer(models.Model):
    _inherit = "stock.valuation.layer"

    location_id = fields.Many2one(
        "stock.location",
        string="Location",
        compute="_compute_location_id",
        store=True,
        compute_sudo=True,
        index=True,
        help="Location (internal or transit) from the move. "
             "Remains empty for SVLs without stock_move_id (e.g., some Landed Costs).",
    )
    
    location_complete_name = fields.Char(
        related='location_id.complete_name',
        string='Location Path',
        store=True,
        readonly=True,
        help="Full hierarchical path of the location"
    )
    
    location_type = fields.Selection(
        related='location_id.usage',
        string='Location Type',
        store=True,
        readonly=True,
        help="Type of location (internal, transit, etc.)"
    )
    
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        related='location_id.warehouse_id',
        string='Warehouse',
        store=True,
        readonly=True,
        help="Warehouse of the location"
    )

    @api.depends("stock_move_id")
    def _compute_location_id(self):
        """Compute location_id with memory-efficient batch processing."""
        # Clear all first
        for svl in self:
            svl.location_id = False
        
        # Filter out records without moves
        svls_with_moves = self.filtered(lambda s: s.stock_move_id)
        if not svls_with_moves:
            return
        
        # Batch read to avoid N+1 queries
        move_data = svls_with_moves.mapped('stock_move_id').read([
            'location_id', 'location_dest_id'
        ])
        move_dict = {m['id']: m for m in move_data}
        
        # Collect all location IDs to fetch usage in batch
        location_ids = set()
        for move in move_data:
            if move['location_id']:
                location_ids.add(move['location_id'][0])
            if move['location_dest_id']:
                location_ids.add(move['location_dest_id'][0])
        
        # Batch read location usage
        if location_ids:
            locations = self.env['stock.location'].browse(list(location_ids)).read(['usage'])
            location_usage = {loc['id']: loc['usage'] for loc in locations}
        else:
            location_usage = {}
        
        # Process each SVL with cached data
        for svl in svls_with_moves:
            move = move_dict.get(svl.stock_move_id.id)
            if not move:
                continue
            
            # Check source location (accept internal and transit locations)
            if move['location_id']:
                loc_id = move['location_id'][0]
                if location_usage.get(loc_id) in ('internal', 'transit'):
                    svl.location_id = loc_id
                    continue
            
            # Check destination location (accept internal and transit locations)
            if move['location_dest_id']:
                loc_id = move['location_dest_id'][0]
                if location_usage.get(loc_id) in ('internal', 'transit'):
                    svl.location_id = loc_id

    def action_recompute_location(self):
        """
        Manual recompute action for selected records or all records.
        Can be called from UI or programmatically.
        """
        if not self:
            # If no records selected, recompute all
            self = self.search([('stock_move_id', '!=', False)])
        
        if not self:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Records',
                    'message': 'No stock valuation layers found to recompute.',
                    'type': 'info',
                }
            }
        
        total = len(self)
        _logger.info(f"Starting manual recompute for {total} SVL records")
        
        # Process in batches to avoid memory issues
        batch_size = 1000
        processed = 0
        
        for i in range(0, total, batch_size):
            batch = self[i:i+batch_size]
            batch._compute_location_id()
            processed += len(batch)
            
            # Commit every batch
            self.env.cr.commit()
            _logger.info(f"Recomputed {processed}/{total} records")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Recompute Complete',
                'message': f'Successfully recomputed location for {processed} stock valuation layers.',
                'type': 'success',
                'sticky': False,
            }
        }
