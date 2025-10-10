from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    mrp_stock_request_count = fields.Integer(
        string="Stock Request Count",
        compute="_compute_mrp_stock_request_count",
    )

    def _compute_mrp_stock_request_count(self):
        for mo in self:
            mo.mrp_stock_request_count = self.env["mrp.stock.request"].search_count([
                ("production_id", "=", mo.id)
            ])

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
        stock_requests = self.env["mrp.stock.request"].search([
            ("production_id", "=", self.id)
        ])
        # Show existing stock requests
        if len(stock_requests) > 1:
            result["domain"] = [("id", "in", stock_requests.ids)]
        elif len(stock_requests) == 1:
            res = self.env.ref("buz_mrp_stock_request.view_mrp_stock_request_form", False)
            result["views"] = [(res and res.id or False, "form")]
            result["res_id"] = stock_requests.id
        else:
            # If no stock requests exist, create a new one
            result["context"] = {
                "default_production_id": self.id,
                "default_company_id": self.company_id.id,
                "default_source_location_id": self.location_src_id.id,
                "default_dest_location_id": self.location_dest_id.id,
            }
        return result


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

    def write(self, vals):
        """Update request state when picking state changes."""
        res = super().write(vals)
        
        # If the picking state has changed, update related stock request
        if "state" in vals:
            for picking in self:
                if picking.stock_request_id:
                    stock_request = picking.stock_request_id
                    if vals["state"] == "done":
                        stock_request.write({"state": "done"})
                    elif vals["state"] == "cancel":
                        stock_request.write({"state": "cancel"})
        
        return res


