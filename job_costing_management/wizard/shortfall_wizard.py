# -*- coding: utf-8 -*-

import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class POShortfallWizardLine(models.TransientModel):
    _name = 'po.shortfall.wizard.line'
    _description = 'PO Shortfall Line'

    wizard_id = fields.Many2one('po.shortfall.wizard', required=True, ondelete='cascade')
    po_line_id = fields.Many2one('purchase.order.line', required=True, ondelete='cascade')
    product_id = fields.Many2one(related='po_line_id.product_id', string='Product')
    product_type = fields.Selection(related='product_id.type')
    product_qty = fields.Float(related='po_line_id.product_qty', string='Ordered')
    qty_received = fields.Float(related='po_line_id.qty_received', string='Current Received')
    new_qty_received = fields.Float(string='Adjust Received', required=True)
    shortfall = fields.Float(string='Shortfall', compute='_compute_shortfall')

    @api.depends('product_qty', 'new_qty_received')
    def _compute_shortfall(self):
        for rec in self:
            rec.shortfall = max(0.0, rec.product_qty - rec.new_qty_received)

    @api.constrains('new_qty_received', 'qty_received', 'product_qty')
    def _check_quantities(self):
        for rec in self:
            if rec.new_qty_received < rec.qty_received:
                raise ValidationError(_('Cannot reduce received quantity for %s (current: %s, adjusted: %s)') % (
                    rec.product_id.display_name, rec.qty_received, rec.new_qty_received))
            if rec.new_qty_received > rec.product_qty:
                raise ValidationError(_('Adjusted received quantity cannot exceed ordered quantity for %s') % rec.product_id.display_name)


