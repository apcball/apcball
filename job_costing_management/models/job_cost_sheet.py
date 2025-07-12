# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class JobCostSheet(models.Model):
    _name = 'job.cost.sheet'
    _description = 'Job Cost Sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name desc'

    name = fields.Char(string='Job Cost Sheet', required=True, copy=False, readonly=True,
                      default=lambda self: _('New'))
    sequence = fields.Integer(string='Sequence', default=10)
    project_id = fields.Many2one('project.project', string='Project/Contract', required=True)
    job_order_id = fields.Many2one('job.order', string='Job Order')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    
    # State management
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
    # Dates
    date_start = fields.Date(string='Start Date', default=fields.Date.today)
    date_end = fields.Date(string='End Date')
    
    # Cost lines
    material_cost_ids = fields.One2many('job.cost.line', 'cost_sheet_id', 
                                       domain=[('cost_type', '=', 'material')],
                                       string='Material Costs')
    labour_cost_ids = fields.One2many('job.cost.line', 'cost_sheet_id', 
                                     domain=[('cost_type', '=', 'labour')],
                                     string='Labour Costs')
    overhead_cost_ids = fields.One2many('job.cost.line', 'cost_sheet_id', 
                                       domain=[('cost_type', '=', 'overhead')],
                                       string='Overhead Costs')
    
    # Totals
    total_material_cost = fields.Float(string='Total Material Cost', compute='_compute_totals', store=True)
    total_labour_cost = fields.Float(string='Total Labour Cost', compute='_compute_totals', store=True)
    total_overhead_cost = fields.Float(string='Total Overhead Cost', compute='_compute_totals', store=True)
    total_cost = fields.Float(string='Total Cost', compute='_compute_totals', store=True)
    
    # Actual costs
    actual_material_cost = fields.Float(string='Actual Material Cost', compute='_compute_actual_costs', store=True)
    actual_labour_cost = fields.Float(string='Actual Labour Cost', compute='_compute_actual_costs', store=True)
    actual_overhead_cost = fields.Float(string='Actual Overhead Cost', compute='_compute_actual_costs', store=True)
    actual_total_cost = fields.Float(string='Actual Total Cost', compute='_compute_actual_costs', store=True)
    
    # Variance
    material_variance = fields.Float(string='Material Variance', compute='_compute_variance', store=True)
    labour_variance = fields.Float(string='Labour Variance', compute='_compute_variance', store=True)
    overhead_variance = fields.Float(string='Overhead Variance', compute='_compute_variance', store=True)
    total_variance = fields.Float(string='Total Variance', compute='_compute_variance', store=True)
    
    # Smart buttons
    purchase_order_count = fields.Integer(string='Purchase Orders', compute='_compute_purchase_order_count')
    timesheet_count = fields.Integer(string='Timesheets', compute='_compute_timesheet_count')
    invoice_count = fields.Integer(string='Invoices', compute='_compute_invoice_count')
    
    # Other fields
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', string='Currency')

    @api.model
    def create(self, vals):
        # Set default currency if not provided
        if not vals.get('currency_id'):
            # Try to get THB currency first, fallback to company currency
            thb_currency = self.env['res.currency'].search([('name', '=', 'THB')], limit=1)
            if thb_currency:
                vals['currency_id'] = thb_currency.id
            else:
                vals['currency_id'] = self.env.company.currency_id.id
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('job.cost.sheet') or _('New')
        result = super(JobCostSheet, self).create(vals)
        return result
    
    @api.depends('material_cost_ids.total_cost', 'labour_cost_ids.total_cost', 'overhead_cost_ids.total_cost')
    def _compute_totals(self):
        for record in self:
            record.total_material_cost = sum(record.material_cost_ids.mapped('total_cost'))
            record.total_labour_cost = sum(record.labour_cost_ids.mapped('total_cost'))
            record.total_overhead_cost = sum(record.overhead_cost_ids.mapped('total_cost'))
            record.total_cost = record.total_material_cost + record.total_labour_cost + record.total_overhead_cost
    
    @api.depends('material_cost_ids.actual_cost', 'labour_cost_ids.actual_cost', 'overhead_cost_ids.actual_cost')
    def _compute_actual_costs(self):
        for record in self:
            record.actual_material_cost = sum(record.material_cost_ids.mapped('actual_cost'))
            record.actual_labour_cost = sum(record.labour_cost_ids.mapped('actual_cost'))
            record.actual_overhead_cost = sum(record.overhead_cost_ids.mapped('actual_cost'))
            record.actual_total_cost = record.actual_material_cost + record.actual_labour_cost + record.actual_overhead_cost
    
    @api.depends('total_material_cost', 'actual_material_cost', 'total_labour_cost', 'actual_labour_cost',
                 'total_overhead_cost', 'actual_overhead_cost', 'total_cost', 'actual_total_cost')
    def _compute_variance(self):
        for record in self:
            record.material_variance = record.actual_material_cost - record.total_material_cost
            record.labour_variance = record.actual_labour_cost - record.total_labour_cost
            record.overhead_variance = record.actual_overhead_cost - record.total_overhead_cost
            record.total_variance = record.actual_total_cost - record.total_cost
    
    def _compute_purchase_order_count(self):
        for record in self:
            # Get purchase orders linked through job cost lines
            all_cost_line_ids = record.material_cost_ids.ids + record.overhead_cost_ids.ids
            if all_cost_line_ids:
                po_line_ids = self.env['purchase.order.line'].search([
                    ('job_cost_line_id', 'in', all_cost_line_ids),
                    ('job_cost_line_id', '!=', False)  # Filter out empty job_cost_line_id
                ])
                po_ids_via_lines = set(po_line_ids.mapped('order_id.id'))
            else:
                po_ids_via_lines = set()
            
            # Get purchase orders linked directly to this job cost sheet
            po_ids_direct = set(self.env['purchase.order'].search([
                ('job_cost_sheet_id', '=', record.id)
            ]).ids)
            
            # Combine both sets and get unique count
            all_po_ids = po_ids_via_lines.union(po_ids_direct)
            record.purchase_order_count = len(all_po_ids)
    
    def _compute_timesheet_count(self):
        for record in self:
            record.timesheet_count = self.env['account.analytic.line'].search_count([
                ('job_cost_line_id', 'in', record.labour_cost_ids.ids)
            ])
    
    def _compute_invoice_count(self):
        for record in self:
            # Get invoice lines linked to job cost lines
            all_cost_line_ids = record.material_cost_ids.ids + record.labour_cost_ids.ids + record.overhead_cost_ids.ids
            if all_cost_line_ids:
                invoice_line_ids = self.env['account.move.line'].search([
                    ('job_cost_line_id', 'in', all_cost_line_ids),
                    ('job_cost_line_id', '!=', False)  # Filter out empty job_cost_line_id
                ])
                # Get unique invoice IDs using set instead of list
                invoice_ids = set(invoice_line_ids.mapped('move_id.id'))
                # Filter out None values and count
                invoice_ids = {inv_id for inv_id in invoice_ids if inv_id}
                record.invoice_count = len(invoice_ids)
            else:
                record.invoice_count = 0
    
    def action_approve(self):
        self.write({'state': 'approved'})
        
    def action_done(self):
        self.write({'state': 'done'})
        
    def action_cancel(self):
        self.write({'state': 'cancelled'})
        
    def action_draft(self):
        self.write({'state': 'draft'})
        
    def action_view_purchase_orders(self):
        # Get purchase orders linked through job cost lines
        all_cost_line_ids = self.material_cost_ids.ids + self.overhead_cost_ids.ids
        if all_cost_line_ids:
            po_line_ids = self.env['purchase.order.line'].search([
                ('job_cost_line_id', 'in', all_cost_line_ids),
                ('job_cost_line_id', '!=', False)  # Filter out empty job_cost_line_id
            ])
            po_ids_via_lines = set(po_line_ids.mapped('order_id.id'))
        else:
            po_ids_via_lines = set()
        
        # Get purchase orders linked directly to this job cost sheet
        po_ids_direct = set(self.env['purchase.order'].search([
            ('job_cost_sheet_id', '=', self.id)
        ]).ids)
        
        # Combine both sets of IDs
        all_po_ids = po_ids_via_lines.union(po_ids_direct)
        all_po_ids = list(all_po_ids)  # Convert set to list for domain
        
        # Use our custom purchase order view to avoid approval_state errors
        tree_view = self.env.ref('job_costing_management.view_purchase_order_tree_job_costing', False)
        
        return {
            'name': 'Purchase Orders',
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'tree,form',
            'views': [(tree_view.id if tree_view else False, 'tree'), (False, 'form')],
            'domain': [('id', 'in', all_po_ids)],
            'context': {'res_model': 'purchase.order'},
        }
    
    def action_view_timesheets(self):
        return {
            'name': 'Timesheets',
            'type': 'ir.actions.act_window',
            'res_model': 'account.analytic.line',
            'view_mode': 'tree,form',
            'domain': [('job_cost_line_id', 'in', self.labour_cost_ids.ids)],
        }
    
    def action_view_invoices(self):
        all_cost_line_ids = self.material_cost_ids.ids + self.labour_cost_ids.ids + self.overhead_cost_ids.ids
        if all_cost_line_ids:
            invoice_line_ids = self.env['account.move.line'].search([
                ('job_cost_line_id', 'in', all_cost_line_ids),
                ('job_cost_line_id', '!=', False)  # Filter out empty job_cost_line_id
            ])
            # Get unique invoice IDs using set instead of list
            invoice_ids = set(invoice_line_ids.mapped('move_id.id'))
            # Filter out None values and convert to list
            invoice_ids = list({inv_id for inv_id in invoice_ids if inv_id})
        else:
            invoice_ids = []
        
        return {
            'name': 'Invoices',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', invoice_ids)],
        }
    
    def action_sync_actual_costs(self):
        """Manually sync actual costs from all linked POs and Invoices"""
        for cost_line in self.material_cost_ids + self.labour_cost_ids + self.overhead_cost_ids:
            cost_line.update_actual_costs_from_purchases()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Actual costs have been synchronized with purchase orders and invoices.',
                'type': 'success',
            }
        }
    
    def action_create_rfq(self):
        """Open wizard to create RFQ from job cost sheet"""
        return {
            'name': 'Create RFQ from Job Cost Sheet',
            'type': 'ir.actions.act_window',
            'res_model': 'create.rfq.from.job.cost',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_job_cost_sheet_id': self.id,
            }
        }
    
    def action_view_cost_analysis(self):
        """Open detailed cost analysis view"""
        return {
            'name': 'Cost Analysis',
            'type': 'ir.actions.act_window',
            'res_model': 'job.cost.line',
            'view_mode': 'tree,form',
            'domain': [('cost_sheet_id', '=', self.id)],
            'context': {
                'default_cost_sheet_id': self.id,
                'search_default_group_cost_type': 1,
            },
        }