class MrpStockRequest(models.Model):
    _name = "mrp.stock.request"
    _description = "MRP Stock Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name desc"

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _("New"),
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    production_id = fields.Many2one(
        "mrp.production",
        string="Manufacturing Order",
        required=True,
        domain="[('company_id', '=', company_id)]",
        index=True,
        tracking=True,
    )
    request_line_ids = fields.One2many(
        "mrp.stock.request.line",
        "request_id",
        string="Request Lines",
        copy=True,
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="Internal Transfer",
        readonly=True,
        copy=False,
    )
    source_location_id = fields.Many2one(
        "stock.location",
        string="Source Location",
        required=True,
        domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]",
    )
    dest_location_id = fields.Many2one(
        "stock.location",
        string="Destination Location",
        required=True,
        domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]",
    )
    requested_by = fields.Many2one(
        "res.users",
        string="Requested By",
        default=lambda self: self.env.user,
        required=True,
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
    note = fields.Text(string="Notes")
    picking_state = fields.Char(
        string="Transfer Status",
        compute="_compute_picking_state",
        store=False,
    )

    @api.depends("picking_id.state")
    def _compute_picking_state(self):
        for request in self:
            if request.picking_id:
                request.picking_state = request.picking_id.state
            else:
                request.picking_state = False

    @api.constrains("request_line_ids", "source_location_id", "dest_location_id")
    def _check_request_lines(self):
        for request in self:
            if request.state in ["draft", "requested"]:
                for line in request.request_line_ids:
                    if line.product_qty <= 0:
                        raise ValidationError(
                            _("Quantity must be positive for product %s")
                            % line.product_id.name
                        )
                if not request.source_location_id:
                    raise ValidationError(_("Source location is required."))
                if not request.dest_location_id:
                    raise ValidationError(_("Destination location is required."))
                # Check company consistency
                if request.production_id.company_id != request.company_id:
                    raise ValidationError(
                        _("Company of the request should match company of the MO.")
                    )

    @api.model
    def create(self, vals):
        if vals.get("name", _("New")) == _("New"):
            vals["name"] = self.env["ir.sequence"].next_by_code("mrp.stock.request") or _("New")
        return super().create(vals)

    def action_prepare_from_mo(self):
        """Prefill lines from MO components that are short/needed."""
        self.ensure_one()
        if not self.production_id:
            return

        # Clear existing lines
        self.request_line_ids.unlink()

        # Get the components required for the MO
        for move in self.production_id.move_raw_ids:
            # Check if we have enough available quantity at destination location
            if move.product_id.type != "product":  # Skip service/digital products
                continue

            # Calculate required quantity that is short
            required_qty = move.product_uom_qty
            # virtual_available at destination location
            virtual_available = move.product_id.with_context(
                location=self.dest_location_id.id
            ).virtual_available

            # Calculate forecasted quantity (available + incoming)
            forecasted_qty = move.product_id.with_context(
                location=self.dest_location_id.id
            ).qty_available + move.product_id.with_context(
                location=self.dest_location_id.id
            ).incoming_qty

            # If virtual_available is less than required, propose the delta
            needed_qty = max(0, required_qty - forecasted_qty)
            
            # If needed quantity is greater than 0, add a line
            if needed_qty > 0:
                self.env["mrp.stock.request.line"].create({
                    "request_id": self.id,
                    "product_id": move.product_id.id,
                    "product_uom": move.product_uom.id,
                    "product_qty": needed_qty,
                    "description": move.product_id.display_name or move.product_id.name,
                })
            elif required_qty > 0:
                # If we have enough available, still add the line but with 0 qty
                # so user can adjust if needed
                self.env["mrp.stock.request.line"].create({
                    "request_id": self.id,
                    "product_id": move.product_id.id,
                    "product_uom": move.product_uom.id,
                    "product_qty": required_qty,
                    "description": move.product_id.display_name or move.product_id.name,
                })

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
        stock_requests = self.env["mrp.stock.request"].search([
            ("production_id", "=", self.id)
        ])
        # Show existing stock requests
        if len(stock_requests) > 1:
            result["domain"] = [("id", "in", stock_requests.ids)]
        elif len(stock_requests) == 1:
            res = self.env.ref("buz_mrp_stock_request.view_mrp_stock_request_form", False)
            result["views"] = [(res and res.id or False, "form")]
            result["res_id"] = stock_requests.id
        else:
            # If no stock requests exist, create a new one
            result["context"] = {
                "default_production_id": self.id,
                "default_company_id": self.company_id.id,
                "default_source_location_id": self.location_src_id.id,
                "default_dest_location_id": self.location_dest_id.id,
            }
        return result

    def action_confirm(self):
        """Create internal transfer from request lines."""
        for request in self:
            if request.state != "draft":
                raise UserError(_("Only draft requests can be confirmed."))

            # Validate request lines
            if not request.request_line_ids:
                raise UserError(_("Cannot confirm request without lines."))

            # Check if source and dest locations are set
            if not request.source_location_id or not request.dest_location_id:
                raise UserError(_("Source and destination locations are required."))

            # Create the picking
            picking_type = request.production_id.picking_type_id or request.env["stock.picking.type"].search([
                ("code", "=", "internal"),
                ("warehouse_id", "=", request.production_id.warehouse_id.id),
                ("company_id", "=", request.company_id.id),
            ], limit=1)

            if not picking_type:
                picking_type = request.env["stock.picking.type"].search([
                    ("code", "=", "internal"),
                    ("company_id", "=", request.company_id.id),
                ], limit=1)
                if not picking_type:
                    raise UserError(_("No internal picking type found for this company."))

            picking_vals = {
                "picking_type_id": picking_type.id,
                "location_id": request.source_location_id.id,
                "location_dest_id": request.dest_location_id.id,
                "origin": request.name,
                "company_id": request.company_id.id,
                "note": request.note or "",
            }

            picking = request.env["stock.picking"].create(picking_vals)

            # Create move lines for each request line
            for line in request.request_line_ids:
                if line.product_qty > 0:
                    request.env["stock.move"].create({
                        "name": line.product_id.name,
                        "product_id": line.product_id.id,
                        "product_uom_qty": line.product_qty,
                        "product_uom": line.product_uom.id,
                        "picking_id": picking.id,
                        "location_id": request.source_location_id.id,
                        "location_dest_id": request.dest_location_id.id,
                        "company_id": request.company_id.id,
                        "origin": request.name,
                    })

            # Update request state and link to picking
            request.write({
                "picking_id": picking.id,
                "state": "requested",
            })

            # Link back from picking to request
            picking.write({
                "stock_request_id": request.id
            })

            # Log in chatter
            request.message_post(
                body=_("Internal transfer %s has been created.") % (
                    "<a href=# data-oe-model=stock.picking data-oe-id=%d>%s</a>" % (
                        picking.id, picking.name
                    )
                ),
                subtype_id=self.env.ref("mail.mt_note").id
            )

            # Confirm the picking
            if picking.state == "draft":
                picking.action_confirm()
                
    def action_open_picking(self):
        """Return action to open the related picking."""
        self.ensure_one()
        if not self.picking_id:
            return

        return {
            "name": _("Internal Transfer"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "stock.picking",
            "res_id": self.picking_id.id,
            "target": "current",
        }

    def action_cancel(self):
        """Cancel the request and related picking if not done."""
        for request in self:
            if request.state == "done":
                raise UserError(_("Cannot cancel a request that is done."))
            
            if request.picking_id:
                if request.picking_id.state == "done":
                    raise UserError(_("Cannot cancel request because the transfer is already done."))
                elif request.picking_id.state not in ["cancel"]:
                    request.picking_id.action_cancel()
            
            request.write({"state": "cancel"})

    def action_draft(self):
        """Reset to draft state."""
        if any(request.state == "done" for request in self):
            raise UserError(_("Cannot reset to draft a request that is done."))
        
        self.write({"state": "draft"})


class MrpStockRequestLine(models.Model):
    _name = "mrp.stock.request.line"
    _description = "MRP Stock Request Line"

    request_id = fields.Many2one(
        "mrp.stock.request",
        string="Stock Request",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        domain=[("type", "=", "product")],  # Only storable products
    )
    product_uom = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        required=True,
    )
    product_qty = fields.Float(
        string="Quantity",
        digits="Product Unit of Measure",
        required=True,
        default=1.0,
    )
    description = fields.Char(string="Description")

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom = self.product_id.uom_id

    @api.constrains("product_qty")
    def _check_product_qty(self):
        for line in self:
            if line.product_qty <= 0:
                raise ValidationError(_("Quantity must be positive."))