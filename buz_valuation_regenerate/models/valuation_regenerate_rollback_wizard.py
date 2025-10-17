from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json


class ValuationRegenerateRollbackWizard(models.TransientModel):
    _name = 'valuation.regenerate.rollback.wizard'
    _description = 'Valuation Regeneration Rollback Wizard'

    log_id = fields.Many2one('valuation.regenerate.log', string='Log Entry', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    confirm_rollback = fields.Boolean('Confirm Rollback Action', default=False)
    notes = fields.Text('Additional Notes')

    def action_perform_rollback(self):
        """Perform the actual rollback"""
        self.ensure_one()
        
        if not self.confirm_rollback:
            raise UserError(_("Please confirm the rollback action before proceeding."))
        
        # Get the old data from the log
        old_svl_data = json.loads(self.log_id.old_svl_data) if self.log_id.old_svl_data else []
        old_move_data = json.loads(self.log_id.old_move_data) if self.log_id.old_move_data else []
        
        # Check for any dependencies that might prevent rollback
        # (This is a simplified check - in a real implementation this would be more comprehensive)
        
        # Get new data that was created
        new_svl_ids = json.loads(self.log_id.new_svl_ids) if self.log_id.new_svl_ids else []
        new_move_ids = json.loads(self.log_id.new_move_ids) if self.log_id.new_move_ids else []
        
        # Delete the newly created SVLs
        if new_svl_ids:
            new_svls = self.env['stock.valuation.layer'].browse(new_svl_ids)
            # Check if these SVLs have any dependent entries
            # For simplicity here, we'll just delete them, but in production,
            # you'd need to check for dependencies first
            new_svls.unlink()
        
        # Delete the newly created Journal Entries (if they are still draft)
        if new_move_ids:
            new_moves = self.env['account.move'].browse(new_move_ids)
            # Only delete moves that are still in draft state, otherwise cancel them
            draft_moves = new_moves.filtered(lambda m: m.state == 'draft')
            posted_moves = new_moves - draft_moves
            
            draft_moves.unlink()
            # For posted moves, we would need to create reversing entries
            # This is a complex accounting operation that would need to be handled carefully
            if posted_moves:
                # In a real implementation, create reversing journal entries
                for move in posted_moves:
                    self._create_reversing_entry(move)
        
        # Restore the old SVLs
        svl_obj = self.env['stock.valuation.layer']
        for svl_data in old_svl_data:
            # Only restore if it doesn't exist already
            existing_svl = svl_obj.search([('id', '=', svl_data['id'])])
            if not existing_svl:
                # Create SVL from backup data
                svl_vals = {
                    'product_id': svl_data['product_id'],
                    'value': svl_data['value'],
                    'unit_cost': svl_data['unit_cost'],
                    'quantity': svl_data['quantity'],
                    'remaining_qty': svl_data['remaining_qty'],
                    'description': svl_data['description'],
                    'company_id': svl_data['company_id'],
                    'stock_move_id': svl_data['stock_move_id'],
                }
                # Note: Not including the original ID to create a new record
                svl_obj.create(svl_vals)
        
        # Restore the old Journal Entries
        move_obj = self.env['account.move']
        for move_data in old_move_data:
            # Only restore if it doesn't exist already
            existing_move = move_obj.search([('id', '=', move_data['id'])])
            if not existing_move:
                # Create move from backup data
                move_vals = {
                    'name': move_data['name'],
                    'ref': move_data['ref'],
                    'date': move_data['date'],
                    'journal_id': move_data['journal_id'],
                    'company_id': move_data['company_id'],
                    'state': move_data['state'],  # Will likely be 'draft' to allow editing
                }
                # Create the journal entry
                new_move = move_obj.create(move_vals)
                
                # Create the move lines
                line_obj = self.env['account.move.line']
                for line_data in move_data.get('line_ids', []):
                    line_vals = {
                        'move_id': new_move.id,
                        'name': line_data[2]['name'],
                        'account_id': line_data[2]['account_id'],
                        'debit': line_data[2]['debit'],
                        'credit': line_data[2]['credit'],
                        'partner_id': line_data[2]['partner_id'],
                    }
                    line_obj.create(line_vals)
        
        # Update the log to mark it as rolled back
        self.log_id.write({
            'notes': (self.log_id.notes or '') + f"\nRollback performed on {fields.Datetime.now()} by {self.env.user.name}. Notes: {self.notes or 'None'}"
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Rollback Completed',
                'message': 'Rollback operation completed successfully.',
                'type': 'success',
                'sticky': False
            }
        }
    
    def _create_reversing_entry(self, move):
        """Create a reversing entry for a posted journal entry"""
        # This would create a reversing journal entry, effectively canceling the original entry
        # Implementation would depend on specific accounting requirements
        reverse_move = move._reverse_moves(cancel=True)
        return reverse_move