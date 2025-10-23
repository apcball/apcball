# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_round, float_is_zero


class MrpStockRequestAllocateWizard(models.TransientModel):
    _name = "mrp.stock.request.allocate.wizard"
    _description = "Allocate Materials to Manufacturing Orders"

    request_id = fields.Many2one(
        "mrp.stock.request",
        string="Stock Request",
        required=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        "mrp.stock.request.allocate.wizard.line",
        "wizard_id",
        string="Allocation Lines",
    )
    company_id = fields.Many2one(
        related="request_id.company_id",
        string="Company",
    )

    @api.model
    def default_get(self, fields_list):
        """Prefill wizard lines with products that have quantities to allocate."""
        res = super().default_get(fields_list)
        
        request_id = self.env.context.get('default_request_id')
        default_mo_id = self.env.context.get('default_mo_id')  # Get MO from context if provided
        
        if request_id:
            request = self.env['mrp.stock.request'].browse(request_id)
            res['request_id'] = request_id
            
            # If no MO specified but request has only one MO, auto-select it
            if not default_mo_id and len(request.mo_ids) == 1:
                default_mo_id = request.mo_ids[0].id
            
            # Create wizard lines for products with available quantities
            wizard_lines = []
            for req_line in request.line_ids:
                if float_compare(
                    req_line.qty_available_to_allocate,
                    0.0,
                    precision_rounding=req_line.uom_id.rounding
                ) > 0:
                    # Create one line per request line
                    # Auto-select MO if: 1) provided in context, OR 2) request has only one MO
                    wizard_lines.append((0, 0, {
                        'request_line_id': req_line.id,
                        'available_to_allocate': req_line.qty_available_to_allocate,
                        'qty_to_consume': req_line.qty_available_to_allocate,  # Pre-fill with available qty
                        'mo_id': default_mo_id if default_mo_id else False,  # Auto-select if available
                    }))
            
            if wizard_lines:
                res['line_ids'] = wizard_lines
                
        return res

    def action_confirm(self):
        """Validate and perform consumption."""
        self.ensure_one()
        
        if not self.line_ids:
            raise UserError(_("Please add at least one allocation line."))

        # Validate each line
        self._validate_allocations()

        # Perform consumption for each line
        summary_lines = []
        for line in self.line_ids:
            if float_is_zero(line.qty_to_consume, precision_rounding=line.uom_id.rounding):
                continue
                
            consumed_qty = line._perform_consumption()
            
            # Create allocation record
            self.env['mrp.stock.request.allocation'].create({
                'request_line_id': line.request_line_id.id,
                'mo_id': line.mo_id.id,
                'uom_id': line.uom_id.id,
                'qty_consumed': consumed_qty,
                'lot_id': line.lot_id.id if line.lot_id else False,
                'notes': line.notes or '',
            })
            
            summary_lines.append(
                _("• MO %s: %s %s of %s%s") % (
                    line.mo_id.name,
                    consumed_qty,
                    line.uom_id.name,
                    line.product_id.display_name,
                    f" (Lot: {line.lot_id.name})" if line.lot_id else ""
                )
            )

        # Log in chatter
        if summary_lines:
            self.request_id.message_post(
                body=_("Materials allocated and consumed:<br/>%s") % "<br/>".join(summary_lines),
                subtype_id=self.env.ref("mail.mt_note").id
            )

        # Recompute quantities
        self.request_id._compute_issued_quantities()

        return {'type': 'ir.actions.act_window_close'}

    def _validate_allocations(self):
        """Validate allocation lines before processing."""
        # Group by request line to check total allocation doesn't exceed available
        line_allocations = {}
        
        for line in self.line_ids:
            # Skip zero quantity lines
            if float_is_zero(line.qty_to_consume, precision_rounding=line.uom_id.rounding):
                continue
            
            # Check MO belongs to request
            if line.mo_id not in self.request_id.mo_ids:
                raise ValidationError(
                    _("Manufacturing Order %s is not linked to this stock request.") % line.mo_id.name
                )
            
            # Check positive quantity
            if line.qty_to_consume <= 0:
                raise ValidationError(
                    _("Quantity to consume must be positive for product %s.") % line.product_id.name
                )
            
            # Check lot/serial requirements
            if line.product_id.tracking != 'none' and not line.lot_id:
                raise ValidationError(
                    _("Product %s requires lot/serial number tracking.") % line.product_id.display_name
                )
            
            # For serial tracking, qty should be 1 (or handle multiple serials)
            if line.product_id.tracking == 'serial':
                if float_compare(line.qty_to_consume, 1.0, precision_rounding=line.uom_id.rounding) != 0:
                    raise ValidationError(
                        _("Product %s is tracked by serial number. Quantity must be 1.0 per serial.") % 
                        line.product_id.display_name
                    )
            
            # Accumulate quantities per request line
            req_line_id = line.request_line_id.id
            if req_line_id not in line_allocations:
                line_allocations[req_line_id] = {
                    'request_line': line.request_line_id,
                    'total_qty': 0.0,
                }
            
            # Convert to request line UoM for comparison
            qty_in_req_uom = line.uom_id._compute_quantity(
                line.qty_to_consume,
                line.request_line_id.uom_id
            )
            line_allocations[req_line_id]['total_qty'] += qty_in_req_uom
        
        # Check each request line doesn't exceed available quantity
        for req_line_id, data in line_allocations.items():
            req_line = data['request_line']
            total_qty = data['total_qty']
            
            if float_compare(
                total_qty,
                req_line.qty_available_to_allocate,
                precision_rounding=req_line.uom_id.rounding
            ) > 0:
                raise ValidationError(
                    _("Total quantity to allocate for product %s (%.2f %s) exceeds available quantity (%.2f %s).") % (
                        req_line.product_id.display_name,
                        total_qty,
                        req_line.uom_id.name,
                        req_line.qty_available_to_allocate,
                        req_line.uom_id.name,
                    )
                )


