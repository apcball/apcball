# Part of buz_warranty_rma_management Odoo module.
# See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime


class BuzWarrantyClaim(models.Model):
    _name = 'buz.warranty.claim'
    _description = 'Warranty Claim'
    _order = 'name desc'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Claim Reference',
        required=True,
        readonly=True,
        default=lambda self: _('New'),
        copy=False
    )
    contract_id = fields.Many2one(
        'buz.warranty.contract',
        string='Warranty Contract',
        required=True,
        domain="[('state', '=', 'active')]"
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lot/Serial Number',
        required=True
    )
    start_date = fields.Date(
        string='Warranty Start Date',
        related='contract_id.start_date',
        readonly=True
    )
    end_date = fields.Date(
        string='Warranty End Date',
        related='contract_id.end_date',
        readonly=True
    )
    reason = fields.Selection([
        ('defect', 'Manufacturing Defect'),
        ('repair', 'Repair Needed'),
        ('replacement', 'Product Replacement'),
        ('refund', 'Refund Request'),
        ('others', 'Other')
    ], string='Reason for Claim', required=True)
    description = fields.Text(
        string='Description',
        required=True
    )
    manager_note = fields.Text(
        string='Manager Notes'
    )
    is_in_warranty = fields.Boolean(
        string='In Warranty',
        compute='_compute_is_in_warranty',
        store=True
    )
    
    # RMA/Logistics references
    rma_in_picking_id = fields.Many2one(
        'stock.picking',
        string='RMA Inbound Picking'
    )
    repair_id = fields.Many2one(
        'repair.order',
        string='Repair Order'
    )
    replacement_out_picking_id = fields.Many2one(
        'stock.picking',
        string='Replacement Outbound Picking'
    )
    return_to_customer_picking_id = fields.Many2one(
        'stock.picking',
        string='Return to Customer Picking'
    )
    
    # Billing
    claim_cost_line_ids = fields.One2many(
        'buz.claim.cost.line',
        'claim_id',
        string='Claim Cost Lines'
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice'
    )
    
    # State
    state = fields.Selection([
        ('draft', 'Draft'),
        ('under_review', 'Under Review'),
        ('rma_in', 'RMA In'),
        ('repairing', 'Repairing'),
        ('replacing', 'Replacing'),
        ('ready_to_return', 'Ready to Return'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string='Status', default='draft', required=True)
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    @api.depends('contract_id.end_date')
    def _compute_is_in_warranty(self):
        today = fields.Date.context_today(self)
        for claim in self:
            if claim.contract_id:
                claim.is_in_warranty = claim.contract_id.end_date >= today
            else:
                claim.is_in_warranty = False

    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        """Auto-fill partner_id, product_id, and lot_id from contract"""
        if self.contract_id:
            self.partner_id = self.contract_id.partner_id
            self.product_id = self.contract_id.product_id
            self.lot_id = self.contract_id.lot_id

    def action_submit(self):
        """Submit the claim - change state to under review"""
        for claim in self:
            claim.state = 'under_review'
        return True

    def action_receive_rma(self):
        """Create Incoming Picking for RMA"""
        picking_type_obj = self.env['stock.picking.type']
        picking_obj = self.env['stock.picking']
        move_obj = self.env['stock.move']
        
        for claim in self:
            if claim.state != 'under_review':
                raise UserError(_("Claim must be under review to receive RMA."))
            
            # Get the RMA inbound picking type from settings
            picking_type_id = self.env['ir.config_parameter'].sudo().get_param(
                'buz.default_rma_in_type_id'
            )
            if not picking_type_id:
                raise UserError(_("Default RMA inbound picking type is not configured in settings."))
            
            picking_type = picking_type_obj.browse(int(picking_type_id))
            if not picking_type.exists():
                raise UserError(_("Configured RMA inbound picking type does not exist."))
            
            # Create the incoming picking
            picking_vals = {
                'partner_id': claim.partner_id.id,
                'picking_type_id': picking_type.id,
                'location_id': picking_type.default_location_src_id.id or self.env.ref('stock.stock_location_suppliers').id,
                'location_dest_id': picking_type.default_location_dest_id.id or self.env.ref('stock.stock_location_stock').id,
                'origin': claim.name,
                'buz_claim_id': claim.id,
            }
            
            picking = picking_obj.create(picking_vals)
            
            # Create stock move for the product
            move_vals = {
                'name': claim.product_id.name,
                'product_id': claim.product_id.id,
                'product_uom_qty': 1,
                'product_uom': claim.product_id.uom_id.id,
                'picking_id': picking.id,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
                'description_picking': claim.description,
            }
            
            move = move_obj.create(move_vals)
            # Apply the lot to the move
            if claim.lot_id:
                move.move_line_ids.write({
                    'lot_ids': [(6, 0, [claim.lot_id.id])],
                    'qty_done': 1.0
                })
            
            claim.rma_in_picking_id = picking.id
            claim.state = 'rma_in'
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('RMA Inbound Picking'),
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_repair(self):
        """Create Repair Order for the claim"""
        repair_obj = self.env['repair.order']
        
        for claim in self:
            if claim.state not in ['rma_in', 'under_review']:
                raise UserError(_("Claim must be in RMA In or Under Review state to create repair."))
            
            # Get the repair location from settings
            repair_location_id = self.env['ir.config_parameter'].sudo().get_param(
                'buz.default_repair_location_id'
            )
            if not repair_location_id:
                raise UserError(_("Default repair location is not configured in settings."))
            
            repair_location = self.env['stock.location'].browse(int(repair_location_id))
            if not repair_location.exists():
                raise UserError(_("Configured repair location does not exist."))
            
            # Create the repair order
            repair_vals = {
                'product_id': claim.product_id.id,
                'product_uom': claim.product_id.uom_id.id,
                'partner_id': claim.partner_id.id,
                'guarantee_limit': claim.contract_id.end_date,
                'lot_id': claim.lot_id.id,
                'buz_claim_id': claim.id,
                'location_id': repair_location.id,
                'invoice_method': 'b4repair',  # No invoice for warranty repairs
                'operations': [],  # Operations will be added separately
                'fees_lines': [(0, 0, {
                    'product_id': claim.product_id.id,
                    'product_uom_qty': 1,
                    'product_uom': claim.product_id.uom_id.id,
                    'name': 'Warranty Repair Service',
                    'price_unit': 0,  # Free for warranty claims
                })],
            }
            
            repair = repair_obj.create(repair_vals)
            claim.repair_id = repair.id
            claim.state = 'repairing'
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Repair Order'),
            'res_model': 'repair.order',
            'res_id': repair.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_replacement(self):
        """Create Outbound Picking for Replacement"""
        picking_type_obj = self.env['stock.picking.type']
        picking_obj = self.env['stock.picking']
        move_obj = self.env['stock.move']
        
        for claim in self:
            if claim.state not in ['repairing', 'under_review']:
                raise UserError(_("Claim must be in Repairing state to create replacement."))
            
            # Get the replacement picking type from settings
            picking_type_id = self.env['ir.config_parameter'].sudo().get_param(
                'buz.default_replacement_type_id'
            )
            if not picking_type_id:
                raise UserError(_("Default replacement picking type is not configured in settings."))
            
            picking_type = picking_type_obj.browse(int(picking_type_id))
            if not picking_type.exists():
                raise UserError(_("Configured replacement picking type does not exist."))
            
            # Create the outbound picking
            picking_vals = {
                'partner_id': claim.partner_id.id,
                'picking_type_id': picking_type.id,
                'location_id': picking_type.default_location_src_id.id or self.env.ref('stock.stock_location_stock').id,
                'location_dest_id': picking_type.default_location_dest_id.id or self.env.ref('stock.stock_location_customers').id,
                'origin': claim.name,
                'buz_claim_id': claim.id,
            }
            
            picking = picking_obj.create(picking_vals)
            
            # Create stock move for the replacement product
            # For now, assume the replacement product is the same as the original
            move_vals = {
                'name': claim.product_id.name,
                'product_id': claim.product_id.id,
                'product_uom_qty': 1,
                'product_uom': claim.product_id.uom_id.id,
                'picking_id': picking.id,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
                'description_picking': "Replacement for warranty claim: %s" % claim.name,
            }
            
            move_obj.create(move_vals)
            claim.replacement_out_picking_id = picking.id
            claim.state = 'replacing'
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Replacement Outbound Picking'),
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_return_to_customer(self):
        """Create Outbound Picking to Return Product to Customer"""
        picking_type_obj = self.env['stock.picking.type']
        picking_obj = self.env['stock.picking']
        move_obj = self.env['stock.move']
        
        for claim in self:
            if claim.state not in ['repairing', 'rma_in']:
                raise UserError(_("Claim must be in Repairing or RMA In state to return to customer."))
            
            # Get the RMA return picking type from settings
            picking_type_id = self.env['ir.config_parameter'].sudo().get_param(
                'buz.default_rma_return_type_id'
            )
            if not picking_type_id:
                raise UserError(_("Default RMA return picking type is not configured in settings."))
            
            picking_type = picking_type_obj.browse(int(picking_type_id))
            if not picking_type.exists():
                raise UserError(_("Configured RMA return picking type does not exist."))
            
            # Create the outbound picking
            picking_vals = {
                'partner_id': claim.partner_id.id,
                'picking_type_id': picking_type.id,
                'location_id': picking_type.default_location_src_id.id or self.env.ref('stock.stock_location_stock').id,
                'location_dest_id': picking_type.default_location_dest_id.id or self.env.ref('stock.stock_location_customers').id,
                'origin': claim.name,
                'buz_claim_id': claim.id,
            }
            
            picking = picking_obj.create(picking_vals)
            
            # Create stock move for the product
            move_vals = {
                'name': claim.product_id.name,
                'product_id': claim.product_id.id,
                'product_uom_qty': 1,
                'product_uom': claim.product_id.uom_id.id,
                'picking_id': picking.id,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
                'description_picking': "Return to customer for warranty claim: %s" % claim.name,
            }
            
            move = move_obj.create(move_vals)
            # Apply the lot to the move
            if claim.lot_id:
                move.move_line_ids.write({
                    'lot_ids': [(6, 0, [claim.lot_id.id])],
                    'qty_done': 1.0
                })
            
            claim.return_to_customer_picking_id = picking.id
            claim.state = 'ready_to_return'
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Return to Customer Picking'),
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_invoice(self):
        """Create invoice for out-of-warranty claims"""
        for claim in self:
            if claim.is_in_warranty:
                raise UserError(_("Cannot create invoice for in-warranty claims."))
            if not claim.claim_cost_line_ids:
                raise UserError(_("No cost lines to invoice."))
            
            # Create sales order first
            sale_order = self.env['sale.order'].create({
                'partner_id': claim.partner_id.id,
                'order_line': [
                    (0, 0, {
                        'product_id': cost_line.product_id.id,
                        'product_uom_qty': cost_line.quantity,
                        'price_unit': cost_line.price_unit,
                        'tax_id': [(6, 0, cost_line.tax_ids.ids)]
                    }) for cost_line in claim.claim_cost_line_ids
                ]
            })
            
            sale_order.action_confirm()
            
            # Create invoice from SO
            invoice = sale_order._create_invoices()
            invoice.action_post()
            
            claim.invoice_id = invoice.id
            
        return {
            'type': 'ir.actions.act_window',
            'name': _('Claim Invoice'),
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_mark_done(self):
        """Mark the claim as done"""
        for claim in self:
            # Check if all required operations are complete
            if claim.state not in ['ready_to_return', 'replacing', 'repairing']:
                raise UserError(_("Claim must be in Ready to Return, Replacing, or Repairing state to be marked as done."))
            
            # Check if all required documents are validated
            required_docs_validated = True
            if claim.rma_in_picking_id and claim.rma_in_picking_id.state != 'done':
                required_docs_validated = False
            if claim.replacement_out_picking_id and claim.replacement_out_picking_id.state != 'done':
                required_docs_validated = False
            if claim.return_to_customer_picking_id and claim.return_to_customer_picking_id.state != 'done':
                required_docs_validated = False
            if claim.repair_id and claim.repair_id.state != 'done':
                required_docs_validated = False
            if not claim.is_in_warranty and not claim.invoice_id:
                required_docs_validated = False
            elif not claim.is_in_warranty and claim.invoice_id and claim.invoice_id.state != 'posted':
                required_docs_validated = False
            
            if not required_docs_validated:
                raise UserError(_("All required operations and documents must be completed before marking as done."))
                
            claim.state = 'done'
        
        return True

    @api.constrains('contract_id', 'lot_id', 'state')
    def _check_duplicate_active_claims(self):
        """Prevent multiple active claims for the same contract/lot"""
        for claim in self:
            if claim.state not in ['done', 'cancel']:
                overlapping_claims = self.search([
                    ('id', '!=', claim.id),
                    ('contract_id', '=', claim.contract_id.id),
                    ('lot_id', '=', claim.lot_id.id),
                    ('state', 'not in', ['done', 'cancel']),
                    ('company_id', '=', claim.company_id.id)
                ])
                if overlapping_claims:
                    raise ValidationError(_(
                        "There is already an active warranty claim for this contract and lot/serial number. "
                        "Please close the existing claim before creating a new one."
                    ))

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('buz.warranty.claim') or _('New')
        return super().create(vals)

    def write(self, vals):
        # Auto-update state based on related documents
        res = super().write(vals)
        
        for claim in self:
            # Update state based on related picking statuses
            if claim.rma_in_picking_id and claim.rma_in_picking_id.state == 'done' and claim.state == 'draft':
                claim.state = 'rma_in'
            
            # Update state based on repair status
            if claim.repair_id and claim.repair_id.state == 'done' and claim.state in ['repairing']:
                claim.state = 'ready_to_return'
            
            # Update state based on replacement picking status
            if claim.replacement_out_picking_id and claim.replacement_out_picking_id.state == 'done':
                claim.state = 'done'
            
            # Update state based on return picking status
            if claim.return_to_customer_picking_id and claim.return_to_customer_picking_id.state == 'done':
                claim.state = 'done'
        
        return res