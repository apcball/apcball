
# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class TransitTransferWizardLine(models.TransientModel):
    _name = "transit.transfer.wizard.line"
    _description = "Products to Transfer Line"

    wizard_id = fields.Many2one("transit.transfer.wizard", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Product", required=True)
    product_uom_qty = fields.Float(string="Quantity", default=1.0, required=True)
    product_uom_id = fields.Many2one("uom.uom", string="Unit of Measure", required=True)
    price_unit = fields.Float(string="Unit Price (from PO)", readonly=True)

class TransitTransferWizard(models.TransientModel):
    _name = "transit.transfer.wizard"
    _description = "Create Internal Transfer from Transit"

    picking_id = fields.Many2one("stock.picking", required=True, readonly=True)
    purchase_order_ref = fields.Char(string="Purchase Order Reference", readonly=True)
    source_location_id = fields.Many2one(
        "stock.location", string="From (Transit / No Valuation)", required=True, readonly=True
    )
    dest_location_id = fields.Many2one(
        "stock.location",
        string="To (Warehouse Location)",
        domain="[('usage','in',('internal','production','inventory'))]",
        required=True,
    )
    auto_validate = fields.Boolean(string="Validate Transfer Immediately", default=False)
    create_landed_cost = fields.Boolean(string="Create Landed Cost (draft)", default=False)
    picking_type_id = fields.Many2one("stock.picking.type", string="Operation Type (Internal)")
    line_ids = fields.One2many("transit.transfer.wizard.line", "wizard_id", string="Products to Transfer")
    force_valuation = fields.Boolean(string="Force Valuation (Override Skip Valuation)", default=True, help="Force accounting entries and stock valuation even if locations are set to skip valuation")

    @api.onchange("dest_location_id")
    def _onchange_dest_location_id(self):
        if self.dest_location_id:
            wh = self.env["stock.warehouse"].search(
                [("lot_stock_id", "parent_of", self.dest_location_id.id)], limit=1
            )
            if wh:
                self.picking_type_id = wh.int_type_id

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'stock.picking' and self.env.context.get('active_id'):
            picking = self.env['stock.picking'].browse(self.env.context['active_id'])
            res['picking_id'] = picking.id
            res['purchase_order_ref'] = picking.origin or "N/A"
            
            # Try to find Purchase Order for pricing
            purchase_order = None
            if picking.origin:
                purchase_order = self.env['purchase.order'].search([('name', '=', picking.origin)], limit=1)
            
            # Auto-populate products from source picking
            lines = []
            for move in picking.move_ids:
                if move.product_id.type == "product" and move.state == "done":
                    qty = getattr(move, 'product_uom_qty', 1.0) or 1.0
                    
                    # Get price from PO if available
                    price_unit = 0.0
                    if purchase_order:
                        po_line = purchase_order.order_line.filtered(lambda l: l.product_id == move.product_id)
                        if po_line:
                            price_unit = po_line[0].price_unit
                    
                    lines.append((0, 0, {
                        'product_id': move.product_id.id,
                        'product_uom_qty': qty,
                        'product_uom_id': move.product_uom.id,
                        'price_unit': price_unit,
                    }))
            res['line_ids'] = lines
        return res

    def action_create_transfer(self):
        self.ensure_one()
        picking = self.picking_id.sudo()
        if picking.state != "done":
            raise UserError(_("The receipt must be done."))

        if self.source_location_id.usage != "transit" and not self.source_location_id.skip_valuation:
            raise UserError(_("Source location must be Transit or a location set to 'No Valuation'."))

        picking_type = self.picking_type_id
        if not picking_type:
            wh = self.env["stock.warehouse"].search(
                [("lot_stock_id", "parent_of", self.dest_location_id.id)], limit=1
            )
            if not wh:
                raise UserError(_("Cannot find warehouse for destination location."))
            picking_type = wh.int_type_id

        # Use PO number as origin for smart button linking
        po_origin = picking.origin if picking.origin else picking.name
        
        # Try to find the related Purchase Order for better integration
        purchase_order = None
        if picking.origin:
            purchase_order = self.env['purchase.order'].search([('name', '=', picking.origin)], limit=1)
        
        new_picking_vals = {
            "picking_type_id": picking_type.id,
            "location_id": self.source_location_id.id,
            "location_dest_id": self.dest_location_id.id,
            "origin": po_origin,  # Use PO number directly for smart button linking
            "move_type": "direct",
        }
        
        # If we found a purchase order, link it properly
        if purchase_order:
            new_picking_vals.update({
                "origin": purchase_order.name,
                "partner_id": purchase_order.partner_id.id if purchase_order.partner_id else picking.partner_id.id,
                "group_id": picking.group_id.id if picking.group_id else False,
            })
        new_picking = self.env["stock.picking"].create(new_picking_vals)

        moves_vals = []
        # Use wizard lines instead of trying to read from source picking
        for line in self.line_ids:
            if line.product_id.type != "product":
                continue
            qty = line.product_uom_qty or 1.0
            if qty <= 0:
                continue
            
            # Use the same origin as the picking for consistency
            origin_ref = new_picking_vals["origin"]
            
            # Use price from wizard line (which was populated from PO)
            price_unit = line.price_unit or 0.0
            
            # If still no price, try to get from Purchase Order
            if not price_unit and purchase_order:
                po_line = purchase_order.order_line.filtered(lambda l: l.product_id == line.product_id)
                if po_line:
                    price_unit = po_line[0].price_unit
                    
            moves_vals.append({
                "name": line.product_id.display_name,
                "product_id": line.product_id.id,
                "product_uom": line.product_uom_id.id,
                "product_uom_qty": qty,
                "price_unit": price_unit,  # Set price from wizard line or PO
                "picking_id": new_picking.id,
                "location_id": self.source_location_id.id,
                "location_dest_id": self.dest_location_id.id,
                "origin": origin_ref,
                "company_id": picking.company_id.id,
                "state": "draft",
            })
            
            # If we have a purchase order, link the move to it as well
            if purchase_order:
                po_line = purchase_order.order_line.filtered(lambda l: l.product_id == line.product_id)
                if po_line:
                    moves_vals[-1].update({
                        "purchase_line_id": po_line[0].id,  # Link to specific PO line
                    })
        if not moves_vals:
            raise UserError(_("No products to transfer. Please add products in the lines below."))

        # Create moves with context if force_valuation is enabled
        if self.force_valuation:
            moves = self.env["stock.move"].with_context(force_valuation=True).create(moves_vals)
        else:
            moves = self.env["stock.move"].create(moves_vals)
        
        # If force_valuation is enabled, ensure context is passed to all operations
        context_updates = {}
        if self.force_valuation:
            context_updates['force_valuation'] = True
            # Apply context to picking and moves
            new_picking = new_picking.with_context(**context_updates)
            moves = moves.with_context(**context_updates)
            # Also update the environment context for all subsequent operations
            self = self.with_context(**context_updates)
        
        # Try to confirm and assign step by step with error handling
        try:
            new_picking.action_confirm()
        except Exception as e:
            raise UserError(_("Cannot confirm picking: %s") % str(e))
        
        try:
            new_picking.action_assign()
        except Exception as e:
            # If assignment fails, try to force availability
            for move in new_picking.move_ids:
                move._set_quantity_done(move.product_uom_qty)
        if self.auto_validate:
            try:
                # Force set quantities done for validation
                for move in new_picking.move_ids:
                    # Apply context to each move if force_valuation is enabled
                    if self.force_valuation:
                        move = move.with_context(**context_updates)
                    
                    if hasattr(move, '_set_quantity_done'):
                        move._set_quantity_done(move.product_uom_qty)
                    else:
                        # Alternative method for setting quantities
                        for move_line in move.move_line_ids:
                            if hasattr(move_line, 'qty_done'):
                                move_line.qty_done = move_line.reserved_qty or move_line.product_uom_qty
                            elif hasattr(move_line, 'quantity'):
                                move_line.quantity = move_line.reserved_qty or move_line.product_uom_qty
                
                # Validate with context if force_valuation is enabled
                if self.force_valuation:
                    new_picking = new_picking.with_context(**context_updates)
                new_picking.button_validate()
            except Exception as e:
                # If validation fails, just leave it unvalidated
                _logger.warning("Validation failed: %s", e)
                pass
        else:
            # Just leave as draft for manual validation
            _logger.info("[tqt] Transfer created as draft - manual validation required")

        if self.create_landed_cost:
            self.env["stock.landed.cost"].create({
                "picking_ids": [(6, 0, [new_picking.id])],
                "company_id": picking.company_id.id,
            })
        
        # Return action to view the created picking
        return {
            'type': 'ir.actions.act_window',
            'name': 'Internal Transfer',
            'res_model': 'stock.picking',
            'res_id': new_picking.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def api_create_transfer(self, picking_vals, move_lines, force_valuation=True, auto_validate=False):
        """Create a transfer from external API-like data.

        picking_vals: dict with keys suitable for stock.picking create (picking_type_id, location_id, location_dest_id, origin, partner_id, date fields)
        move_lines: list of dicts each with product_id, product_uom, product_uom_qty, optional price_unit and purchase_line_id
        force_valuation: bool - if True will force valuation even if locations skip valuation
        auto_validate: bool - if True will attempt to validate the picking automatically

        Returns: dict with 'picking_id' and created 'move_ids'
        """
        # Create picking
        Picking = self.env['stock.picking']
        Move = self.env['stock.move']
        if force_valuation:
            Picking = Picking.with_context(force_valuation=True)
            Move = Move.with_context(force_valuation=True)

        picking = Picking.create(picking_vals)

        created_move_ids = []
        for ml in move_lines:
            mv = {
                'name': ml.get('name') or 'API Transfer',
                'product_id': ml['product_id'],
                'product_uom': ml['product_uom'],
                'product_uom_qty': ml['product_uom_qty'],
                'picking_id': picking.id,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
            }
            # optional fields
            if 'price_unit' in ml and ml.get('price_unit') is not None:
                mv['price_unit'] = float(ml['price_unit'])
            if 'purchase_line_id' in ml and ml.get('purchase_line_id'):
                mv['purchase_line_id'] = int(ml['purchase_line_id'])

            move = Move.create(mv)
            created_move_ids.append(move.id)

        # Confirm picking
        try:
            picking.with_context(force_valuation=bool(force_valuation)).action_confirm()
        except Exception as e:
            # propagate error to caller
            _logger.error('api_create_transfer: cannot confirm picking %s: %s', picking.id, e)
            raise

        # Try to assign / set done qty if auto_validate requested
        if auto_validate:
            try:
                # set quantities done
                for move in picking.move_ids:
                    if hasattr(move, '_set_quantity_done'):
                        move.with_context(force_valuation=bool(force_valuation))._set_quantity_done(move.product_uom_qty)
                    else:
                        for ml in move.move_line_ids:
                            if hasattr(ml, 'qty_done'):
                                ml.qty_done = ml.reserved_qty or ml.product_uom_qty
                # validate
                picking.with_context(force_valuation=bool(force_valuation)).button_validate()
            except Exception as e:
                _logger.warning('api_create_transfer: auto-validate failed for picking %s: %s', picking.id, e)

        # Ensure valuation layers / accounting entries exist for moves (best-effort)
        try:
            for move in self.env['stock.move'].browse(created_move_ids):
                # Only try for done moves
                if move.state != 'done':
                    continue
                # If there is no SVL, try to create it manually
                svl = self.env['stock.valuation.layer'].search([('stock_move_id', '=', move.id)], limit=1)
                if not svl:
                    try:
                        if move._is_in():
                            move.with_context(force_valuation=bool(force_valuation))._create_in_svl()
                        elif move._is_out():
                            move.with_context(force_valuation=bool(force_valuation))._create_out_svl()
                        else:
                            move.with_context(force_valuation=bool(force_valuation))._create_valuation_layers()
                    except Exception as e:
                        _logger.error('api_create_transfer: manual SVL creation failed for move %s: %s', move.id, e)
        except Exception:
            # ignore best-effort failures
            pass

        return {'picking_id': picking.id, 'move_ids': created_move_ids}
