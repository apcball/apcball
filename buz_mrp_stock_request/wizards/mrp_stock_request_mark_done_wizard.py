# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_round, float_is_zero


class MrpStockRequestMarkDoneWizard(models.TransientModel):
    _name = "mrp.stock.request.mark.done.wizard"
    _description = "Mark Stock Request as Done - Transfer Unallocated Materials"

    request_id = fields.Many2one(
        "mrp.stock.request",
        string="Stock Request",
        required=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        "mrp.stock.request.mark.done.wizard.line",
        "wizard_id",
        string="Materials to Transfer",
    )
    summary_html = fields.Html(
        string="Summary",
        compute="_compute_summary_html",
    )
    has_unallocated = fields.Boolean(
        string="Has Unallocated Materials",
        compute="_compute_has_unallocated",
    )
    company_id = fields.Many2one(
        related="request_id.company_id",
        string="Company",
    )

    @api.depends("request_id", "line_ids")
    def _compute_summary_html(self):
        """Generate HTML summary of materials to be transferred."""
        for wizard in self:
            if not wizard.request_id:
                wizard.summary_html = ""
                continue

            total_qty = sum(line.qty_to_transfer for line in wizard.line_ids)
            total_products = len(wizard.line_ids)

            # Build summary lines
            summary_lines = []
            for line in wizard.line_ids:
                summary_lines.append(
                    "<tr>"
                    "<td>%s</td>"
                    "<td class='text-right'>%.2f</td>"
                    "<td>%s</td>"
                    "</tr>" % (
                        line.product_id.display_name,
                        line.qty_to_transfer,
                        line.uom_id.name,
                    )
                )

            # Create HTML table
            table_html = ""
            if summary_lines:
                table_html = """
                <table class='table table-sm table-striped'>
                    <thead>
                        <tr>
                            <th>Product</th>
                            <th class='text-right'>Quantity</th>
                            <th>UoM</th>
                        </tr>
                    </thead>
                    <tbody>
                        %s
                    </tbody>
                </table>
                """ % "".join(summary_lines)

            wizard.summary_html = _(
                """
                <div class='alert alert-warning'>
                    <h4><i class='fa fa-exclamation-triangle'/> Warning</h4>
                    <p>This action will:</p>
                    <ul>
                        <li>Transfer <strong>%d</strong> material(s) (total: <strong>%.2f</strong> units)</li>
                        <li>From: <strong>%s</strong></li>
                        <li>To: <strong>%s</strong></li>
                        <li>Mark the stock request as <strong>Done</strong></li>
                    </ul>
                    <p><strong>This action cannot be undone.</strong></p>
                </div>
                %s
                """ % (
                    total_products,
                    total_qty,
                    wizard.request_id.location_id.name,
                    wizard.request_id.location_dest_id.name,
                    table_html,
                )
            )

    @api.depends("request_id")
    def _compute_has_unallocated(self):
        """Check if there are unallocated materials."""
        for wizard in self:
            if not wizard.request_id:
                wizard.has_unallocated = False
                continue

            wizard.has_unallocated = any(
                float_compare(
                    line.qty_available_to_allocate,
                    0.0,
                    precision_rounding=line.uom_id.rounding
                ) > 0
                for line in wizard.request_id.line_ids
            )

    @api.model
    def default_get(self, fields_list):
        """Populate wizard with unallocated materials from stock request."""
        res = super().default_get(fields_list)
        
        request_id = self.env.context.get('default_request_id')
        if request_id:
            request = self.env['mrp.stock.request'].browse(request_id)
            res['request_id'] = request_id
            
            # Create wizard lines for unallocated materials
            wizard_lines = []
            for req_line in request.line_ids:
                if float_compare(
                    req_line.qty_available_to_allocate,
                    0.0,
                    precision_rounding=req_line.uom_id.rounding
                ) > 0:
                    wizard_lines.append((0, 0, {
                        'request_line_id': req_line.id,
                        'product_id': req_line.product_id.id,
                        'uom_id': req_line.uom_id.id,
                        'qty_to_transfer': req_line.qty_available_to_allocate,
                    }))
            
            if wizard_lines:
                res['line_ids'] = wizard_lines
                
        return res

    def action_confirm(self):
        """Create transfer and mark request as done."""
        self.ensure_one()
        
        if not self.line_ids:
            raise UserError(_("No materials to transfer."))
        
        # Validate lines
        self._validate_lines()
        
        # Create stock transfer
        picking = self._create_transfer_picking()
        
        # Mark request as done
        self.request_id.write({"state": "done"})
        
        # Log in chatter
        self._log_action(picking)
        
        # Show success message and close
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _(
                    'Transfer %s created and stock request marked as Done.\n'
                    '%d material(s) transferred automatically.'
                ) % (picking.name, len(self.line_ids)),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    def _validate_lines(self):
        """Validate wizard lines before processing."""
        for line in self.line_ids:
            if line.qty_to_transfer <= 0:
                raise ValidationError(
                    _("Quantity must be positive for product %s.") % line.product_id.name
                )
            
            # Check against available quantity
            if float_compare(
                line.qty_to_transfer,
                line.request_line_id.qty_available_to_allocate,
                precision_rounding=line.uom_id.rounding
            ) > 0:
                raise ValidationError(
                    _("Transfer quantity (%.2f) exceeds available quantity (%.2f) for product %s.") % (
                        line.qty_to_transfer,
                        line.request_line_id.qty_available_to_allocate,
                        line.product_id.name,
                    )
                )

    def _create_transfer_picking(self):
        """Create a stock picking for unallocated materials."""
        request = self.request_id
        
        # Create picking
        picking_vals = {
            'picking_type_id': request.picking_type_id.id,
            'location_id': request.location_id.id,
            'location_dest_id': request.location_dest_id.id,
            'origin': _('Auto-transfer: %s') % request.name,
            'company_id': request.company_id.id,
            'note': _('Automatic transfer of unallocated materials when marking request as Done'),
        }
        
        picking = self.env['stock.picking'].create(picking_vals)
        
        # Create moves for each line
        for line in self.line_ids:
            move_vals = {
                'name': line.product_id.display_name or line.product_id.name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty_to_transfer,
                'product_uom': line.uom_id.id,
                'picking_id': picking.id,
                'location_id': request.location_id.id,
                'location_dest_id': request.location_dest_id.id,
                'company_id': request.company_id.id,
                'origin': picking.origin,
            }
            move = self.env['stock.move'].create(move_vals)
            
            # Link move to request line for traceability
            line.request_line_id.write({'move_ids': [(4, move.id)]})
        
        # Confirm and validate picking
        picking.action_confirm()
        picking.action_assign()
        
        # Create move lines and validate
        for move in picking.move_ids:
            # For simplicity, create move lines without lot tracking
            # In production, you might need lot selection logic
            if move.state == 'assigned':
                for move_line in move.move_line_ids:
                    move_line.qty_done = move_line.product_uom_qty
            else:
                # Create move line manually if not assigned
                move_line_vals = {
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'quantity': move.product_uom_qty,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'company_id': move.company_id.id,
                }
                self.env['stock.move.line'].create(move_line_vals)
        
        # Validate the picking
        picking._action_done()
        
        return picking

    def _log_action(self, picking):
        """Log the action in chatter."""
        request = self.request_id
        
        # Build material list for message
        material_lines = []
        for line in self.line_ids:
            material_lines.append(
                "• %.2f %s of %s" % (
                    line.qty_to_transfer,
                    line.uom_id.name,
                    line.product_id.display_name,
                )
            )
        
        # Log in request chatter
        request.message_post(
            body=_(
                "Stock request marked as Done.<br/><br/>"
                "<strong>Automatic Transfer Created:</strong> %s<br/>"
                "<strong>Materials Transferred:</strong><br/>%s"
            ) % (
                "<a href=# data-oe-model=stock.picking data-oe-id=%d>%s</a>" % (
                    picking.id, picking.name
                ),
                "<br/>".join(material_lines),
            ),
            subtype_id=self.env.ref("mail.mt_note").id
        )


class MrpStockRequestMarkDoneWizardLine(models.TransientModel):
    _name = "mrp.stock.request.mark.done.wizard.line"
    _description = "Mark Done Wizard Line - Material to Transfer"

    wizard_id = fields.Many2one(
        "mrp.stock.request.mark.done.wizard",
        string="Wizard",
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
        string="Unit of Measure",
        required=True,
        readonly=True,
    )
    qty_to_transfer = fields.Float(
        string="Quantity to Transfer",
        digits="Product Unit of Measure",
        required=True,
        readonly=True,
    )
    available_qty = fields.Float(
        string="Available Quantity",
        digits="Product Unit of Measure",
        readonly=True,
    )