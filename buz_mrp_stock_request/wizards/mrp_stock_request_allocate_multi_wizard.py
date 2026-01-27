# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_round, float_is_zero


class MrpStockRequestAllocateMultiWizard(models.TransientModel):
    _name = "mrp.stock.request.allocate.multi.wizard"
    _description = "Allocate Materials to Multiple MOs (Tab View)"

    request_id = fields.Many2one(
        "mrp.stock.request",
        string="Stock Request",
        required=True,
        readonly=True,
    )
    mo_allocation_ids = fields.One2many(
        "mrp.stock.request.mo.allocation",
        "wizard_id",
        string="MO Allocations",
    )
    company_id = fields.Many2one(
        related="request_id.company_id",
        string="Company",
    )
    info_html = fields.Html(
        string="Information",
        compute="_compute_info_html",
    )
    has_unallocated_materials = fields.Boolean(
        string="Has Unallocated Materials",
        compute="_compute_has_unallocated_materials",
        help="Indicates if there are unallocated materials in the stock request"
    )

    @api.depends("request_id", "request_id.mo_ids", "mo_allocation_ids")
    def _compute_info_html(self):
        """Display helpful information."""
        for wizard in self:
            # Count from request's MOs (source of truth) or allocated MOs
            if wizard.request_id:
                mo_count = len(wizard.request_id.mo_ids)
                mo_names = ", ".join(wizard.request_id.mo_ids.mapped('name'))
            else:
                mo_count = len(wizard.mo_allocation_ids)
                mo_names = ", ".join(wizard.mo_allocation_ids.mapped('mo_id.name'))
                
            wizard.info_html = _(
                "<div class='alert alert-info'>"
                "<strong>📋 Multi-MO Allocation</strong><br/>"
                "Stock Request: <strong>%s</strong><br/>"
                "Manufacturing Orders: <strong>%d</strong> (%s)<br/><br/>"
                "💡 <strong>Instructions:</strong><br/>"
                "• Click on each MO below to review and adjust quantities<br/>"
                "• Select lot/serial numbers for tracked products<br/>"
                "• Click <strong>Allocate All</strong> to confirm all allocations<br/>"
                "• Set quantity to 0 to skip allocation"
                "</div>"
            ) % (wizard.request_id.name if wizard.request_id else "N/A", mo_count, mo_names)

    @api.depends("request_id")
    def _compute_has_unallocated_materials(self):
        """Check if there are unallocated materials in the stock request."""
        import logging
        _logger = logging.getLogger(__name__)
        
        for wizard in self:
            if not wizard.request_id:
                wizard.has_unallocated_materials = False
                _logger.info("=== _compute_has_unallocated_materials: No request_id, setting to False")
                continue
            
            # Check each line for available materials
            has_unallocated = False
            for line in wizard.request_id.line_ids:
                has_qty = float_compare(
                    line.qty_available_to_allocate,
                    0.0,
                    precision_rounding=line.uom_id.rounding
                ) > 0
                _logger.info("=== _compute_has_unallocated_materials: Product %s, available=%s, has_qty=%s",
                             line.product_id.name, line.qty_available_to_allocate, has_qty)
                if has_qty:
                    has_unallocated = True
                    break
            
            wizard.has_unallocated_materials = has_unallocated
            _logger.info("=== _compute_has_unallocated_materials: Final result=%s for wizard %s",
                        has_unallocated, wizard.id)

    @api.model
    def default_get(self, fields_list):
        """Create one tab per MO with available materials."""
        res = super().default_get(fields_list)
        
        request_id = self.env.context.get('default_request_id')
        if request_id:
            res['request_id'] = request_id
                
        return res
    
    @api.model
    def create(self, vals):
        """Create wizard and populate MO allocations."""
        wizard = super().create(vals)
        
        if wizard.request_id:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info("=== Creating MO allocations for request: %s", wizard.request_id.name)
            _logger.info("=== MOs in request: %s", wizard.request_id.mo_ids.mapped('name'))
            
            # Create one allocation group per MO
            created_count = 0
            for mo in wizard.request_id.mo_ids:
                # Collect available materials for this MO
                line_vals = []
                for req_line in wizard.request_id.line_ids:
                    _logger.info("=== Product %s: available = %s", req_line.product_id.name, req_line.qty_available_to_allocate)
                    if float_compare(
                        req_line.qty_available_to_allocate,
                        0.0,
                        precision_rounding=req_line.uom_id.rounding
                    ) > 0:
                        line_vals.append((0, 0, {
                            'request_line_id': req_line.id,
                            'product_id': req_line.product_id.id,
                            'uom_id': req_line.uom_id.id,
                            'available_qty': req_line.qty_available_to_allocate,
                            'qty_to_consume': req_line.qty_available_to_allocate,
                        }))
                
                _logger.info("=== MO %s has %d materials available", mo.name, len(line_vals))
                
                # Create MO allocation even if no materials (so user sees the MO in list)
                # If no materials, show empty - user can't allocate anything but sees why
                mo_alloc = self.env['mrp.stock.request.mo.allocation'].create({
                    'wizard_id': wizard.id,
                    'mo_id': mo.id,
                    'line_ids': line_vals,
                })
                created_count += 1
                _logger.info("=== Created MO allocation: %s (id=%s) with %d lines", mo_alloc.mo_id.name, mo_alloc.id, len(line_vals))
            
            _logger.info("=== Total MO allocations created: %d", created_count)
            
            # Force refresh to show MO allocations
            wizard.invalidate_recordset(['mo_allocation_ids'])
            
            # Check what we have
            _logger.info("=== Wizard mo_allocation_ids count: %d", len(wizard.mo_allocation_ids))
        
        return wizard

    def action_allocate_all(self):
        """Allocate materials to all MOs."""
        self.ensure_one()
        
        if not self.mo_allocation_ids:
            raise UserError(_("No allocations to process."))

        # Collect all lines to allocate
        all_lines = []
        for mo_allocation in self.mo_allocation_ids:
            for line in mo_allocation.line_ids:
                if not float_is_zero(line.qty_to_consume, precision_rounding=line.uom_id.rounding):
                    all_lines.append(line)
        
        if not all_lines:
            raise UserError(_("Please specify quantities to allocate."))

        # Validate all allocations
        self._validate_all_allocations(all_lines)

        # Perform allocations
        summary_by_mo = {}
        for line in all_lines:
            consumed_qty = line._perform_consumption()
            
            # Create allocation record
            self.env['mrp.stock.request.allocation'].create({
                'request_line_id': line.request_line_id.id,
                'mo_id': line.mo_allocation_id.mo_id.id,
                'uom_id': line.uom_id.id,
                'qty_consumed': consumed_qty,
                'lot_id': line.lot_id.id if line.lot_id else False,
                'notes': line.notes or '',
            })
            
            # Group by MO for summary
            mo_name = line.mo_allocation_id.mo_id.name
            if mo_name not in summary_by_mo:
                summary_by_mo[mo_name] = []
            
            summary_by_mo[mo_name].append(
                _("  • %s %s of %s%s") % (
                    consumed_qty,
                    line.uom_id.name,
                    line.product_id.display_name,
                    f" (Lot: {line.lot_id.name})" if line.lot_id else ""
                )
            )

        # Log in stock request chatter
        if summary_by_mo:
            summary_lines = []
            for mo_name, lines in summary_by_mo.items():
                summary_lines.append(f"<strong>{mo_name}:</strong>")
                summary_lines.extend(lines)
            
            self.request_id.message_post(
                body=_("Materials allocated to multiple MOs:<br/>%s") % "<br/>".join(summary_lines),
                subtype_id=self.env.ref("mail.mt_note").id
            )

        # Log in each MO's chatter
        for mo_allocation in self.mo_allocation_ids:
            mo = mo_allocation.mo_id
            mo_lines = [line for line in all_lines if line.mo_allocation_id == mo_allocation]
            if mo_lines:
                mo_summary = [
                    _("• %s %s of %s%s") % (
                        line.qty_to_consume,
                        line.uom_id.name,
                        line.product_id.display_name,
                        f" (Lot: {line.lot_id.name})" if line.lot_id else ""
                    )
                    for line in mo_lines
                ]
                mo.message_post(
                    body=_("Materials allocated from %s:<br/>%s") % (
                        self.request_id.name, 
                        "<br/>".join(mo_summary)
                    ),
                    subtype_id=self.env.ref("mail.mt_note").id
                )

        # Recompute quantities
        self.request_id._compute_issued_quantities()

        # Show success message
        total_allocated = len(all_lines)
        total_mos = len(summary_by_mo)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('%d material(s) allocated to %d MO(s)') % (total_allocated, total_mos),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_mark_as_done(self):
        """Open mark as done confirmation wizard."""
        self.ensure_one()
        
        request = self.request_id
        
        if not request:
            raise UserError(_("No stock request found."))
        
        # Check if request has unallocated materials
        has_unallocated = any(
            float_compare(
                line.qty_available_to_allocate,
                0.0,
                precision_rounding=line.uom_id.rounding
            ) > 0
            for line in request.line_ids
        )
        
        if not has_unallocated:
            raise UserError(_(
                "No unallocated materials found.\n\n"
                "All materials from this stock request have already been allocated."
            ))
        
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

    def _validate_all_allocations(self, lines):
        """Validate all allocation lines."""
        # Group by request line to check total doesn't exceed available
        line_totals = {}
        
        for line in lines:
            # Basic validations
            if line.qty_to_consume <= 0:
                raise ValidationError(
                    _("Quantity must be positive for product %s in MO %s") % (
                        line.product_id.name,
                        line.mo_allocation_id.mo_id.name
                    )
                )
            
            # Tracking validations
            if line.product_id.tracking != 'none' and not line.lot_id:
                raise ValidationError(
                    _("Product %s requires lot/serial number in MO %s") % (
                        line.product_id.display_name,
                        line.mo_allocation_id.mo_id.name
                    )
                )
            
            if line.product_id.tracking == 'serial':
                if float_compare(line.qty_to_consume, 1.0, precision_rounding=line.uom_id.rounding) != 0:
                    raise ValidationError(
                        _("Product %s is tracked by serial. Quantity must be 1.0 in MO %s") % (
                            line.product_id.display_name,
                            line.mo_allocation_id.mo_id.name
                        )
                    )
            
            # Accumulate totals per request line
            req_line_id = line.request_line_id.id
            if req_line_id not in line_totals:
                line_totals[req_line_id] = {
                    'request_line': line.request_line_id,
                    'total': 0.0,
                }
            
            # Convert to request line UoM
            qty_in_req_uom = line.uom_id._compute_quantity(
                line.qty_to_consume,
                line.request_line_id.uom_id
            )
            line_totals[req_line_id]['total'] += qty_in_req_uom
        
        # Check totals don't exceed available
        for req_line_id, data in line_totals.items():
            req_line = data['request_line']
            total = data['total']
            
            if float_compare(
                total,
                req_line.qty_available_to_allocate,
                precision_rounding=req_line.uom_id.rounding
            ) > 0:
                raise ValidationError(
                    _("Total allocation for product %s (%.2f %s) exceeds available quantity (%.2f %s)") % (
                        req_line.product_id.display_name,
                        total,
                        req_line.uom_id.name,
                        req_line.qty_available_to_allocate,
                        req_line.uom_id.name,
                    )
                )


