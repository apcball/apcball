# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    job_cost_sheet_id = fields.Many2one('job.cost.sheet', string='Job Cost Sheet', index=True)
    project_id = fields.Many2one('project.project', string='Project', index=True)
    job_order_id = fields.Many2one('job.order', string='Job Order', index=True)
    
    @api.model
    def create(self, vals):
        result = super(AccountMove, self).create(vals)
        
        # Debug logging
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Creating account move: {result.name}")
        
        # Auto-link to job cost sheet if created from purchase order
        if result.invoice_origin and result.move_type in ['in_invoice', 'in_refund']:
            _logger.info(f"Invoice has origin: {result.invoice_origin}")
            
            # Find purchase order(s) from origin
            purchase_orders = self.env['purchase.order'].search([
                ('name', 'in', result.invoice_origin.split(', '))
            ])
            
            if purchase_orders:
                _logger.info(f"Found {len(purchase_orders)} related purchase orders")
                
                # Get job cost sheet from the first PO that has one
                for po in purchase_orders:
                    if po.job_cost_sheet_id:
                        _logger.info(f"Linking invoice to job cost sheet: {po.job_cost_sheet_id.name}")
                        result.job_cost_sheet_id = po.job_cost_sheet_id.id
                        result.project_id = po.project_id.id
                        result.job_order_id = po.job_order_id.id if po.job_order_id else False
                        break
        
        return result

    def action_post(self):
        """Override to trigger actual cost recompute on job cost sheet when vendor bill is posted."""
        result = super(AccountMove, self).action_post()
        
        for move in self:
            if move.move_type not in ('in_invoice', 'in_refund'):
                continue
            
            # Collect all job cost sheets referenced by invoice lines
            cost_sheets = self.env['job.cost.sheet']
            for line in move.invoice_line_ids:
                if line.job_cost_line_id and line.job_cost_line_id.cost_sheet_id:
                    cost_sheets |= line.job_cost_line_id.cost_sheet_id
            
            # Also check from the move's own job_cost_sheet_id
            if move.job_cost_sheet_id:
                cost_sheets |= move.job_cost_sheet_id
            
            # Trigger recompute on all related job cost sheets
            for sheet in cost_sheets:
                sheet._compute_actual_costs()
        
        return result


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    job_cost_line_id = fields.Many2one('job.cost.line', string='Job Cost Line', index=True)
    
    @api.model
    def create(self, vals):
        result = super(AccountMoveLine, self).create(vals)
        
        import logging
        _logger = logging.getLogger(__name__)
        
        # Auto-link to job cost line if created from purchase order line
        if result.purchase_line_id:
            po_line = result.purchase_line_id
            
            if po_line.job_cost_line_id:
                _logger.info(f"Linking invoice line to job cost line from PO: {po_line.job_cost_line_id.id}")
                result.job_cost_line_id = po_line.job_cost_line_id.id
            elif po_line.job_cost_sheet_id or po_line.order_id.job_cost_sheet_id:
                # PO line has job cost sheet but no specific cost line — find matching one
                cost_sheet = po_line.job_cost_sheet_id or po_line.order_id.job_cost_sheet_id
                product = result.product_id
                
                if cost_sheet and product:
                    # Search ALL cost types (material + labour + overhead)
                    all_cost_lines = (
                        cost_sheet.material_cost_ids
                        | cost_sheet.labour_cost_ids
                        | cost_sheet.overhead_cost_ids
                    )
                    matching = all_cost_lines.filtered(lambda l: l.product_id == product)
                    if matching:
                        result.job_cost_line_id = matching[0].id
                        # Also link the PO line for future reference
                        po_line.job_cost_line_id = matching[0].id
                        _logger.info(f"Linked invoice line to job cost line {matching[0].id} via cost sheet search")
        
        # Fallback: link through analytic account if no direct link
        elif result.analytic_distribution and not result.job_cost_line_id:
            analytic_account_id = list(result.analytic_distribution.keys())[0] if result.analytic_distribution else False
            
            if analytic_account_id:
                try:
                    clean_id = str(analytic_account_id).split(',')[0]
                    analytic_account = self.env['account.analytic.account'].browse(int(clean_id))
                    
                    cost_sheet = self.env['job.cost.sheet'].search([
                        ('analytic_account_id', '=', analytic_account.id),
                        ('state', '=', 'approved')
                    ], limit=1)
                    
                    if cost_sheet and result.product_id:
                        existing_cost_line = self.env['job.cost.line'].sudo().search([
                            ('source_invoice_line_id', '=', result.id)
                        ], limit=1)
                        
                        if existing_cost_line:
                            result.job_cost_line_id = existing_cost_line.id
                        else:
                            # Search ALL cost types
                            all_cost_lines = (
                                cost_sheet.material_cost_ids
                                | cost_sheet.labour_cost_ids
                                | cost_sheet.overhead_cost_ids
                            )
                            matching = all_cost_lines.filtered(
                                lambda l: l.product_id == result.product_id
                            )
                            if matching:
                                result.job_cost_line_id = matching[0].id
                                _logger.info(f"Linked invoice line to cost line {matching[0].id} via analytic")
                                
                except Exception as e:
                    _logger.error(f"Error linking invoice line to job cost line: {e}")
        
        return result
    
    @api.onchange('analytic_distribution')
    def _onchange_analytic_distribution(self):
        if self.analytic_distribution:
            # Get the first analytic account from distribution
            analytic_account_id = list(self.analytic_distribution.keys())[0] if self.analytic_distribution else False
            
            if analytic_account_id:
                try:
                    # Handle multi-analytic keys like "1,4"
                    acc_id = int(str(analytic_account_id).split(',')[0])
                    analytic_account = self.env['account.analytic.account'].browse(acc_id)
                    
                    # Find related job cost sheet
                    cost_sheet = self.env['job.cost.sheet'].search([
                        ('analytic_account_id', '=', analytic_account.id),
                        ('state', '=', 'approved')
                    ], limit=1)
                    
                    if cost_sheet:
                        domain = [('cost_sheet_id', '=', cost_sheet.id)]
                        return {'domain': {'job_cost_line_id': domain}}
                except Exception:
                    pass