class JobCostLine(models.Model):
    _name = 'job.cost.line'
    _description = 'Job Cost Line'
    _order = 'sequence, id'

    cost_sheet_id = fields.Many2one('job.cost.sheet', string='Cost Sheet', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    
    # Cost type
    cost_type = fields.Selection([
        ('material', 'Material'),
        ('labour', 'Labour'),
        ('overhead', 'Overhead')
    ], string='Cost Type', required=True)
    
    # Product/Service
    product_id = fields.Many2one('product.product', string='Product/Service')
    name = fields.Char(string='Description', required=True)
    
    # Quantities
    planned_qty = fields.Float(string='Planned Quantity', default=1.0)
    actual_qty = fields.Float(string='Actual Quantity', compute='_compute_actual_qty', store=True)
    
    # Unit costs
    unit_cost = fields.Float(string='Unit Cost')
    actual_unit_cost = fields.Float(string='Actual Unit Cost', compute='_compute_actual_unit_cost', store=True)
    
    # Total costs
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_cost', store=True)
    actual_cost = fields.Float(string='Actual Cost', compute='_compute_actual_cost', store=True)
    
    # Variance
    qty_variance = fields.Float(string='Quantity Variance', compute='_compute_variance', store=True)
    cost_variance = fields.Float(string='Cost Variance', compute='_compute_variance', store=True)
    
    # UOM
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    
    # Analytic
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    
    # Relations
    purchase_order_line_ids = fields.One2many('purchase.order.line', 'job_cost_line_id', string='Purchase Order Lines')
    timesheet_ids = fields.One2many('account.analytic.line', 'job_cost_line_id', string='Timesheets')
    invoice_line_ids = fields.One2many('account.move.line', 'job_cost_line_id', string='Invoice Lines')
    boq_line_id = fields.Many2one('boq.line', string='BOQ Line')
    
    # Currency (inherits from cost sheet)
    currency_id = fields.Many2one('res.currency', related='cost_sheet_id.currency_id', string='Currency', store=True, readonly=True)

    @api.depends('planned_qty', 'unit_cost')
    def _compute_total_cost(self):
        for record in self:
            record.total_cost = record.planned_qty * record.unit_cost
    
    @api.depends('purchase_order_line_ids.product_qty', 'purchase_order_line_ids.qty_received',
                 'timesheet_ids.unit_amount', 'invoice_line_ids.quantity')
    def _compute_actual_qty(self):
        for record in self:
            if record.cost_type == 'material':
                # Use received quantity from confirmed purchase orders
                po_lines = record.purchase_order_line_ids.filtered(lambda l: l.order_id.state in ['purchase', 'done'])
                record.actual_qty = sum(po_lines.mapped('qty_received'))
            elif record.cost_type == 'labour':
                record.actual_qty = sum(record.timesheet_ids.mapped('unit_amount'))
            else:  # overhead
                # Use invoice lines first, fallback to purchase orders
                if record.invoice_line_ids:
                    record.actual_qty = sum(record.invoice_line_ids.filtered(
                        lambda l: l.move_id.state == 'posted').mapped('quantity'))
                else:
                    po_lines = record.purchase_order_line_ids.filtered(lambda l: l.order_id.state in ['purchase', 'done'])
                    record.actual_qty = sum(po_lines.mapped('qty_received'))
    
    @api.depends('purchase_order_line_ids.price_unit', 'purchase_order_line_ids.product_qty', 
                 'timesheet_ids.amount', 'invoice_line_ids.price_unit', 'invoice_line_ids.quantity')
    def _compute_actual_unit_cost(self):
        for record in self:
            total_cost = 0
            total_qty = 0
            
            if record.cost_type == 'material':
                # Use confirmed/received purchase order lines
                for line in record.purchase_order_line_ids.filtered(lambda l: l.order_id.state in ['purchase', 'done']):
                    total_cost += line.price_subtotal
                    total_qty += line.product_qty
            elif record.cost_type == 'labour':
                # Use timesheets
                for line in record.timesheet_ids:
                    total_cost += abs(line.amount)
                    total_qty += line.unit_amount
            else:  # overhead
                # Use invoice lines or purchase order lines
                for line in record.invoice_line_ids.filtered(lambda l: l.move_id.state == 'posted'):
                    total_cost += line.price_subtotal
                    total_qty += line.quantity
                # If no invoices, use purchase orders
                if not total_cost:
                    for line in record.purchase_order_line_ids.filtered(lambda l: l.order_id.state in ['purchase', 'done']):
                        total_cost += line.price_subtotal
                        total_qty += line.product_qty
            
            record.actual_unit_cost = total_cost / total_qty if total_qty else 0
    
    @api.depends('actual_qty', 'actual_unit_cost')
    def _compute_actual_cost(self):
        for record in self:
            record.actual_cost = record.actual_qty * record.actual_unit_cost
    
    @api.depends('actual_qty', 'planned_qty', 'actual_cost', 'total_cost')
    def _compute_variance(self):
        for record in self:
            record.qty_variance = record.actual_qty - record.planned_qty
            record.cost_variance = record.actual_cost - record.total_cost
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.name
            self.unit_cost = self.product_id.standard_price
            self.uom_id = self.product_id.uom_id
    
    def update_actual_costs_from_purchases(self):
        """Method to manually update actual costs from purchase orders"""
        for record in self:
            if record.cost_type == 'material':
                # Get confirmed purchase order lines
                po_lines = record.purchase_order_line_ids.filtered(
                    lambda l: l.order_id.state in ['purchase', 'done']
                )
                if po_lines:
                    total_cost = sum(po_lines.mapped('price_subtotal'))
                    total_qty = sum(po_lines.mapped(lambda l: l.qty_received or l.product_qty))
                    
                    record.actual_qty = total_qty
                    record.actual_unit_cost = total_cost / total_qty if total_qty else 0
                    record.actual_cost = total_cost
    
    def button_update_actual_costs(self):
        """Button action to update actual costs"""
        self.update_actual_costs_from_purchases()
        return True
