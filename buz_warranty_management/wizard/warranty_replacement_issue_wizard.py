from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WarrantyReplacementIssueWizard(models.TransientModel):
    _name = 'warranty.replacement.issue.wizard'
    _description = 'Warranty Replacement Issue Wizard'

    claim_id = fields.Many2one(
        'warranty.claim',
        string='Warranty Claim',
        required=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True
    )
    is_under_warranty = fields.Boolean(
        related='claim_id.is_under_warranty',
        string='Under Warranty'
    )
    line_ids = fields.One2many(
        'warranty.replacement.issue.line',
        'wizard_id',
        string='Replacement Lines'
    )
    picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Picking Type',
        required=True
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Source Location',
        required=True,
        domain="[('usage', '=', 'internal')]"
    )
    create_sale_order = fields.Boolean(
        string='Create Sale Order',
        help='Create SO for portal tracking (zero price for under-warranty)'
    )
    notes = fields.Text(string='Notes')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ICP = self.env['ir.config_parameter'].sudo()
        
        picking_type_id = ICP.get_param('buz_warranty_management.warranty_replacement_out_picking_type_id')
        if picking_type_id:
            res['picking_type_id'] = int(picking_type_id)
        
        location_id = ICP.get_param('buz_warranty_management.warranty_repair_location_id')
        if location_id:
            res['location_id'] = int(location_id)
        
        # Load claim lines as replacement lines
        if 'claim_id' in self._context:
            claim = self.env['warranty.claim'].browse(self._context['claim_id'])
            lines = []
            for claim_line in claim.claim_line_ids.filtered(lambda l: l.need_replacement):
                lines.append((0, 0, {
                    'product_id': claim_line.product_id.id,
                    'qty': claim_line.qty,
                    'lot_id': claim_line.lot_id.id,
                    'unit_price': 0.0 if claim.is_under_warranty else claim_line.unit_price,
                }))
            if lines:
                res['line_ids'] = lines
        
        return res

    def action_issue_replacement(self):
        self.ensure_one()
        
        if not self.picking_type_id:
            raise UserError(_('Please configure Replacement OUT Picking Type in Warranty settings.'))
        
        if not self.location_id:
            raise UserError(_('Please configure Repair Location in Warranty settings.'))
        
        if not self.line_ids:
            raise UserError(_('Please add at least one replacement line.'))
        
        # Get customer location
        customer_location = self.partner_id.property_stock_customer
        
        # Create sale order if requested
        sale_order = None
        if self.create_sale_order:
            sale_order = self._create_sale_order()
        
        # Create picking
        picking_vals = {
            'partner_id': self.partner_id.id,
            'picking_type_id': self.picking_type_id.id,
            'location_id': self.location_id.id,
            'location_dest_id': customer_location.id,
            'origin': self.claim_id.name,
            'note': self.notes,
        }
        
        if sale_order:
            picking_vals['sale_id'] = sale_order.id
        
        picking = self.env['stock.picking'].create(picking_vals)
        
        # Create moves
        for line in self.line_ids:
            move_vals = {
                'name': f'Replacement: {line.product_id.name}',
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
                'product_uom': line.product_id.uom_id.id,
                'picking_id': picking.id,
                'location_id': self.location_id.id,
                'location_dest_id': customer_location.id,
            }
            
            if line.lot_id:
                move_vals['lot_ids'] = [(6, 0, [line.lot_id.id])]
            
            move = self.env['stock.move'].create(move_vals)
            
            # Link to claim lines
            claim_lines = self.claim_id.claim_line_ids.filtered(
                lambda l: l.product_id == line.product_id and l.need_replacement
            )
            if claim_lines:
                claim_lines[0].write({'move_ids': [(4, move.id)]})
        
        # Link picking to claim
        self.claim_id.write({
            'replacement_out_picking_ids': [(4, picking.id)],
            'status': 'ready_to_issue'
        })
        
        # Post message
        msg = _('Replacement OUT picking created: %s', picking.name)
        if sale_order:
            msg += _('<br/>Sale Order: %s', sale_order.name)
        self.claim_id.message_post(body=msg, subject=_('Replacement Issued'))
        
        return {
            'name': _('Replacement Picking'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_sale_order(self):
        """Create SO for replacement tracking"""
        order_vals = {
            'partner_id': self.partner_id.id,
            'origin': self.claim_id.name,
            'note': f'Warranty Replacement - {self.claim_id.name}',
        }
        
        order = self.env['sale.order'].create(order_vals)
        
        for line in self.line_ids:
            self.env['sale.order.line'].create({
                'order_id': order.id,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
                'price_unit': line.unit_price,
            })
        
        if not self.is_under_warranty:
            self.claim_id.write({'quotation_id': order.id})
        
        return order


class WarrantyReplacementIssueLine(models.TransientModel):
    _name = 'warranty.replacement.issue.line'
    _description = 'Warranty Replacement Issue Line'

    wizard_id = fields.Many2one(
        'warranty.replacement.issue.wizard',
        required=True,
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True
    )
    qty = fields.Float(
        string='Quantity',
        default=1.0,
        required=True
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lot/Serial Number',
        domain="[('product_id', '=', product_id)]"
    )
    unit_price = fields.Monetary(
        string='Unit Price',
        currency_field='currency_id'
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )
