# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare
import logging

_logger = logging.getLogger(__name__)


class MrpProductionAllocateWizard(models.TransientModel):
    _name = 'mrp.production.allocate.wizard'
    _description = 'Quick Allocate Materials to MO'

    mo_id = fields.Many2one('mrp.production', string='Manufacturing Order', required=True, readonly=True)
    line_ids = fields.One2many('mrp.production.allocate.wizard.line', 'wizard_id', string='Materials')
    note = fields.Html(string='Note', readonly=True)
    has_unallocated_materials = fields.Boolean(
        string="Has Unallocated Materials",
        compute="_compute_has_unallocated_materials",
        help="Indicates if there are unallocated materials in linked stock requests"
    )

    @api.model
    def default_get(self, fields_list):
        """Populate wizard with MO."""
        res = super().default_get(fields_list)
        
        mo_id = self.env.context.get('default_mo_id')
        if mo_id:
            res['mo_id'] = mo_id
        
        return res
    
    @api.depends("mo_id")
    def _compute_has_unallocated_materials(self):
        """Check if there are unallocated materials in linked stock requests."""
        for wizard in self:
            if not wizard.mo_id:
                wizard.has_unallocated_materials = False
                continue
            
            # Check all linked stock requests for unallocated materials
            wizard.has_unallocated_materials = any(
                float_compare(
                    line.qty_available_to_allocate,
                    0.0,
                    precision_rounding=line.uom_id.rounding
                ) > 0
                for request in wizard.mo_id.stock_request_ids
                for line in request.line_ids
                if request.state in ['requested', 'done']
            )
    
    def _populate_wizard(self):
        """Populate wizard with lines after creation."""
        self.ensure_one()
        
        if not self.mo_id:
            self.debug_info = "ERROR: No MO"
            return
        
        _logger.info("=== Populating wizard for MO: %s", self.mo_id.name)
        wizard_data = self._get_wizard_data(self.mo_id)
        
        # Create lines directly
        if 'line_ids' in wizard_data:
            for line_tuple in wizard_data['line_ids']:
                if line_tuple[0] == 0:  # (0, 0, {...})
                    line_vals = line_tuple[2]
                    line_vals['wizard_id'] = self.id
                    line = self.env['mrp.production.allocate.wizard.line'].create(line_vals)
                    _logger.info("=== Created line: product=%s (%s), uom=%s, qty=%.2f", 
                                line.product_id.id, line.product_id.name, 
                                line.uom_id.id, line.qty_to_consume)

    def _get_wizard_data(self, mo):
        """Get wizard data for an MO - returns dict for default_get."""
        _logger.info("=== Getting wizard data for MO: %s", mo.name)
        
        # Initialize result
        result = {}
        
        # Calculate missing components for this MO
        missing_components = {}  # {product_id: {'qty': qty, 'uom': uom}}
        for move in mo.move_raw_ids:
            if move.state == 'cancel':
                continue
            
            product = move.product_id
            uom = product.uom_id
            
            # Required vs consumed
            required_qty = move.product_uom._compute_quantity(move.product_uom_qty, uom)
            consumed_qty = move.product_uom._compute_quantity(move.quantity, uom)
            missing_qty = max(required_qty - consumed_qty, 0.0)
            
            if missing_qty > 0:
                if product.id not in missing_components:
                    missing_components[product.id] = {'qty': 0.0, 'uom': uom}
                missing_components[product.id]['qty'] += missing_qty
        
        _logger.info("=== Missing components: %s", 
                     {self.env['product.product'].browse(pid).name: data['qty'] 
                      for pid, data in missing_components.items()})
        
        # Collect available materials from stock requests
        # Only use missing filter if we have move_raw_ids AND missing components
        has_moves = len(mo.move_raw_ids) > 0
        use_missing_filter = has_moves and len(missing_components) > 0
        _logger.info("=== Has moves: %s, Missing count: %d, Use filter: %s", 
                     has_moves, len(missing_components), use_missing_filter)
        
        wizard_lines = []
        
        for request in mo.stock_request_ids:
            _logger.info("=== Checking request %s, state=%s", request.name, request.state)
            if request.state not in ['requested', 'done']:
                _logger.info("=== Skipping request (state not requested/done)")
                continue
            
            for req_line in request.line_ids:
                product_id = req_line.product_id.id
                available_qty = req_line.qty_available_to_allocate
                
                _logger.info("=== Product %s: available=%.2f", req_line.product_id.name, available_qty)
                
                if float_compare(available_qty, 0.0, precision_rounding=req_line.uom_id.rounding) <= 0:
                    _logger.info("=== Skipping (no available qty)")
                    continue
                
                qty_to_allocate = available_qty
                
                # Filter by missing components if any
                if use_missing_filter:
                    if product_id not in missing_components:
                        _logger.info("=== Skipping %s (not in missing components)", req_line.product_id.name)
                        continue
                    missing_qty = missing_components[product_id]['qty']
                    qty_to_allocate = min(available_qty, missing_qty)
                    _logger.info("=== Product in missing: missing=%.2f, to_allocate=%.2f", missing_qty, qty_to_allocate)
                
                if qty_to_allocate > 0:
                    # Get UOM with fallback
                    uom_id = req_line.uom_id.id if req_line.uom_id else req_line.product_id.uom_id.id
                    
                    if not uom_id:
                        _logger.error("=== Product %s has no UOM, skipping", req_line.product_id.name)
                        continue
                    
                    line_data = {
                        'request_line_id': req_line.id,
                        'product_id': req_line.product_id.id,
                        'available_qty': available_qty,
                        'qty_to_consume': qty_to_allocate,
                        'uom_id': uom_id,
                    }
                    wizard_lines.append(line_data)
                    _logger.info("=== Added line: product_id=%s (%s), uom_id=%s, qty=%.2f", 
                                req_line.product_id.id, req_line.product_id.name, uom_id, qty_to_allocate)
        
        _logger.info("=== Total lines created: %d", len(wizard_lines))
        
        # Add lines in format for default_get
        if wizard_lines:
            result['line_ids'] = [(0, 0, line_data) for line_data in wizard_lines]
            _logger.info("=== Returning line_ids with %d lines, sample: %s", 
                        len(wizard_lines), wizard_lines[0] if wizard_lines else "none")
        else:
            _logger.warning("=== No wizard lines to return")
        
        return result

    def action_allocate(self):
        """Perform the allocation and consumption."""
        self.ensure_one()
        
        _logger.info("=== Starting allocation for MO: %s", self.mo_id.name)
        
        # Filter valid lines
        lines_to_process = self.line_ids.filtered(
            lambda l: l.product_id and l.uom_id and l.request_line_id and l.qty_to_consume and l.qty_to_consume > 0
        )
        
        _logger.info("=== Lines to process: %d", len(lines_to_process))
        
        if not lines_to_process:
            if not self.line_ids:
                raise UserError(_(
                    "No materials available to allocate.\n\n"
                    "This MO either:\n"
                    "• Has no stock requests linked\n"
                    "• Already consumed all required materials\n"
                    "• Has no materials issued yet (validate stock request picking first)\n\n"
                    "Check the MO's Components tab and Stock Requests."
                ))
            else:
                problems = []
                for line in self.line_ids:
                    if not line.qty_to_consume or line.qty_to_consume <= 0:
                        problems.append(f"• {line.product_id.name if line.product_id else 'Unknown'}: quantity is 0 or empty")
                    if not line.uom_id:
                        problems.append(f"• {line.product_id.name if line.product_id else 'Unknown'}: missing unit of measure")
                
                error_msg = _("Cannot allocate materials.\n\nProblems found:\n%s\n\nPlease enter quantities greater than 0.") % "\n".join(problems[:5])
                raise UserError(error_msg)
        
        # Validate
        for line in lines_to_process:
            if line.qty_to_consume <= 0:
                raise ValidationError(_("Quantity must be positive for %s") % line.product_id.name)
            
            if float_compare(line.qty_to_consume, line.available_qty, precision_rounding=line.uom_id.rounding) > 0:
                raise ValidationError(
                    _("Quantity %.2f exceeds available %.2f for %s") % 
                    (line.qty_to_consume, line.available_qty, line.product_id.name)
                )
        
        # Group by request line and allocate
        summary_lines = []
        for line in lines_to_process:
            req_line = line.request_line_id
            product = line.product_id
            uom = line.uom_id
            qty_to_consume = line.qty_to_consume
            
            # Find or create raw material move
            raw_move = self.mo_id.move_raw_ids.filtered(
                lambda m: m.product_id == product and m.state not in ['done', 'cancel']
            )
            
            if not raw_move:
                # Create a new raw move
                raw_move = self.env['stock.move'].create({
                    'name': product.display_name,
                    'product_id': product.id,
                    'product_uom_qty': qty_to_consume,
                    'product_uom': uom.id,
                    'location_id': self.mo_id.location_src_id.id,
                    'location_dest_id': product.property_stock_production.id,
                    'raw_material_production_id': self.mo_id.id,
                    'company_id': self.mo_id.company_id.id,
                    'origin': self.mo_id.name,
                    'state': 'confirmed',
                })
                raw_move._action_confirm()
            else:
                raw_move = raw_move[0]
            
            # Convert qty to move's UoM
            qty_in_move_uom = uom._compute_quantity(qty_to_consume, raw_move.product_uom)
            
            # Get source location from request
            location_src = req_line.request_id.location_dest_id or self.mo_id.location_src_id
            
            # Create move line for consumption
            move_line_vals = {
                'move_id': raw_move.id,
                'product_id': product.id,
                'product_uom_id': raw_move.product_uom.id,
                'quantity': qty_in_move_uom,
                'location_id': location_src.id,
                'location_dest_id': raw_move.location_dest_id.id,
                'company_id': self.mo_id.company_id.id,
            }
            
            if line.lot_id:
                move_line_vals['lot_id'] = line.lot_id.id
            
            self.env['stock.move.line'].create(move_line_vals)
            
            # Update allocation
            req_line.qty_allocated += qty_to_consume
            
            summary_lines.append(product.name)
            _logger.info("=== Allocated: %s, qty=%.2f", product.name, qty_to_consume)
        
        # Recompute quantities
        for request in self.mo_id.stock_request_ids:
            request._compute_issued_quantities()
        
        # Show success message and close wizard
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('%d material(s) allocated successfully.') % len(summary_lines),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
    
    def action_mark_as_done(self):
        """Open mark as done confirmation wizard."""
        self.ensure_one()
        
        # Get stock requests linked to this MO
        stock_requests = self.mo_id.stock_request_ids.filtered(
            lambda r: r.state in ['requested', 'done']
        )
        
        if not stock_requests:
            raise UserError(_(
                "No stock requests found for this MO that can be marked as done.\n\n"
                "Please ensure:\n"
                "• Stock requests are linked to this MO\n"
                "• Stock requests are in 'Requested' or 'Done' state\n"
                "• Materials have been issued (picking validated)"
            ))
        
        # Check if any request has unallocated materials
        requests_with_unallocated = stock_requests.filtered(
            lambda r: any(
                float_compare(
                    line.qty_available_to_allocate,
                    0.0,
                    precision_rounding=line.uom_id.rounding
                ) > 0
                for line in r.line_ids
            )
        )
        
        if not requests_with_unallocated:
            raise UserError(_(
                "No unallocated materials found.\n\n"
                "All materials from linked stock requests have already been allocated."
            ))
        
        # If multiple requests, let user choose (for now, use first one)
        # In future, could add selection dialog
        request = requests_with_unallocated[0]
        
        # Open mark done wizard
        return {
            "name": _("Mark Stock Request as Done"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "mrp.stock.request.mark.done.wizard",
            "target": "new",
            "context": {
                "default_request_id": request.id,
            },
        }
    
    def _refresh_lines(self):
        """Refresh wizard lines after allocation."""
        self.ensure_one()
        
        # Remove existing lines
        self.line_ids.unlink()
        
        # Repopulate
        self._populate_wizard()
    
    def action_complete(self):
        """Complete and close wizard."""
        self.ensure_one()
        
        if self.line_ids:
            raise UserError(_("Cannot complete: materials remaining. Please allocate all first."))
        
        return {'type': 'ir.actions.act_window_close'}


class MrpProductionAllocateWizardLine(models.TransientModel):
    _name = 'mrp.production.allocate.wizard.line'
    _description = 'Quick Allocate Materials Line'

    wizard_id = fields.Many2one('mrp.production.allocate.wizard', required=True, ondelete='cascade')
    request_line_id = fields.Many2one('mrp.stock.request.line', string='Request Line', required=True)
    
    # Store these as regular fields (not computed) so they work in transient models
    product_id = fields.Many2one('product.product', string='Product', required=True)
    available_qty = fields.Float(string='Available', readonly=True, digits='Product Unit of Measure')
    qty_to_consume = fields.Float(string='Quantity to Allocate', required=True, digits='Product Unit of Measure')
    uom_id = fields.Many2one('uom.uom', string='UoM', required=True)
    lot_id = fields.Many2one('stock.lot', string='Lot/Serial')
    
    tracking = fields.Selection(related='product_id.tracking', readonly=True)
