# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ProcurementPool(models.Model):
    _name = 'procurement.pool'
    _description = 'Procurement Consolidation Pool'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Pool Number', required=True, copy=False, readonly=True,
        default=lambda self: _('New'))

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('rfq_created', 'RFQ Created'),
        ('ordered', 'Ordered'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    line_ids = fields.One2many(
        'procurement.pool.line', 'pool_id', string='Pool Lines')

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    company_currency_id = fields.Many2one(
        'res.currency', string='Company Currency',
        related='company_id.currency_id', readonly=True, store=True)

    user_id = fields.Many2one(
        'res.users', string='Procurement Officer',
        default=lambda self: self.env.user, tracking=True)

    notes = fields.Text(string='Notes')

    # Computed summary fields
    total_demand_qty = fields.Float(
        string='Total Demand', compute='_compute_totals', store=True)
    total_ordered_qty = fields.Float(
        string='Total Ordered', compute='_compute_totals', store=True)
    total_received_qty = fields.Float(
        string='Total Received', compute='_compute_totals', store=True)
    total_remaining_qty = fields.Float(
        string='Total Remaining', compute='_compute_totals', store=True)

    # Smart buttons
    po_count = fields.Integer(
        string='Purchase Orders', compute='_compute_po_count')
    mr_count = fields.Integer(
        string='Material Requisitions', compute='_compute_mr_count')

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'procurement.pool') or _('New')
        return super(ProcurementPool, self).create(vals)

    @api.depends(
        'line_ids.total_qty', 'line_ids.ordered_qty', 'line_ids.received_qty')
    def _compute_totals(self):
        for record in self:
            record.total_demand_qty = sum(record.line_ids.mapped('total_qty'))
            record.total_ordered_qty = sum(
                record.line_ids.mapped('ordered_qty'))
            record.total_received_qty = sum(
                record.line_ids.mapped('received_qty'))
            record.total_remaining_qty = sum(
                record.line_ids.mapped('remaining_qty'))

    def _compute_po_count(self):
        for record in self:
            record.po_count = self.env['purchase.order'].search_count(
                [('procurement_pool_id', '=', record.id)])

    def _compute_mr_count(self):
        for record in self:
            mr_ids = record.line_ids.mapped('mr_line_ids.requisition_id').ids
            record.mr_count = len(set(mr_ids))

    # --- Workflow actions ---

    def action_confirm(self):
        for record in self:
            if not record.line_ids:
                raise ValidationError(
                    _('Cannot confirm an empty procurement pool.'))
            # Validate that all lines have a vendor
            lines_no_vendor = record.line_ids.filtered(lambda l: not l.vendor_id)
            if lines_no_vendor:
                raise ValidationError(
                    _('All pool lines must have a Vendor assigned before confirming.\n'
                      'Missing vendor on: %s') % ', '.join(
                        l.product_id.display_name for l in lines_no_vendor))
            record.write({'state': 'confirmed'})

    def action_create_rfq(self):
        """Create RFQ(s) from the procurement pool, grouped by vendor on each line."""
        self.ensure_one()
        if self.state not in ('confirmed', 'rfq_created'):
            raise ValidationError(
                _('Pool must be confirmed before creating RFQs.'))

        # Validate vendors and analytic distribution
        lines_no_vendor = self.line_ids.filtered(lambda l: not l.vendor_id)
        lines_no_analytic = self.line_ids.filtered(lambda l: not l.analytic_distribution)
        errors = []
        if lines_no_vendor:
            errors.append(
                _('Missing Vendor on: %s') % ', '.join(
                    l.product_id.display_name for l in lines_no_vendor))
        if lines_no_analytic:
            errors.append(
                _('Missing Analytic Distribution on: %s') % ', '.join(
                    l.product_id.display_name for l in lines_no_analytic))
        if errors:
            raise ValidationError(
                _('Cannot create RFQ. Please fill in all required fields:\n') +
                '\n'.join(errors))

        # Group pool lines by vendor_id
        vendor_lines = {}
        for line in self.line_ids:
            remaining = line.total_qty - line.ordered_qty
            if remaining <= 0:
                continue
            vendor_lines.setdefault(line.vendor_id, []).append(line)

        if not vendor_lines:
            raise ValidationError(
                _('No remaining demand to create RFQs for.'))

        purchase_orders = []

        for vendor, lines in vendor_lines.items():
            # Collect job cost sheet, project, and department from MR lines
            job_cost_sheet_id = False
            project_id = False
            dept_id = False
            for line in lines:
                if not dept_id and line.department_id:
                    dept_id = line.department_id.id
                for mr_line in line.mr_line_ids:
                    mr = mr_line.requisition_id
                    if not job_cost_sheet_id and mr.job_cost_sheet_id:
                        job_cost_sheet_id = mr.job_cost_sheet_id.id
                    if not project_id and mr.project_id:
                        project_id = mr.project_id.id
                    if not dept_id and mr.department_id:
                        dept_id = mr.department_id.id
                    if job_cost_sheet_id and project_id and dept_id:
                        break
                if job_cost_sheet_id and project_id and dept_id:
                    break

            po_vals = {
                'partner_id': vendor.id,
                'procurement_pool_id': self.id,
                'origin': self.name,
                'order_line': [],
            }
            if dept_id:
                po_vals['department_id'] = dept_id
            if job_cost_sheet_id:
                po_vals['job_cost_sheet_id'] = job_cost_sheet_id
            if project_id:
                po_vals['project_id'] = project_id

            for line in lines:
                remaining = line.total_qty - line.ordered_qty
                if remaining <= 0:
                    continue

                # Find job_cost_line_id from MR lines
                job_cost_line_id = False
                mr_line_id = False
                analytic_account_id = False
                for mr_line in line.mr_line_ids:
                    if mr_line.job_cost_line_id:
                        job_cost_line_id = mr_line.job_cost_line_id.id
                    if not mr_line_id:
                        mr_line_id = mr_line.id
                    if not analytic_account_id and mr_line.analytic_account_id:
                        analytic_account_id = mr_line.analytic_account_id.id
                    elif not analytic_account_id and mr_line.requisition_id.analytic_account_id:
                        analytic_account_id = mr_line.requisition_id.analytic_account_id.id

                po_line_vals = {
                    'product_id': line.product_id.id,
                    'name': line.product_id.display_name,
                    'product_qty': remaining,
                    'product_uom': line.uom_id.id,
                    'price_unit': line.price_unit or line.product_id.standard_price,
                }
                if job_cost_line_id:
                    po_line_vals['job_cost_line_id'] = job_cost_line_id
                if job_cost_sheet_id:
                    po_line_vals['job_cost_sheet_id'] = job_cost_sheet_id
                if mr_line_id:
                    po_line_vals['material_requisition_line_id'] = mr_line_id
                # Use analytic_distribution from pool line (user-specified) first, fallback to MR
                if line.analytic_distribution:
                    po_line_vals['analytic_distribution'] = line.analytic_distribution
                elif analytic_account_id:
                    po_line_vals['analytic_account_id'] = analytic_account_id

                if line.department_id:
                    po_line_vals['department_id'] = line.department_id.id

                po_vals['order_line'].append((0, 0, po_line_vals))

            if po_vals['order_line']:
                po = self.env['purchase.order'].create(po_vals)
                purchase_orders.append(po.id)

                # Create allocations linking PO lines → MR lines
                self._create_allocations_for_po(po, lines)

        if purchase_orders:
            self.write({'state': 'rfq_created'})
            self.message_post(
                body=_('Created %d RFQ(s) from procurement pool, '
                       'split by vendor.') % len(purchase_orders))

            return {
                'name': _('Purchase Orders'),
                'type': 'ir.actions.act_window',
                'res_model': 'purchase.order',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', purchase_orders)],
            }

        raise ValidationError(
            _('Could not create any RFQs. No remaining demand found.'))

    def _create_allocations_for_po(self, po, pool_lines):
        """Create purchase.allocation records linking PO lines to MR lines."""
        Allocation = self.env['purchase.allocation']

        for po_line in po.order_line:
            # Find matching pool line
            matching_pool_lines = [
                pl for pl in pool_lines
                if pl.product_id == po_line.product_id
            ]

            for pool_line in matching_pool_lines:
                # Distribute PO qty across MR lines proportionally
                for mr_line in pool_line.mr_line_ids:
                    if mr_line.requisition_id.state in ('cancelled', 'rejected'):
                        continue

                    alloc_qty = mr_line.quantity
                    Allocation.create({
                        'po_line_id': po_line.id,
                        'mr_line_id': mr_line.id,
                        'pool_line_id': pool_line.id,
                        'qty': alloc_qty,
                        'project_id': mr_line.requisition_id.project_id.id,
                        'analytic_account_id': (
                            mr_line.requisition_id.analytic_account_id.id
                            if mr_line.requisition_id.analytic_account_id
                            else False),
                        'job_cost_sheet_id': (
                            mr_line.requisition_id.job_cost_sheet_id.id
                            if mr_line.requisition_id.job_cost_sheet_id
                            else False),
                    })

                    # Also link PO line back to MR line's job cost line
                    if not po_line.job_cost_line_id and mr_line.job_cost_line_id:
                        po_line.write({
                            'job_cost_line_id': mr_line.job_cost_line_id.id,
                        })

    def action_mark_ordered(self):
        """Called when linked POs are confirmed."""
        self.write({'state': 'ordered'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        for record in self:
            # Check if any linked POs are confirmed
            pos = self.env['purchase.order'].search([
                ('procurement_pool_id', '=', record.id),
                ('state', 'not in', ['draft', 'cancel']),
            ])
            if pos:
                raise ValidationError(
                    _('Cannot cancel pool with confirmed Purchase Orders:\n%s')
                    % '\n'.join('- %s' % po.name for po in pos))

            # Cancel draft POs
            draft_pos = self.env['purchase.order'].search([
                ('procurement_pool_id', '=', record.id),
                ('state', '=', 'draft'),
            ])
            draft_pos.button_cancel()

            record.write({'state': 'cancelled'})

    def action_reset_to_draft(self):
        self.filtered(
            lambda r: r.state in ('cancelled',)).write({'state': 'draft'})

    # --- Smart button actions ---

    def action_view_purchase_orders(self):
        pos = self.env['purchase.order'].search(
            [('procurement_pool_id', '=', self.id)])
        return {
            'name': _('Purchase Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', pos.ids)],
        }

    def action_view_material_requisitions(self):
        mr_ids = self.line_ids.mapped('mr_line_ids.requisition_id').ids
        return {
            'name': _('Material Requisitions'),
            'type': 'ir.actions.act_window',
            'res_model': 'material.requisition',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', list(set(mr_ids)))],
        }


class ProcurementPoolLine(models.Model):
    _name = 'procurement.pool.line'
    _inherit = ['analytic.mixin']
    _description = 'Procurement Pool Line'
    _order = 'vendor_id, product_id'

    pool_id = fields.Many2one(
        'procurement.pool', string='Procurement Pool',
        required=True, ondelete='cascade')

    product_id = fields.Many2one(
        'product.product', string='Product', required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    description = fields.Char(string='Description')
    vendor_id = fields.Many2one(
        'res.partner', string='Vendor',
        domain="[('is_company', '=', True), ('supplier_rank', '>', 0)]")
    department_id = fields.Many2one(
        'hr.department', string='Department')
    analytic_distribution = fields.Json(string='Analytic Distribution')
    price_unit = fields.Float(string='Unit Price', digits='Product Price')

    # Linked MR lines
    mr_line_ids = fields.Many2many(
        'material.requisition.line',
        'procurement_pool_mr_line_rel',
        'pool_line_id', 'mr_line_id',
        string='MR Lines')

    # Quantities
    total_qty = fields.Float(
        string='Total Demand', compute='_compute_quantities', store=True)
    ordered_qty = fields.Float(
        string='Ordered Qty', compute='_compute_quantities', store=True)
    received_qty = fields.Float(
        string='Received Qty', compute='_compute_quantities', store=True)
    remaining_qty = fields.Float(
        string='Remaining Qty', compute='_compute_quantities', store=True)

    # Related MR info display
    mr_count = fields.Integer(
        string='MR Count', compute='_compute_mr_count')
    mr_references = fields.Char(
        string='MR References', compute='_compute_mr_references')

    company_id = fields.Many2one(
        'res.company', related='pool_id.company_id',
        string='Company', store=True)

    @api.depends('mr_line_ids', 'mr_line_ids.quantity')
    def _compute_quantities(self):
        Allocation = self.env['purchase.allocation']
        for record in self:
            record.total_qty = sum(record.mr_line_ids.mapped('quantity'))

            # Calculate ordered qty from allocations
            allocations = Allocation.search([
                ('pool_line_id', '=', record.id),
            ])
            record.ordered_qty = sum(allocations.mapped('qty'))
            record.received_qty = sum(allocations.mapped('qty_received'))
            record.remaining_qty = record.total_qty - record.received_qty

    def _compute_mr_count(self):
        for record in self:
            record.mr_count = len(
                record.mr_line_ids.mapped('requisition_id'))

    def _compute_mr_references(self):
        for record in self:
            mr_names = record.mr_line_ids.mapped('requisition_id.name')
            record.mr_references = ', '.join(set(mr_names)) if mr_names else ''

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id
            self.description = self.product_id.display_name
            # Auto-set preferred vendor
            if not self.vendor_id and self.product_id.seller_ids:
                self.vendor_id = self.product_id.seller_ids[0].partner_id
            # Auto-set price from MR lines or product
            if not self.price_unit:
                if self.mr_line_ids:
                    for mr_line in self.mr_line_ids:
                        if mr_line.estimated_cost:
                            self.price_unit = mr_line.estimated_cost
                            break
                if not self.price_unit:
                    self.price_unit = self.product_id.standard_price
            # Auto-set analytic from MR lines
            if not self.analytic_distribution and self.mr_line_ids:
                for mr_line in self.mr_line_ids:
                    if mr_line.analytic_distribution:
                        self.analytic_distribution = mr_line.analytic_distribution
                        break
