from odoo import models, fields, api
import json


class ValuationRegenerateLog(models.Model):
    _name = 'valuation.regenerate.log'
    _description = 'Valuation Regeneration Log'
    _order = 'executed_at desc'
    
    name = fields.Char(compute='_compute_name', store=True)
    user_id = fields.Many2one('res.users', string='Executed By', required=True, readonly=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True)
    executed_at = fields.Datetime(string='Executed At', required=True, readonly=True)
    
    # Scope of regeneration
    scope_products = fields.Many2many('product.product', string='Target Products', readonly=True)
    scope_date_from = fields.Date('Date From', readonly=True)
    scope_date_to = fields.Date('Date To', readonly=True)
    scope_location_ids = fields.Many2many('stock.location', string='Target Locations', readonly=True)
    
    # Options used
    rebuild_valuation_layers = fields.Boolean('Rebuilt Valuation Layers', readonly=True)
    rebuild_account_moves = fields.Boolean('Rebuilt Journal Entries', readonly=True)
    include_landed_cost_layers = fields.Boolean('Included Landed Cost Layers', readonly=True)
    recompute_cost_method = fields.Selection([
        ('auto', 'Auto (Follow Product Category)'),
        ('fifo', 'FIFO'),
        ('avco', 'AVCO'),
    ], string='Recompute Cost Method', readonly=True)
    dry_run = fields.Boolean('Was Dry Run', readonly=True)
    post_new_moves = fields.Boolean('Posted New Moves', readonly=True)
    notes = fields.Text('Notes', readonly=True)
    
    # Backup data (JSON fields)
    old_svl_data = fields.Text('Old SVL Data (JSON)', readonly=True)
    old_move_data = fields.Text('Old Move Data (JSON)', readonly=True)
    
    # New data created (IDs)
    new_svl_ids = fields.Text('New SVL IDs (JSON)', readonly=True)
    new_move_ids = fields.Text('New Move IDs (JSON)', readonly=True)
    
    # Attachments (CSV reports, etc.)
    attachment_ids = fields.One2many('ir.attachment', 'res_id', 
        domain=lambda self: [('res_model', '=', self._name)], string='Attachments')
    
    @api.depends('executed_at', 'user_id', 'company_id')
    def _compute_name(self):
        for record in self:
            if record.executed_at and record.user_id:
                record.name = f"Valuation Regen: {record.user_id.name} - {record.executed_at.strftime('%Y-%m-%d %H:%M')}"
            else:
                record.name = "Valuation Regeneration Log"
    
    def action_view_impacted_moves(self):
        """Action to view the impacted stock moves"""
        self.ensure_one()
        
        # Get the impacted stock moves based on the SVLs
        old_svl_data = json.loads(self.old_svl_data) if self.old_svl_data else []
        move_ids = [svl.get('stock_move_id') for svl in old_svl_data if svl.get('stock_move_id')]
        
        if move_ids:
            return {
                'name': 'Impacted Stock Moves',
                'view_mode': 'tree,form',
                'res_model': 'stock.move',
                'type': 'ir.actions.act_window',
                'domain': [('id', 'in', move_ids)],
            }
        else:
            return {
                'name': 'Impacted Stock Moves',
                'view_mode': 'tree,form',
                'res_model': 'stock.move',
                'type': 'ir.actions.act_window',
                'domain': [('id', '=', False)],  # Empty domain
                'help': 'No impacted stock moves found for this regeneration.',
            }
    
    def action_export_csv_report(self):
        """Export a CSV report showing differences"""
        self.ensure_one()
        
        # Find the attached CSV report
        csv_attachments = self.env['ir.attachment'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('name', 'like', '%.csv')
        ], limit=1)
        
        if csv_attachments:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{csv_attachments.id}/{csv_attachments.name}?download=true',
                'target': 'new',
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Report Found',
                    'message': 'No CSV report is attached to this log entry.',
                    'type': 'warning',
                    'sticky': False
                }
            }
    
    def action_rollback(self):
        """Attempt to rollback the regeneration (if possible)"""
        self.ensure_one()
        
        # Check if this was a dry run - no rollback needed
        if self.dry_run:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Dry Run',
                    'message': 'This was a dry run, no data was modified, so no rollback is necessary.',
                    'type': 'info',
                    'sticky': False
                }
            }
            
        # Validate permissions
        if not self.user_has_groups('stock.group_stock_manager,account.group_account_manager'):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Access Denied',
                    'message': 'You need Inventory or Accounting Manager permissions to perform rollback.',
                    'type': 'error',
                    'sticky': True
                }
            }
        
        # Validate that we're not in a locked period
        if self.company_id.fiscalyear_lock_date and self.scope_date_from and self.scope_date_from <= self.company_id.fiscalyear_lock_date:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Locked Period',
                    'message': f'Cannot rollback entries in a locked period. Lock date: {self.company_id.fiscalyear_lock_date}',
                    'type': 'error',
                    'sticky': True
                }
            }
        
        # Confirm rollback action
        return {
            'name': 'Confirm Rollback',
            'type': 'ir.actions.act_window',
            'res_model': 'valuation.regenerate.rollback.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_log_id': self.id, 'default_company_id': self.company_id.id}
        }