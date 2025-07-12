# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    job_cost_sheet_id = fields.Many2one('job.cost.sheet', string='Job Cost Sheet')
    project_id = fields.Many2one('project.project', string='Project')
    job_order_id = fields.Many2one('job.order', string='Job Order')
    
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


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    job_cost_line_id = fields.Many2one('job.cost.line', string='Job Cost Line')
    
    @api.model
    def create(self, vals):
        result = super(AccountMoveLine, self).create(vals)
        
        # Debug logging
        import logging
        _logger = logging.getLogger(__name__)
        
        # Auto-link to job cost line if created from purchase order line
        if result.purchase_line_id and result.purchase_line_id.job_cost_line_id:
            _logger.info(f"Linking invoice line to job cost line: {result.purchase_line_id.job_cost_line_id.id}")
            result.job_cost_line_id = result.purchase_line_id.job_cost_line_id.id
        
        # Fallback: link through analytic account if no direct link
        elif result.analytic_distribution and not result.job_cost_line_id:
            # Get the first analytic account from distribution
            analytic_account_id = list(result.analytic_distribution.keys())[0] if result.analytic_distribution else False
            
            if analytic_account_id:
                try:
                    # Remove any commas and convert to integer
                    clean_id = str(analytic_account_id).replace(',', '')
                    analytic_account = self.env['account.analytic.account'].browse(int(clean_id))
                    
                    # Find related job cost sheet
                    cost_sheet = self.env['job.cost.sheet'].search([
                        ('analytic_account_id', '=', analytic_account.id),
                        ('state', '=', 'approved')
                    ], limit=1)
                    
                    if cost_sheet and result.product_id:
                        # Find matching job cost line
                        matching_cost_line = cost_sheet.material_cost_ids.filtered(
                            lambda l: l.product_id == result.product_id
                        )
                        if matching_cost_line:
                            _logger.info(f"Linking invoice line to job cost line via analytic account: {matching_cost_line[0].id}")
                            result.job_cost_line_id = matching_cost_line[0].id
                except Exception as e:
                    _logger.error(f"Error linking invoice line to job cost line: {e}")
        
        return result
    
    @api.onchange('analytic_distribution')
    def _onchange_analytic_distribution(self):
        if self.analytic_distribution:
            # Get the first analytic account from distribution
            analytic_account_id = list(self.analytic_distribution.keys())[0] if self.analytic_distribution else False
            
            if analytic_account_id:
                analytic_account = self.env['account.analytic.account'].browse(int(analytic_account_id))
                
                # Find related job cost sheet
                cost_sheet = self.env['job.cost.sheet'].search([
                    ('analytic_account_id', '=', analytic_account.id),
                    ('state', '=', 'approved')
                ], limit=1)
                
                if cost_sheet:
                    domain = [('cost_sheet_id', '=', cost_sheet.id)]
                    return {'domain': {'job_cost_line_id': domain}}