class MrpStockRequestMoAllocation(models.TransientModel):
    _name = "mrp.stock.request.mo.allocation"
    _description = "MO Allocation Group (One per MO)"

    wizard_id = fields.Many2one(
        "mrp.stock.request.allocate.multi.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    mo_id = fields.Many2one(
        "mrp.production",
        string="Manufacturing Order",
        required=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        "mrp.stock.request.mo.allocation.line",
        "mo_allocation_id",
        string="Materials to Allocate",
    )
    company_id = fields.Many2one(
        related="wizard_id.company_id",
        string="Company",
    )
    total_lines = fields.Integer(
        string="Total Items",
        compute="_compute_total_lines",
    )

    @api.depends("line_ids")
    def _compute_total_lines(self):
        for rec in self:
            rec.total_lines = len(rec.line_ids)


class MrpStockRequestMoAllocationLine(models.TransientModel):
    _name = "mrp.stock.request.mo.allocation.line"
    _description = "Material Line for MO Allocation"

    mo_allocation_id = fields.Many2one(
        "mrp.stock.request.mo.allocation",
        string="MO Allocation",
        required=True,
        ondelete="cascade",
    )
    request_line_id = fields.Many2one(
        "mrp.stock.request.line",
        string="Request Line",
        required=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        readonly=True,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="UoM",
        required=True,
        readonly=True,
    )
    available_qty = fields.Float(
        string="Available",
        digits="Product Unit of Measure",
        readonly=True,
    )
    qty_to_consume = fields.Float(
        string="Qty to Consume",
        digits="Product Unit of Measure",
        required=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot/Serial",
        domain="[('product_id', '=', product_id), ('company_id', '=', company_id)]",
    )
    tracking = fields.Selection(
        related="product_id.tracking",
        string="Tracking",
    )
    company_id = fields.Many2one(
        related="mo_allocation_id.company_id",
        string="Company",
    )
    notes = fields.Char(string="Notes")

    @api.onchange("qty_to_consume")
    def _onchange_qty_to_consume(self):
        """Warn if exceeding available."""
        if self.qty_to_consume and self.available_qty:
            if float_compare(
                self.qty_to_consume,
                self.available_qty,
                precision_rounding=self.uom_id.rounding
            ) > 0:
                return {
                    'warning': {
                        'title': _('Warning'),
                        'message': _('Quantity exceeds available quantity.')
                    }
                }

    def _perform_consumption(self):
        """Perform consumption to MO."""
        self.ensure_one()
        
        mo = self.mo_allocation_id.mo_id
        product = self.product_id
        qty_to_consume = self.qty_to_consume
        uom = self.uom_id
        lot = self.lot_id

        # Find or create raw move
        raw_move = mo.move_raw_ids.filtered(
            lambda m: m.product_id == product and m.state not in ['done', 'cancel']
        )
        
        if not raw_move:
            if mo.state in ['done', 'cancel']:
                raise UserError(
                    _("Cannot add materials to MO %s (state: %s)") % (mo.name, mo.state)
                )
            
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

        # Convert quantity
        qty_in_move_uom = uom._compute_quantity(qty_to_consume, raw_move.product_uom)

        # Get location from request
        location_src = self.mo_allocation_id.wizard_id.request_id.location_dest_id or mo.location_src_id
        
        # Create move line
        move_line_vals = {
            'move_id': raw_move.id,
            'product_id': product.id,
            'product_uom_id': raw_move.product_uom.id,
            'quantity': qty_in_move_uom,
            'location_id': location_src.id,
            'location_dest_id': raw_move.location_dest_id.id,
            'company_id': mo.company_id.id,
        }
        
        if lot:
            move_line_vals['lot_id'] = lot.id
            
        self.env['stock.move.line'].create(move_line_vals)

        return qty_to_consume