class POShortfallWizard(models.TransientModel):
    _name = 'po.shortfall.wizard'
    _description = 'PO Shortfall Closure Wizard'

    po_id = fields.Many2one(
        'purchase.order', string='Purchase Order',
        required=True, readonly=True)
    
    line_ids = fields.One2many('po.shortfall.wizard.line', 'wizard_id', string='Shortfall Details')
    
    action_type = fields.Selection([
        ('create_po', 'Create New PO for Remaining'),
        ('cancel', 'Cancel Remaining (Return Budget)')
    ], string='Action', default='create_po', required=True)

    reason = fields.Text(
        string='Reason', required=True,
        help='Explain why the supplier could not deliver the full quantity.')
    note = fields.Text(string='Additional Notes')

    has_storable_product = fields.Boolean(compute='_compute_has_storable')
    total_shortfall = fields.Float(compute='_compute_total_shortfall', string='Total Shortfall')

    @api.depends('line_ids.product_type')
    def _compute_has_storable(self):
        for rec in self:
            rec.has_storable_product = any(line.product_type == 'product' for line in rec.line_ids)

    @api.depends('line_ids.shortfall')
    def _compute_total_shortfall(self):
        for rec in self:
            rec.total_shortfall = sum(rec.line_ids.mapped('shortfall'))

    @api.model
    def default_get(self, fields_list):
        res = super(POShortfallWizard, self).default_get(fields_list)
        if 'po_id' in res and res['po_id']:
            po = self.env['purchase.order'].browse(res['po_id'])
            lines = []
            for line in po.order_line:
                if line.display_type not in (False, 'product', ''):
                    continue
                if line.qty_received < line.product_qty:
                    lines.append((0, 0, {
                        'po_line_id': line.id,
                        'new_qty_received': line.qty_received,
                    }))
            res['line_ids'] = lines
        return res

    def action_confirm(self):
        """Process adjusted receiving and handle shortfall (Create PO or Cancel Remaining)."""
        self.ensure_one()
        po = self.po_id

        if po.state != 'purchase':
            raise ValidationError(_('Can only close shortfall on confirmed Purchase Orders.'))

        # 1. Adjust Receiving Quantities First
        self._process_receive_adjustments()

        changes = []
        new_po_lines_vals = []
        shortfall_found = False

        for w_line in self.line_ids:
            po_line = w_line.po_line_id
            
            # Use w_line.new_qty_received as the final received quantity
            # Note: _process_receive_adjustments has already adjusted the true qty_received or scheduled a picking if needed.
            new_received = w_line.new_qty_received
            old_qty = po_line.product_qty
            shortfall = w_line.shortfall

            if shortfall > 0:
                shortfall_found = True

            # 2. Close current PO Line
            # We strictly set product_qty = new_received
            if old_qty != new_received:
                old_price = po_line.price_unit
                po_line.write({
                    'product_qty': new_received,
                    'price_unit': old_price,  # Try to force it in the first write
                })
                # Safety check: if standard Odoo recomputes it to 0.0 later because of pricelist MOQ
                if po_line.price_unit != old_price:
                    po_line.write({'price_unit': old_price})

            changes.append(
                _('%s: Ordered %.2f → Final %.2f (shortfall %.2f)') % (
                    po_line.product_id.display_name,
                    old_qty, new_received, shortfall,
                )
            )

            # 3. Handle specific action logic
            if self.action_type == 'cancel':
                # Return budget / MR capacity
                if po_line.material_requisition_line_id:
                    mr_line = po_line.material_requisition_line_id
                    # Ensure we don't reduce below 0. 
                    # Note: We must reduce the MR line quantity to the newly ordered amount to free up budget.
                    # Wait, the MR Line might be linked to OTHER POs as well, but standard Odoo/biz_weekly_budget returns capacity if MR line qty is reduced.
                    # The prompt says: "MR Sync: mr_line.quantity = new_order_qty"
                    new_mr_qty = max(0, mr_line.quantity - shortfall)
                    if new_mr_qty != mr_line.quantity:
                        mr_line.write({'quantity': new_mr_qty})
                        _logger.info('Shortfall cascade (cancel): MR line %s qty → %.2f', mr_line.id, new_mr_qty)

            elif self.action_type == 'create_po' and shortfall > 0:
                # Prepare data to duplicate PO line for the remaining amount
                line_vals = {
                    'product_id': po_line.product_id.id,
                    'name': po_line.name,
                    'product_qty': shortfall,
                    'price_unit': po_line.price_unit,
                    'taxes_id': [(6, 0, po_line.taxes_id.ids)],
                    'material_requisition_line_id': po_line.material_requisition_line_id.id,
                    'job_cost_line_id': po_line.job_cost_line_id.id if hasattr(po_line, 'job_cost_line_id') else False,
                    'date_planned': po_line.date_planned,
                    'display_type': po_line.display_type,
                }
                if 'department_id' in po_line._fields:
                    line_vals['department_id'] = po_line.department_id.id
                if 'analytic_account_id' in po_line._fields:
                    line_vals['analytic_account_id'] = po_line.analytic_account_id.id
                new_po_lines_vals.append((0, 0, line_vals))

        # Create New PO if applicable
        if self.action_type == 'create_po' and new_po_lines_vals:
            new_po_vals = {
                'partner_id': po.partner_id.id,
                'origin': po.origin or po.name,
                'order_line': new_po_lines_vals,
                'picking_type_id': po.picking_type_id.id,
                'company_id': po.company_id.id,
                'currency_id': po.currency_id.id,
            }
            
            # Copy contextual identifying fields from the original PO to retain budget hooks
            fields_to_copy = [
                'employee_id', 'department_id', 'dept_id', 
                'pr_number', 'requisition_order', 'material_requisition_id',
                'job_cost_sheet_id', 'project_id', 'job_order_id', 
                'procurement_pool_id', 'payment_date'
            ]
            for f in fields_to_copy:
                if f in po._fields:
                    val = getattr(po, f)
                    new_po_vals[f] = val.id if hasattr(val, 'id') else val
                    
            new_po = self.env['purchase.order'].create(new_po_vals)
            changes.append(_('<br/><strong>Created New PO (%s) for remaining shortfall.</strong>') % new_po.name)

        # Post audit message on PO
        if changes:
            body = _(
                '<strong>Close Shortfall (%s)</strong><br/>'
                '<strong>Reason:</strong> %s<br/>'
                '%s<br/>'
                '<strong>Lines adjusted:</strong><br/>%s'
            ) % (
                dict(self._fields['action_type'].selection).get(self.action_type),
                self.reason,
                _('<strong>Note:</strong> %s') % self.note if self.note else '',
                '<br/>'.join(changes),
            )
            po.message_post(
                body=body,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

        # Trigger budget recomputes identically for both MRs and PO
        if hasattr(po, '_update_budget_moves'):
            po._update_budget_moves()

        mr_ids = set()
        for line in po.order_line:
            if line.material_requisition_line_id:
                mr_ids.add(line.material_requisition_line_id.requisition_id.id)
        if mr_ids:
            mrs = self.env['material.requisition'].browse(list(mr_ids))
            if hasattr(mrs, '_update_budget_moves'):
                mrs._update_budget_moves()

        # Recompute BOQ tracking
        boq_lines = po.order_line.mapped('material_requisition_line_id.boq_line_id')
        if boq_lines:
            boq_lines._compute_purchase_tracking()

        return {'type': 'ir.actions.act_window_close'}

    def _process_receive_adjustments(self):
        """
        Process the new_qty_received values:
        - Product (Storable): Create and validate stock.picking.
        - Service: Write to po_line.qty_received.
        """
        StockPicking = self.env['stock.picking']
        StockMove = self.env['stock.move']

        picking_vals_by_po = {}
        for w_line in self.line_ids:
            diff = w_line.new_qty_received - w_line.qty_received
            if diff <= 0:
                continue

            po_line = w_line.po_line_id
            product = w_line.product_id

            if product.type == 'service':
                po_line.qty_received = w_line.new_qty_received

            elif product.type in ('product', 'consu'):
                po = po_line.order_id
                if po.id not in picking_vals_by_po:
                    picking_vals_by_po[po.id] = {
                        'po': po,
                        'moves': []
                    }
                picking_vals_by_po[po.id]['moves'].append((w_line, po_line, diff))

        # Create pickings for storables
        for po_data in picking_vals_by_po.values():
            po = po_data['po']
            picking_type = po.picking_type_id
            
            if not picking_type:
                raise ValidationError(_("Cannot create receipt: Purchase Order %s has no Deliver To (picking_type_id) set.") % po.name)

            picking = StockPicking.create({
                'partner_id': po.partner_id.id,
                'picking_type_id': picking_type.id,
                'location_id': po.partner_id.property_stock_supplier.id,
                'location_dest_id': picking_type.default_location_dest_id.id,
                'origin': _('Shortfall Adjustment: %s') % po.name,
                'company_id': po.company_id.id,
            })

            for w_line, po_line, diff in po_data['moves']:
                move = StockMove.create({
                    'name': po_line.name or po_line.product_id.name,
                    'product_id': po_line.product_id.id,
                    'product_uom_qty': diff,
                    'product_uom': po_line.product_uom.id,
                    'picking_id': picking.id,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'purchase_line_id': po_line.id,
                    'company_id': po.company_id.id,
                    'price_unit': po_line.price_unit,
                })

            picking.action_confirm()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
            picking.button_validate()


