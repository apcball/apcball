# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    material_requisition_id = fields.Many2one('material.requisition', string='Material Requisition')
    procurement_pool_id = fields.Many2one('procurement.pool', string='Procurement Pool', index=True)
    job_cost_sheet_id = fields.Many2one('job.cost.sheet', string='Job Cost Sheet', index=True)
    project_id = fields.Many2one('project.project', string='Project', index=True)
    job_order_id = fields.Many2one('job.order', string='Job Order', index=True)
    allocation_count = fields.Integer(string='Allocations', compute='_compute_allocation_count')
    has_shortfall = fields.Boolean(
        string='Has Shortfall',
        compute='_compute_has_shortfall',
        help='True if any PO line has received less than ordered (on confirmed POs).',
    )

    def _compute_allocation_count(self):
        for record in self:
            record.allocation_count = self.env['purchase.allocation'].search_count(
                [('po_line_id.order_id', '=', record.id)])

    def action_view_allocations(self):
        """Smart button to view purchase allocations."""
        allocations = self.env['purchase.allocation'].search(
            [('po_line_id.order_id', '=', self.id)])
        return {
            'name': 'Purchase Allocations',
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.allocation',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', allocations.ids)],
        }

    def _compute_has_shortfall(self):
        """Check if any PO line on a confirmed PO has received < ordered."""
        for record in self:
            has_gap = False
            if record.state == 'purchase':
                for line in record.order_line:
                    if line.display_type not in (False, 'product', ''):
                        continue
                    if line.qty_received < line.product_qty:
                        has_gap = True
                        break
            record.has_shortfall = has_gap

    def action_open_shortfall_wizard(self):
        """Open wizard to confirm shortfall closure with reason."""
        self.ensure_one()
        return {
            'name': _('Close Shortfall'),
            'type': 'ir.actions.act_window',
            'res_model': 'po.shortfall.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_po_id': self.id},
        }
    
    @api.model
    def create(self, vals):
        result = super(PurchaseOrder, self).create(vals)
        
        # Debug logging
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Creating purchase order: {result.name}")
        
        # Auto-link to job cost sheet if material requisition is provided
        # Use sudo() to avoid access rights issues when reading linked documents
        if result.material_requisition_id and result.material_requisition_id.sudo().boq_id:
            _logger.info(f"Purchase order has material requisition: {result.material_requisition_id.name}")
            boq = result.material_requisition_id.sudo().boq_id
            _logger.info(f"Material requisition linked to BOQ: {boq.name}")
            
            if boq.job_cost_sheet_id:
                _logger.info(f"BOQ linked to job cost sheet: {boq.job_cost_sheet_id.name}")
                result.job_cost_sheet_id = boq.job_cost_sheet_id.id
                result.project_id = boq.project_id.id
                result.job_order_id = boq.job_order_id.id if boq.job_order_id else False
                
                # Also set analytic account if available
                if result.material_requisition_id.sudo().analytic_account_id:
                     _logger.info(f"Setting analytic account from requisition: {result.material_requisition_id.sudo().analytic_account_id.name}")
                     # Set analytic account on purchase order lines
                     for line in result.order_line:
                        line.analytic_account_id = result.material_requisition_id.sudo().analytic_account_id.id
                elif boq.job_cost_sheet_id.analytic_account_id:
                    _logger.info(f"Setting analytic account on PO lines: {boq.job_cost_sheet_id.analytic_account_id.name}")
                    # Set analytic account on purchase order lines
                    for line in result.order_line:
                        line.analytic_account_id = boq.job_cost_sheet_id.analytic_account_id.id
                
                _logger.info(f"Purchase order successfully linked to job cost sheet: {result.job_cost_sheet_id.name}")
            else:
                _logger.warning(f"BOQ {boq.name} has no job cost sheet linked")
        else:
            _logger.info("Purchase order has no material requisition or BOQ")
        
        return result
    
    def button_confirm(self):
        """Override button_confirm to update job cost sheet actual costs and pool state."""
        result = super(PurchaseOrder, self).button_confirm()

        requisitions = (
            self.mapped('material_requisition_id')
            | self.mapped('order_line.material_requisition_line_id.requisition_id')
        )
        requisitions.sudo()._check_and_mark_done()
        
        # Update job cost sheet actual costs
        if self.job_cost_sheet_id:
            self._update_job_cost_sheet_actual_costs()

        # Update procurement pool state if linked
        if self.procurement_pool_id and self.procurement_pool_id.state == 'rfq_created':
            # Check if all POs for this pool are confirmed
            pool_pos = self.env['purchase.order'].search([
                ('procurement_pool_id', '=', self.procurement_pool_id.id),
                ('state', '=', 'draft'),
            ])
            if not pool_pos:
                self.procurement_pool_id.action_mark_ordered()
            
        return result
    
    def _update_job_cost_sheet_actual_costs(self):
        """Update actual costs in job cost sheet from purchase order lines"""
        if not self.job_cost_sheet_id:
            return
            
        for po_line in self.order_line:
            if po_line.job_cost_line_id:
                # Update the specific job cost line
                po_line.job_cost_line_id.update_actual_costs_from_purchases()
            else:
                # Determine which cost type to search based on product type
                product = po_line.product_id
                cost_lines = False

                if product and product.detailed_type == 'service':
                    # Service product → search Labour tab first, then Overhead
                    cost_lines = self.job_cost_sheet_id.labour_cost_ids.filtered(
                        lambda l: l.product_id == product
                    )
                    if not cost_lines:
                        cost_lines = self.job_cost_sheet_id.overhead_cost_ids.filtered(
                            lambda l: l.product_id == product
                        )
                else:
                    # Storable/consumable product → search Material tab first
                    cost_lines = self.job_cost_sheet_id.material_cost_ids.filtered(
                        lambda l: l.product_id == product
                    )

                # Fallback: search all cost types if not found
                if not cost_lines:
                    all_cost_lines = (
                        self.job_cost_sheet_id.material_cost_ids
                        | self.job_cost_sheet_id.labour_cost_ids
                        | self.job_cost_sheet_id.overhead_cost_ids
                    )
                    cost_lines = all_cost_lines.filtered(
                        lambda l: l.product_id == product
                    )

                if cost_lines:
                    # Link the purchase order line to the first matching cost line
                    po_line.job_cost_line_id = cost_lines[0].id
                    cost_lines[0].update_actual_costs_from_purchases()
    
    def action_view_job_cost_sheet(self):
        """Action to view the related job cost sheet"""
        if self.job_cost_sheet_id:
            return {
                'name': 'Job Cost Sheet',
                'type': 'ir.actions.act_window',
                'res_model': 'job.cost.sheet',
                'res_id': self.job_cost_sheet_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return False


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    material_requisition_line_id = fields.Many2one('material.requisition.line', string='Requisition Line', index=True)
    job_cost_sheet_id = fields.Many2one('job.cost.sheet', string='Job Cost Center', index=True)
    job_cost_line_id = fields.Many2one('job.cost.line', string='Job Cost Line', index=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account', index=True)
    allocation_ids = fields.One2many(
        'purchase.allocation', 'po_line_id', string='Allocations')
    
    @api.model
    def create(self, vals):
        result = super(PurchaseOrderLine, self).create(vals)
        
        # Debug logging
        import logging
        _logger = logging.getLogger(__name__)
        
        # First, ensure job_cost_sheet_id is set if provided
        if vals.get('job_cost_sheet_id') and not result.job_cost_sheet_id:
            result.job_cost_sheet_id = vals.get('job_cost_sheet_id')
        
        # Set job_cost_sheet_id from parent PO if not set
        if not result.job_cost_sheet_id and result.order_id.job_cost_sheet_id:
            result.job_cost_sheet_id = result.order_id.job_cost_sheet_id.id
        
        # Link to job cost line from material requisition line
        if result.material_requisition_line_id:
            req_line = result.material_requisition_line_id.sudo()
            _logger.info(f"Processing PO line with requisition line: {req_line.id}")
            
            # Use job cost line from requisition line if available
            if req_line.job_cost_line_id:
                result.job_cost_line_id = req_line.job_cost_line_id.id
                _logger.info(f"Linked to job cost line from requisition: {req_line.job_cost_line_id.id}")
                
                # Also set job cost sheet and analytic account
                if req_line.job_cost_line_id.cost_sheet_id:
                    result.job_cost_sheet_id = req_line.job_cost_line_id.cost_sheet_id.id
                
                if req_line.analytic_account_id:
                     result.analytic_account_id = req_line.analytic_account_id.id
                elif req_line.requisition_id.analytic_account_id:
                     result.analytic_account_id = req_line.requisition_id.analytic_account_id.id
                elif req_line.job_cost_line_id.analytic_account_id:
                    result.analytic_account_id = req_line.job_cost_line_id.analytic_account_id.id
            
            # Otherwise try to link through BOQ line
            elif req_line.boq_line_id:
                boq_line = req_line.boq_line_id
                _logger.info(f"Found BOQ line: {boq_line.id}")
                # Find matching job cost line
                if boq_line.cost_line_ids:
                    matching_cost_line = boq_line.cost_line_ids.filtered(
                        lambda l: l.product_id == result.product_id
                    )
                    if matching_cost_line:
                        result.job_cost_line_id = matching_cost_line[0].id
                        result.job_cost_sheet_id = matching_cost_line[0].cost_sheet_id.id
                        _logger.info(f"Linked to job cost line from BOQ: {matching_cost_line[0].id}")
                        # Also set analytic account if available
                        if matching_cost_line[0].analytic_account_id:
                            result.analytic_account_id = matching_cost_line[0].analytic_account_id.id
            
            # If no job cost line found from BOQ, try material requisition project
            if not result.job_cost_line_id and req_line.requisition_id.project_id:
                project = req_line.requisition_id.project_id
                _logger.info(f"Trying to find job cost sheet for project: {project.name}")
                # Find job cost sheet for this project
                cost_sheet = self.env['job.cost.sheet'].search([
                    ('project_id', '=', project.id),
                    ('state', '=', 'approved')
                ], limit=1)
                
                if cost_sheet:
                    # Set analytic account
                    if cost_sheet.analytic_account_id:
                        result.analytic_account_id = cost_sheet.analytic_account_id.id
                    
                    # FIX ISSUE #2: Check for duplicate before creating cost line
                    existing_line = self.env['job.cost.line'].sudo().search([
                        ('cost_sheet_id', '=', cost_sheet.id),
                        ('source_po_line_id', '=', result.id)
                    ], limit=1)
                    
                    if not existing_line:
                        # Also check by product
                        existing_line = cost_sheet.material_cost_ids.filtered(
                            lambda l: l.product_id == result.product_id
                        )
                    
                    if existing_line:
                        result.job_cost_line_id = existing_line[0].id
                        _logger.info(f"Using existing job cost line: {existing_line[0].id}")
                    else:
                        # Create new cost line with source tracking
                        cost_line_vals = {
                            'cost_sheet_id': cost_sheet.id,
                            'cost_type': 'material',
                            'product_id': result.product_id.id,
                            'name': result.product_id.name,
                            'planned_qty': result.product_qty,
                            'unit_cost': result.price_unit,
                            'uom_id': result.product_uom.id,
                            'analytic_account_id': cost_sheet.analytic_account_id.id if cost_sheet.analytic_account_id else False,
                            'source_po_line_id': result.id,  # Track source to prevent duplicates
                        }
                        # Use sudo() to allow creation of job cost lines by users without explicit access
                        new_cost_line = self.env['job.cost.line'].sudo().create(cost_line_vals)
                        result.job_cost_line_id = new_cost_line.id
                        _logger.info(f"Created new job cost line: {new_cost_line.id}")
        
        # Auto-link to job cost sheet if job cost sheet is set but job cost line is not
        if result.job_cost_sheet_id and not result.job_cost_line_id and result.product_id:
            cost_sheet = result.job_cost_sheet_id
            _logger.info(f"Auto-linking to job cost sheet: {cost_sheet.name}")
            
            # FIX ISSUE #2: Check for duplicate before creating cost line
            # First check by source PO line ID
            existing_line = self.env['job.cost.line'].sudo().search([
                ('cost_sheet_id', '=', cost_sheet.id),
                ('source_po_line_id', '=', result.id)
            ], limit=1)
            
            if not existing_line:
                # Check by product
                existing_line = cost_sheet.material_cost_ids.filtered(
                    lambda l: l.product_id == result.product_id
                )
            
            if existing_line:
                result.job_cost_line_id = existing_line[0].id
                _logger.info(f"Found existing job cost line: {existing_line[0].id}")
            else:
                # Create new cost line with source tracking
                cost_line_vals = {
                    'cost_sheet_id': cost_sheet.id,
                    'cost_type': 'material',
                    'product_id': result.product_id.id,
                    'name': result.product_id.name,
                    'planned_qty': result.product_qty,
                    'unit_cost': result.price_unit,
                    'uom_id': result.product_uom.id,
                    'analytic_account_id': cost_sheet.analytic_account_id.id if cost_sheet.analytic_account_id else False,
                    'source_po_line_id': result.id,  # Track source to prevent duplicates
                }
                # Use sudo() to allow creation of job cost lines by users without explicit access
                new_cost_line = self.env['job.cost.line'].sudo().create(cost_line_vals)
                result.job_cost_line_id = new_cost_line.id
                _logger.info(f"Created new job cost line: {new_cost_line.id}")
            
            # Set analytic account
            if cost_sheet.analytic_account_id:
                result.analytic_account_id = cost_sheet.analytic_account_id.id
        
        return result
    
    def write(self, vals):
        """Override write to update job cost line when PO line changes"""
        result = super(PurchaseOrderLine, self).write(vals)
        
        # If this line has a job cost line, update the actual costs
        if self.job_cost_line_id and 'qty_received' in vals:
            self.job_cost_line_id.update_actual_costs_from_purchases()
            
        return result
    
    @api.onchange('job_cost_sheet_id')
    def _onchange_job_cost_sheet_id(self):
        """Update domain for job cost line when job cost sheet changes"""
        if self.job_cost_sheet_id:
            # Set analytic account from job cost sheet
            self.analytic_account_id = self.job_cost_sheet_id.analytic_account_id.id
            
            # Return domain for job cost line
            domain = [
                ('cost_sheet_id', '=', self.job_cost_sheet_id.id),
                ('cost_type', 'in', ['material', 'overhead'])
            ]
            return {'domain': {'job_cost_line_id': domain}}
        else:
            self.job_cost_line_id = False
            return {'domain': {'job_cost_line_id': []}}
    
    @api.onchange('job_cost_line_id')
    def _onchange_job_cost_line_id(self):
        """Update product and price when job cost line changes"""
        if self.job_cost_line_id:
            # Set product from job cost line
            if self.job_cost_line_id.product_id:
                self.product_id = self.job_cost_line_id.product_id.id
                self.product_uom = self.job_cost_line_id.uom_id.id or self.job_cost_line_id.product_id.uom_po_id.id
                
            # Set quantity and price
            self.product_qty = self.job_cost_line_id.planned_qty
            self.price_unit = self.job_cost_line_id.unit_cost
            
            # Set analytic account
            if self.job_cost_line_id.analytic_account_id:
                self.analytic_account_id = self.job_cost_line_id.analytic_account_id.id

    @api.onchange('analytic_account_id')
    def _onchange_analytic_account_id(self):
        if self.analytic_account_id:
            # Find related job cost sheet
            cost_sheet = self.env['job.cost.sheet'].search([
                ('analytic_account_id', '=', self.analytic_account_id.id),
                ('state', '=', 'approved')
            ], limit=1)
            
            if cost_sheet:
                # Set job cost sheet
                self.job_cost_sheet_id = cost_sheet.id
                
                # Update domain for job cost line
                domain = [
                    ('cost_sheet_id', '=', cost_sheet.id), 
                    ('cost_type', 'in', ['material', 'overhead'])
                ]
                return {'domain': {'job_cost_line_id': domain}}
        else:
            self.job_cost_sheet_id = False
            self.job_cost_line_id = False
            return {'domain': {'job_cost_line_id': []}}
