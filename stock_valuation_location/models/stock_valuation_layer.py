"""
Adds the location to stock valuation layer, much in the same way the base code adds
warehouse_id.
"""

from odoo import models, fields, api


class StockValuationLayer(models.Model):
    _inherit = "stock.valuation.layer"

    location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Location",
        compute="_compute_location_id",
        store=True,
        compute_sudo=True,
    )

    def _compute_location_id(self):
        for svl in self:
            if not svl.stock_move_id:
                svl.location_id = False
                continue
                
            if svl.stock_move_id.location_id.usage == "internal":
                svl.location_id = svl.stock_move_id.location_id
            elif svl.stock_move_id.location_dest_id.usage == "internal":
                svl.location_id = svl.stock_move_id.location_dest_id
            else:
                svl.location_id = False

    @api.model
    def recompute_location(self):
        # Process in batches to handle large datasets
        batch_size = 1000
        offset = 0
        
        while True:
            # Search with offset for pagination
            records = self.search([('stock_move_id', '!=', False)], limit=batch_size, offset=offset)
            if not records:
                break
                
            # Process records by move type
            for record in records:
                move = record.stock_move_id
                if not move:
                    continue
                    
                # Determine correct location
                location_id = False
                if move.location_id.usage == "internal":
                    location_id = move.location_id.id
                elif move.location_dest_id.usage == "internal":
                    location_id = move.location_dest_id.id
                    
                # Update record directly if location changed
                if record.location_id.id != location_id:
                    record.write({'location_id': location_id})
            
            # Increment offset for next batch
            offset += batch_size
            
            # Commit transaction for each batch to free memory
            self.env.cr.commit()  # pylint: disable=invalid-commit
            
        return True

        return True

    def action_recompute_stock_valuation_location(self):
        self.recompute_location()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
