from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_round, float_is_zero
from odoo.tools.translate import _


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    mrp_stock_request_count = fields.Integer(
        string="Stock Request Count",
        compute="_compute_mrp_stock_request_count",
    )
    stock_request_ids = fields.Many2many(
        "mrp.stock.request",
        "mrp_stock_request_production_rel",
        "production_id",
        "request_id",
        string="Stock Requests",
    )
    has_available_to_allocate = fields.Boolean(
        string="Has Materials to Allocate",
        compute="_compute_has_available_to_allocate",
        help="Indicates if there are materials available to allocate from stock requests",
    )
    available_allocations_count = fields.Integer(
        string="Available Allocations Count",
        compute="_compute_has_available_to_allocate",
    )

    def _compute_mrp_stock_request_count(self):
        for mo in self:
            mo.mrp_stock_request_count = len(mo.stock_request_ids)

    def _compute_has_available_to_allocate(self):
        """Check if there are materials available to allocate to this MO."""
        for mo in self:
            count = 0
            has_available = False
            # Check all linked stock requests
            for request in mo.stock_request_ids:
                if request.state in ['requested', 'done']:
                    # Check if any line has available quantity
                    for line in request.line_ids:
                        if float_compare(
                            line.qty_available_to_allocate,
                            0.0,
                            precision_rounding=line.uom_id.rounding
                        ) > 0:
                            has_available = True
                            count += 1
            mo.has_available_to_allocate = has_available
            mo.available_allocations_count = count

    def action_view_stock_requests(self):
        """
        This function returns an action that display existing stock requests
        of a given production order.
        """
        self.ensure_one()
        result = self.env["ir.actions.act_window"]._for_xml_id(
            "buz_mrp_stock_request.action_mrp_stock_request"
        )
        # Get stock requests for this MO
        stock_requests = self.stock_request_ids
        # Show existing stock requests
        if len(stock_requests) > 1:
            result["domain"] = [("id", "in", stock_requests.ids)]
        elif len(stock_requests) == 1:
            res = self.env.ref("buz_mrp_stock_request.view_mrp_stock_request_form", False)
            result["views"] = [(res and res.id or False, "form")]
            result["res_id"] = stock_requests.id
        else:
            # If no stock requests exist, create a new one with this MO
            result["context"] = {
                "default_mo_ids": [(6, 0, [self.id])],
                "default_company_id": self.company_id.id,
                "default_location_id": self.location_src_id.id,
                "default_location_dest_id": self.location_dest_id.id,
            }
        return result

    def action_create_stock_request(self):
        """Create a new stock request from this MO with missing components pre-filled."""
        self.ensure_one()
        
        # Check if MO is in correct state
        if self.state not in ['confirmed', 'progress', 'to_close']:
            raise UserError(_("Stock request can only be created for confirmed Manufacturing Orders."))
        
        # Create the stock request
        request = self.env['mrp.stock.request'].create({
            'mo_ids': [(6, 0, [self.id])],
            'company_id': self.company_id.id,
            'location_id': self.location_src_id.id,
            'location_dest_id': self.location_dest_id.id,
            'picking_type_id': self._get_default_picking_type().id if self._get_default_picking_type() else False,
        })
        
        # Auto-prepare lines from this MO
        request.action_prepare_from_mos()
        
        # Open the created request
        return {
            "name": _("Stock Request"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "mrp.stock.request",
            "res_id": request.id,
            "target": "current",
        }
    
    def _get_default_picking_type(self):
        """Get default internal picking type for stock request."""
        picking_type = self.env["stock.picking.type"].search([
            ("code", "=", "internal"),
            ("warehouse_id", "=", self.warehouse_id.id if self.warehouse_id else False),
            ("company_id", "=", self.company_id.id),
        ], limit=1)
        
        if not picking_type:
            picking_type = self.env["stock.picking.type"].search([
                ("code", "=", "internal"),
                ("company_id", "=", self.company_id.id),
            ], limit=1)
        
        return picking_type

    def action_allocate_materials_quick(self):
        """Open quick allocation wizard for this MO with pre-filtered materials."""
        self.ensure_one()
        
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info("=== Quick allocation for MO: %s", self.name)
        _logger.info("=== has_available_to_allocate: %s", self.has_available_to_allocate)
        _logger.info("=== Stock requests: %s", self.stock_request_ids.mapped('name'))
        
        # Check if there are materials available to allocate
        if not self.has_available_to_allocate:
            raise UserError(_("No materials available to allocate to this Manufacturing Order."))
        
        # Check if there are stock requests with materials
        available_materials = []
        for request in self.stock_request_ids:
            if request.state in ['requested', 'done']:
                for line in request.line_ids:
                    if line.qty_available_to_allocate > 0:
                        available_materials.append(f"{line.product_id.name}: {line.qty_available_to_allocate}")
        
        _logger.info("=== Available materials: %s", available_materials)
        
        if not available_materials:
            raise UserError(_("No materials found to allocate. Please check that stock requests have been issued."))
        
        # Create wizard and populate it
        wizard = self.env['mrp.production.allocate.wizard'].create({
            'mo_id': self.id,
        })
        wizard._populate_wizard()
        
        # Open the wizard
        return {
            "name": _("Allocate Materials to %s") % self.name,
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "mrp.production.allocate.wizard",
            "res_id": wizard.id,
            "target": "new",
        }


class StockPicking(models.Model):
    _inherit = "stock.picking"

    stock_request_id = fields.Many2one(
        "mrp.stock.request",
        string="Origin Stock Request",
        copy=False,
    )

    def action_open_stock_request(self):
        """Return action to open the related stock request."""
        self.ensure_one()
        if not self.stock_request_id:
            return

        return {
            "name": _("Stock Request"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "mrp.stock.request",
            "res_id": self.stock_request_id.id,
            "target": "current",
        }

    def _action_done(self):
        """Update request when picking is done."""
        res = super()._action_done()
        
        # Update related stock requests
        for picking in self:
            if picking.stock_request_id:
                picking.stock_request_id._compute_issued_quantities()
                
                # If all lines are fully issued, mark as done (configurable behavior)
                config = self.env['ir.config_parameter'].sudo()
                auto_done = config.get_param('mrp_stock_request.auto_done_on_issue', 'False')
                if auto_done == 'True':
                    request = picking.stock_request_id
                    if all(float_is_zero(line.qty_remaining, precision_rounding=line.uom_id.rounding) 
                           for line in request.line_ids):
                        request.write({"state": "done"})
        
        return res


class MrpStockRequest(models.Model):
    _name = "mrp.stock.request"
    _description = "MRP Stock Request - Multi-MO Material Issuing"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name desc"

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _("New"),
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    mo_ids = fields.Many2many(
        "mrp.production",
        "mrp_stock_request_production_rel",
        "request_id",
        "production_id",
        string="Manufacturing Orders",
        domain="[('company_id', '=', company_id), ('state', 'in', ['confirmed', 'progress', 'to_close'])]",
        tracking=True,
    )
    line_ids = fields.One2many(
        "mrp.stock.request.line",
        "request_id",
        string="Request Lines",
        copy=True,
    )
    picking_ids = fields.Many2many(
        "stock.picking",
        compute="_compute_picking_ids",
        string="Internal Transfers",
        store=True,
    )
    move_ids = fields.Many2many(
        "stock.move",
        compute="_compute_move_ids",
        string="Stock Moves",
        store=True,
    )
    picking_type_id = fields.Many2one(
        "stock.picking.type",
        string="Operation Type",
        required=True,
        domain="[('code', '=', 'internal'), ('company_id', '=', company_id)]",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Source Location",
        required=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
        tracking=True,
    )
    location_dest_id = fields.Many2one(
        "stock.location",
        string="Destination Location",
        required=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
        tracking=True,
    )
    request_date = fields.Date(
        string="Request Date",
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    requested_by = fields.Many2one(
        "res.users",
        string="Requested By",
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("requested", "Requested"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        readonly=True,
        default="draft",
        tracking=True,
    )
    qty_issued_total = fields.Float(
        string="Total Issued",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    qty_remaining_total = fields.Float(
        string="Total Remaining",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    note = fields.Text(string="Notes")

    @api.depends("line_ids.move_ids")
    def _compute_picking_ids(self):
        for request in self:
            pickings = request.line_ids.mapped("move_ids.picking_id")
            request.picking_ids = pickings

    @api.depends("line_ids.move_ids")
    def _compute_move_ids(self):
        for request in self:
            request.move_ids = request.line_ids.mapped("move_ids")

    @api.depends("line_ids.qty_issued", "line_ids.qty_remaining")
    def _compute_totals(self):
        for request in self:
            request.qty_issued_total = sum(request.line_ids.mapped("qty_issued"))
            request.qty_remaining_total = sum(request.line_ids.mapped("qty_remaining"))
            
            # Auto-update state to done when all materials are allocated
            if request.state == 'requested' and request.qty_remaining_total == 0.0 and request.qty_issued_total > 0.0:
                request.state = 'done'

    @api.constrains("mo_ids", "company_id")
    def _check_company_consistency(self):
        """Ensure all MOs belong to the same company as the request."""
        for request in self:
            if request.mo_ids:
                invalid_mos = request.mo_ids.filtered(lambda mo: mo.company_id != request.company_id)
                if invalid_mos:
                    raise ValidationError(
                        _("All Manufacturing Orders must belong to company %s. "
                          "Invalid MOs: %s") % (
                            request.company_id.name,
                            ", ".join(invalid_mos.mapped("name"))
                        )
                    )

    @api.constrains("line_ids")
    def _check_request_lines(self):
        """Validate request lines."""
        for request in self:
            if request.state in ["draft"] and not request.line_ids:
                continue  # Allow saving draft without lines
            for line in request.line_ids:
                if line.qty_requested <= 0:
                    raise ValidationError(
                        _("Quantity must be positive for product %s") % line.product_id.name
                    )

    @api.model
    def create(self, vals):
        if vals.get("name", _("New")) == _("New"):
            vals["name"] = self.env["ir.sequence"].next_by_code("mrp.stock.request") or _("New")
        return super().create(vals)

    def unlink(self):
        """Prevent deletion if not in draft or if pickings exist."""
        for request in self:
            if request.state != "draft":
                raise UserError(_("Cannot delete a request that is not in draft state."))
            if request.picking_ids.filtered(lambda p: p.state not in ["draft", "cancel"]):
                raise UserError(_("Cannot delete a request that has posted pickings."))
        return super().unlink()

    def action_prepare_from_mos(self):
        """Prefill lines from selected MOs' components that have shortages."""
        self.ensure_one()
        if not self.mo_ids:
            raise UserError(_("Please select at least one Manufacturing Order."))

        # Clear existing lines
        self.line_ids.unlink()

        # Get shortage policy from config
        config = self.env['ir.config_parameter'].sudo()
        policy = config.get_param('mrp_stock_request.shortage_policy', 'subtract_done')

        # Dictionary to aggregate shortages by product
        product_shortages = {}  # {product_id: {uom_id: qty}}

        for mo in self.mo_ids:
            for move in mo.move_raw_ids:
                # Skip non-storable products
                if move.product_id.type != "product":
                    continue
                
                # Skip moves that are cancelled
                if move.state == 'cancel':
                    continue

                product = move.product_id
                uom = product.uom_id

                # Calculate required quantity (To Consume = product_uom_qty)
                required_qty = move.product_uom._compute_quantity(
                    move.product_uom_qty, 
                    uom
                )

                # Calculate already consumed quantity (Consumed = quantity)
                # In Odoo, stock.move.quantity is the sum of move_line quantities (done qty)
                consumed_qty = move.product_uom._compute_quantity(
                    move.quantity,  # This is the consumed/done quantity
                    uom
                )

                # Calculate reserved if policy requires
                reserved_qty = 0.0
                if policy == 'subtract_done_and_reserved':
                    # reserved_availability shows reserved qty that's not yet consumed
                    reserved_qty = move.product_uom._compute_quantity(
                        move.reserved_availability,
                        uom
                    )

                # Calculate shortage: Required - Consumed - Reserved
                # This gives us what's still needed
                shortage = max(required_qty - consumed_qty - reserved_qty, 0.0)

                # Round to UoM rounding
                shortage = float_round(shortage, precision_rounding=uom.rounding)

                if float_compare(shortage, 0.0, precision_rounding=uom.rounding) > 0:
                    key = product.id
                    if key not in product_shortages:
                        product_shortages[key] = shortage
                    else:
                        product_shortages[key] += shortage

        # Create request lines
        for product_id, qty in product_shortages.items():
            product = self.env['product.product'].browse(product_id)
            self.env["mrp.stock.request.line"].create({
                "request_id": self.id,
                "product_id": product_id,
                "uom_id": product.uom_id.id,
                "qty_requested": qty,
            })

        # Log message
        self.message_post(
            body=_("Request lines prepared from %d Manufacturing Order(s). %d product line(s) created.") % (
                len(self.mo_ids), len(self.line_ids)
            ),
            subtype_id=self.env.ref("mail.mt_note").id
        )

    def action_confirm(self):
        """Open confirmation wizard before creating internal transfer(s)."""
        self.ensure_one()
        
        if self.state != "draft":
            raise UserError(_("Only draft requests can be confirmed."))

        # Validate
        if not self.line_ids:
            raise UserError(_("Cannot confirm request without lines."))
        
        if not self.mo_ids:
            raise UserError(_("Please select at least one Manufacturing Order."))

        if not self.location_id or not self.location_dest_id:
            raise UserError(_("Source and destination locations are required."))

        # Open confirmation wizard instead of directly confirming
        return {
            "name": _("Confirm Stock Request"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "mrp.stock.request.confirm.wizard",
            "target": "new",
            "context": {
                "default_request_id": self.id,
            },
        }

    def action_confirm_with_validation(self):
        """Create internal transfer(s) from request lines after confirmation."""
        for request in self:
            if request.state != "draft":
                raise UserError(_("Only draft requests can be confirmed."))

            # Validate
            if not request.line_ids:
                raise UserError(_("Cannot confirm request without lines."))
            
            if not request.mo_ids:
                raise UserError(_("Please select at least one Manufacturing Order."))

            if not request.location_id or not request.location_dest_id:
                raise UserError(_("Source and destination locations are required."))

            # Create picking(s)
            pickings = request._create_issue_picking()

            # Update state
            request.write({"state": "requested"})

            # Log in chatter
            picking_links = ", ".join([
                "<a href=# data-oe-model=stock.picking data-oe-id=%d>%s</a>" % (p.id, p.name)
                for p in pickings
            ])
            request.message_post(
                body=_("Internal transfer(s) created: %s") % picking_links,
                subtype_id=self.env.ref("mail.mt_note").id
            )

    def _create_issue_picking(self):
        """Create one or more pickings to issue materials."""
        self.ensure_one()

        picking_type = self.picking_type_id
        if not picking_type:
            raise UserError(_("Please select an operation type."))

        # For simplicity, create one picking per request
        # Could be enhanced to split by warehouse/route if needed
        picking_vals = {
            "picking_type_id": picking_type.id,
            "location_id": self.location_id.id,
            "location_dest_id": self.location_dest_id.id,
            "origin": self.name,
            "company_id": self.company_id.id,
            "note": self.note or "",
            "stock_request_id": self.id,
        }

        picking = self.env["stock.picking"].create(picking_vals)

        # Create moves for each line
        for line in self.line_ids:
            if line.qty_requested > 0:
                move_vals = {
                    "name": line.product_id.display_name or line.product_id.name,
                    "product_id": line.product_id.id,
                    "product_uom_qty": line.qty_requested,
                    "product_uom": line.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": self.location_id.id,
                    "location_dest_id": self.location_dest_id.id,
                    "company_id": self.company_id.id,
                    "origin": self.name,
                }
                move = self.env["stock.move"].create(move_vals)
                # Link move to request line
                line.write({"move_ids": [(4, move.id)]})

        # Confirm the picking
        if picking.state == "draft":
            picking.action_confirm()

        return picking

    def _compute_issued_quantities(self):
        """Recompute issued quantities from done moves."""
        for request in self:
            for line in request.line_ids:
                line._compute_qty_issued()

    def action_allocate_wizard(self):
        """Open allocation wizard - smart selection based on MO count."""
        self.ensure_one()
        
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info("=== action_allocate_wizard called for: %s", self.name)
        _logger.info("=== Stock Request state: %s", self.state)
        _logger.info("=== Stock Request MOs: %s (count: %d)", self.mo_ids.mapped('name'), len(self.mo_ids))

        # DEBUG: Check if allocation should be allowed for this state
        if self.state == 'done':
            _logger.warning("=== ALLOCATION BLOCKED: Stock request %s is in 'done' state", self.name)
            raise UserError(_("Cannot allocate materials from a stock request that is marked as 'done'."))
        
        if not self.picking_ids.filtered(lambda p: p.state == 'done'):
            raise UserError(_("No materials have been issued yet. Please validate the picking first."))

        # Check if there are any quantities available to allocate
        has_available = any(
            float_compare(
                line.qty_available_to_allocate,
                0.0,
                precision_rounding=line.uom_id.rounding
            ) > 0
            for line in self.line_ids
        )

        if not has_available:
            raise UserError(_("No quantities available to allocate."))

        # Smart wizard selection based on number of MOs
        mo_count = len(self.mo_ids)
        _logger.info("=== MO count: %d, using %s wizard", mo_count, "multi" if mo_count > 1 else "single")
        
        if mo_count > 1:
            # Multiple MOs: Create wizard first, then populate
            wizard = self.env['mrp.stock.request.allocate.multi.wizard'].create({
                'request_id': self.id,
            })
            
            # Now open the wizard
            return {
                "name": _("Allocate Materials to Manufacturing Orders"),
                "type": "ir.actions.act_window",
                "view_mode": "form",
                "res_model": "mrp.stock.request.allocate.multi.wizard",
                "res_id": wizard.id,
                "target": "new",
            }
        else:
            # Single MO or no specific MO: Use original wizard
            return {
                "name": _("Allocate Materials to MO"),
                "type": "ir.actions.act_window",
                "view_mode": "form",
                "res_model": "mrp.stock.request.allocate.wizard",
                "target": "new",
                "context": {
                    "default_request_id": self.id,
                },
            }

    def action_open_pickings(self):
        """Return action to open related pickings."""
        self.ensure_one()
        pickings = self.picking_ids
        
        if not pickings:
            return

        action = self.env["ir.actions.act_window"]._for_xml_id("stock.action_picking_tree_all")
        
        if len(pickings) == 1:
            action["views"] = [(False, "form")]
            action["res_id"] = pickings.id
        else:
            action["domain"] = [("id", "in", pickings.ids)]
            
        return action

    def action_cancel(self):
        """Cancel the request and create return picking for issued materials."""
        for request in self:
            if request.state == "done":
                raise UserError(_("Cannot cancel a request that is done."))

            # Handle done pickings - create return pickings for issued materials
            done_pickings = request.picking_ids.filtered(lambda p: p.state == "done")
            return_pickings = self.env['stock.picking']
            
            for picking in done_pickings:
                # Check if materials are still available (not allocated)
                unallocated_lines = []
                for line in request.line_ids:
                    if line.qty_available_to_allocate > 0:
                        unallocated_lines.append({
                            'product_id': line.product_id,
                            'qty': line.qty_available_to_allocate,
                            'uom_id': line.uom_id,
                        })
                
                if unallocated_lines:
                    # Create return picking
                    picking_type = request.location_id.warehouse_id.int_type_id or self.env['stock.picking.type'].search([
                        ('code', '=', 'internal'),
                        ('warehouse_id', '=', request.location_id.warehouse_id.id)
                    ], limit=1)
                    
                    return_picking_vals = {
                        'picking_type_id': picking_type.id,
                        'location_id': request.location_dest_id.id,  # From issued location
                        'location_dest_id': request.location_id.id,  # Back to warehouse
                        'origin': _('Return: %s') % request.name,
                        'move_ids': [],
                    }
                    
                    # Create moves for unallocated materials
                    for line_data in unallocated_lines:
                        move_vals = {
                            'name': _('Return: %s') % line_data['product_id'].name,
                            'product_id': line_data['product_id'].id,
                            'product_uom_qty': line_data['qty'],
                            'product_uom': line_data['uom_id'].id,
                            'location_id': request.location_dest_id.id,
                            'location_dest_id': request.location_id.id,
                        }
                        return_picking_vals['move_ids'].append((0, 0, move_vals))
                    
                    if return_picking_vals['move_ids']:
                        return_picking = self.env['stock.picking'].create(return_picking_vals)
                        return_picking.action_confirm()
                        return_pickings |= return_picking

            # Cancel pickings that are not done
            pickings_to_cancel = request.picking_ids.filtered(lambda p: p.state not in ["done", "cancel"])
            if pickings_to_cancel:
                pickings_to_cancel.action_cancel()

            request.write({"state": "cancel"})

            # Post message with return picking info
            message = _("Stock request cancelled.")
            if return_pickings:
                message += _("\n\nReturn picking(s) created: %s") % ", ".join(return_pickings.mapped('name'))
                message += _("\nPlease validate the return picking(s) to return materials to warehouse.")
            
            request.message_post(
                body=message,
                subtype_id=self.env.ref("mail.mt_note").id
            )

    def action_draft(self):
        """Reset to draft state. Cancel request first if needed."""
        for request in self:
            if request.state == "done":
                raise UserError(_("Cannot reset to draft a request that is done."))
            
            # If there are pickings in progress or done, must cancel first
            active_pickings = request.picking_ids.filtered(lambda p: p.state not in ["draft", "cancel"])
            if active_pickings:
                raise UserError(_(
                    "Cannot reset to draft when pickings are in progress or done.\n\n"
                    "Please cancel the request first, which will:\n"
                    "• Cancel pickings in draft/waiting/confirmed state\n"
                    "• Create return pickings for issued materials that haven't been allocated\n\n"
                    "After canceling, you can then reset to draft if needed."
                ))

        self.write({"state": "draft"})


class MrpStockRequestLine(models.Model):
    _name = "mrp.stock.request.line"
    _description = "MRP Stock Request Line"

    request_id = fields.Many2one(
        "mrp.stock.request",
        string="Stock Request",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        domain=[("type", "=", "product")],  # Only storable products
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        required=True,
    )
    qty_requested = fields.Float(
        string="Requested",
        digits="Product Unit of Measure",
        required=True,
        default=1.0,
    )
    qty_issued = fields.Float(
        string="Issued",
        digits="Product Unit of Measure",
        compute="_compute_qty_issued",
        store=True,
    )
    qty_allocated = fields.Float(
        string="Allocated",
        digits="Product Unit of Measure",
        compute="_compute_qty_allocated",
        store=True,
    )
    qty_remaining = fields.Float(
        string="Remaining",
        digits="Product Unit of Measure",
        compute="_compute_qty_remaining",
        store=True,
    )
    qty_available_to_allocate = fields.Float(
        string="Available to Allocate",
        digits="Product Unit of Measure",
        compute="_compute_qty_available_to_allocate",
        store=True,
    )
    move_ids = fields.Many2many(
        "stock.move",
        "mrp_stock_request_line_move_rel",
        "line_id",
        "move_id",
        string="Stock Moves",
        copy=False,
    )
    allocation_ids = fields.One2many(
        "mrp.stock.request.allocation",
        "request_line_id",
        string="Allocations",
        copy=False,
    )

    @api.depends("move_ids.state", "move_ids.product_uom_qty", "move_ids.product_uom")
    def _compute_qty_issued(self):
        """Compute issued quantity from done moves."""
        for line in self:
            qty_issued = 0.0
            done_moves = line.move_ids.filtered(lambda m: m.state == 'done')
            for move in done_moves:
                # Convert move quantity to line UoM
                qty_issued += move.product_uom._compute_quantity(
                    move.product_uom_qty,
                    line.uom_id
                )
            line.qty_issued = qty_issued

    @api.depends("allocation_ids.qty_consumed", "allocation_ids.uom_id")
    def _compute_qty_allocated(self):
        """Compute allocated quantity from allocations."""
        for line in self:
            qty_allocated = 0.0
            for allocation in line.allocation_ids:
                # Convert allocation quantity to line UoM
                qty_allocated += allocation.uom_id._compute_quantity(
                    allocation.qty_consumed,
                    line.uom_id
                )
            line.qty_allocated = qty_allocated

    @api.depends("qty_requested", "qty_issued")
    def _compute_qty_remaining(self):
        """Compute remaining quantity."""
        for line in self:
            remaining = line.qty_requested - line.qty_issued
            # Ensure not negative
            line.qty_remaining = max(remaining, 0.0)

    @api.depends("qty_issued", "qty_allocated")
    def _compute_qty_available_to_allocate(self):
        """Compute available quantity to allocate."""
        for line in self:
            available = line.qty_issued - line.qty_allocated
            # Ensure not negative
            line.qty_available_to_allocate = max(available, 0.0)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id

    @api.constrains("qty_requested")
    def _check_qty_requested(self):
        for line in self:
            if line.qty_requested <= 0:
                raise ValidationError(_("Requested quantity must be positive."))


class MrpStockRequestAllocation(models.Model):
    _name = "mrp.stock.request.allocation"
    _description = "MRP Stock Request Allocation"
    _order = "create_date desc"

    request_line_id = fields.Many2one(
        "mrp.stock.request.line",
        string="Request Line",
        required=True,
        ondelete="cascade",
        index=True,
    )
    request_id = fields.Many2one(
        related="request_line_id.request_id",
        string="Stock Request",
        store=True,
        index=True,
    )
    mo_id = fields.Many2one(
        "mrp.production",
        string="Manufacturing Order",
        required=True,
        ondelete="restrict",
        index=True,
    )
    product_id = fields.Many2one(
        related="request_line_id.product_id",
        string="Product",
        store=True,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        required=True,
    )
    qty_consumed = fields.Float(
        string="Consumed Quantity",
        digits="Product Unit of Measure",
        required=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot/Serial Number",
        ondelete="restrict",
    )
    allocation_date = fields.Datetime(
        string="Allocation Date",
        default=fields.Datetime.now,
        required=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Allocated By",
        default=lambda self: self.env.user,
        required=True,
    )
    notes = fields.Text(string="Notes")