class MrpStockRequestAllocateWizardLine(models.TransientModel):
    _name = "mrp.stock.request.allocate.wizard.line"
    _description = "Allocation Wizard Line"

    wizard_id = fields.Many2one(
        "mrp.stock.request.allocate.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    request_line_id = fields.Many2one(
        "mrp.stock.request.line",
        string="Request Line",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        related="request_line_id.product_id",
        readonly=True,
        store=True,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        related="request_line_id.uom_id",
        readonly=True,
        store=True,
    )
    available_to_allocate = fields.Float(
        string="Available to Allocate",
        digits="Product Unit of Measure",
        readonly=True,
    )
    mo_id = fields.Many2one(
        "mrp.production",
        string="Manufacturing Order",
        required=True,
        domain="[('id', 'in', available_mo_ids)]",
    )
    available_mo_ids = fields.Many2many(
        "mrp.production",
        compute="_compute_available_mo_ids",
        string="Available MOs",
    )
    qty_to_consume = fields.Float(
        string="Quantity to Consume",
        digits="Product Unit of Measure",
        required=True,
        default=0.0,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot/Serial Number",
        domain="[('product_id', '=', product_id), ('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(
        related="wizard_id.company_id",
        string="Company",
    )
    tracking = fields.Selection(
        related="product_id.tracking",
        string="Tracking",
    )
    notes = fields.Char(string="Notes")

    @api.depends("wizard_id.request_id.mo_ids")
    def _compute_available_mo_ids(self):
        """Compute available MOs from the request."""
        for line in self:
            if line.wizard_id and line.wizard_id.request_id:
                line.available_mo_ids = line.wizard_id.request_id.mo_ids
            else:
                line.available_mo_ids = False

    @api.onchange("available_to_allocate")
    def _onchange_available_to_allocate(self):
        """Auto-fill qty_to_consume with available quantity if not set."""
        if self.available_to_allocate and not self.qty_to_consume:
            self.qty_to_consume = self.available_to_allocate

    def _perform_consumption(self):
        """Perform the actual consumption to the MO."""
        self.ensure_one()
        
        mo = self.mo_id
        product = self.product_id
        qty_to_consume = self.qty_to_consume
        uom = self.uom_id
        lot = self.lot_id

        # Find or create raw move for this product in the MO
        raw_move = mo.move_raw_ids.filtered(
            lambda m: m.product_id == product and m.state not in ['done', 'cancel']
        )
        
        if not raw_move:
            # Check if MO is in a state where we can add moves
            if mo.state in ['done', 'cancel']:
                raise UserError(
                    _("Cannot add materials to MO %s because it is %s.") % (mo.name, mo.state)
                )
            
            # Create a new raw move
            raw_move = self.env['stock.move'].create({
                'name': product.display_name,
                'product_id': product.id,
                'product_uom_qty': qty_to_consume,
                'product_uom': uom.id,
                'location_id': mo.location_src_id.id,
                'location_dest_id': product.property_stock_production.id,
                'raw_material_production_id': mo.id,
                'company_id': mo.company_id.id,
                'origin': mo.name,
                'state': 'confirmed',
            })
            raw_move._action_confirm()
        else:
            raw_move = raw_move[0]

        # Convert qty to move's UoM
        qty_in_move_uom = uom._compute_quantity(qty_to_consume, raw_move.product_uom)

        # Record consumption using move lines
        # Check if we have stock in the source location
        location_src = self.wizard_id.request_id.location_dest_id or mo.location_src_id
        
        # Create move line for consumption
        # In Odoo 17, use 'quantity' instead of 'qty_done'
        if lot:
            # With lot/serial
            move_line_vals = {
                'move_id': raw_move.id,
                'product_id': product.id,
                'product_uom_id': raw_move.product_uom.id,
                'quantity': qty_in_move_uom,  # Use 'quantity' not 'qty_done'
                'lot_id': lot.id,
                'location_id': location_src.id,
                'location_dest_id': raw_move.location_dest_id.id,
                'company_id': mo.company_id.id,
            }
            self.env['stock.move.line'].create(move_line_vals)
        else:
            # Without lot/serial
            move_line_vals = {
                'move_id': raw_move.id,
                'product_id': product.id,
                'product_uom_id': raw_move.product_uom.id,
                'quantity': qty_in_move_uom,  # Use 'quantity' not 'qty_done'
                'location_id': location_src.id,
                'location_dest_id': raw_move.location_dest_id.id,
                'company_id': mo.company_id.id,
            }
            self.env['stock.move.line'].create(move_line_vals)

        # Note: The move's quantity field is automatically computed from move lines
        # No need to update it manually

        # Return the actual consumed quantity in the line's UoM
        return qty_to_consume
