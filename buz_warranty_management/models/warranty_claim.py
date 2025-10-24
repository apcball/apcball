from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WarrantyClaim(models.Model):
    _name = 'warranty.claim'
    _description = 'Warranty Claim'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'claim_date desc'

    name = fields.Char(
        string='Claim Number',
        required=True,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('warranty.claim') or 'New',
        copy=False,
        tracking=True
    )
    warranty_card_id = fields.Many2one(
        'warranty.card',
        string='Warranty Card',
        required=True,
        tracking=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        tracking=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        tracking=True
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Serial/Lot Number'
    )
    claim_type = fields.Selection([
        ('repair', 'Repair'),
        ('replace', 'Replacement'),
        ('refund', 'Refund'),
    ], string='Claim Type', required=True, default='repair', tracking=True)
    is_under_warranty = fields.Boolean(
        string='Under Warranty',
        compute='_compute_is_under_warranty',
        store=True
    )
    claim_date = fields.Date(
        string='Claim Date',
        required=True,
        default=fields.Date.today,
        tracking=True
    )
    status = fields.Selection([
        ('draft', 'Draft'),
        ('under_review', 'Under Review'),
        ('awaiting_return', 'Awaiting Return'),
        ('received', 'Received'),
        ('diagnosing', 'Diagnosing'),
        ('awaiting_parts', 'Awaiting Parts'),
        ('ready_to_issue', 'Ready to Issue'),
        ('approved', 'Approved'),
        ('done', 'Done'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', required=True, tracking=True)
    description = fields.Text(
        string='Problem Description',
        required=True
    )
    internal_notes = fields.Text(string='Internal Notes')
    cost_estimate = fields.Float(
        string='Cost Estimate',
        tracking=True
    )
    quotation_id = fields.Many2one(
        'sale.order',
        string='Out-of-Warranty Quotation',
        readonly=True
    )
    resolution = fields.Text(string='Resolution')
    warranty_end_date = fields.Date(
        string='Warranty End Date',
        related='warranty_card_id.end_date',
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True
    )
    claim_line_ids = fields.One2many(
        'warranty.claim.line',
        'claim_id',
        string='Claim Lines',
        help='Parts and consumables used in repair'
    )
    rma_in_picking_ids = fields.Many2many(
        'stock.picking',
        'warranty_claim_rma_in_rel',
        'claim_id',
        'picking_id',
        string='RMA IN Pickings',
        readonly=True,
        help='Customer return pickings'
    )
    replacement_out_picking_ids = fields.Many2many(
        'stock.picking',
        'warranty_claim_replacement_out_rel',
        'claim_id',
        'picking_id',
        string='Replacement OUT Pickings',
        readonly=True,
        help='Replacement delivery pickings'
    )
    invoice_ids = fields.Many2many(
        'account.move',
        'warranty_claim_invoice_rel',
        'claim_id',
        'invoice_id',
        string='Invoices',
        readonly=True,
        domain="[('move_type', '=', 'out_invoice')]"
    )
    rma_in_count = fields.Integer(
        string='RMA IN Count',
        compute='_compute_picking_counts'
    )
    replacement_out_count = fields.Integer(
        string='Replacement OUT Count',
        compute='_compute_picking_counts'
    )
    invoice_count = fields.Integer(
        string='Invoice Count',
        compute='_compute_invoice_count'
    )

    @api.depends('warranty_card_id', 'warranty_card_id.end_date', 'claim_date')
    def _compute_is_under_warranty(self):
        for record in self:
            if record.warranty_card_id and record.warranty_card_id.end_date:
                record.is_under_warranty = record.claim_date <= record.warranty_card_id.end_date
            else:
                record.is_under_warranty = False

    @api.onchange('warranty_card_id')
    def _onchange_warranty_card_id(self):
        if self.warranty_card_id:
            self.partner_id = self.warranty_card_id.partner_id
            self.product_id = self.warranty_card_id.product_id
            self.lot_id = self.warranty_card_id.lot_id

    def action_review(self):
        self.write({'status': 'under_review'})

    def action_approve(self):
        self.write({'status': 'approved'})

    def action_reject(self):
        self.write({'status': 'rejected'})

    def action_done(self):
        self.write({'status': 'done'})

    def action_create_out_warranty_quotation(self):
        self.ensure_one()
        if self.is_under_warranty:
            raise UserError(_('This claim is still under warranty. Cannot create out-of-warranty quotation.'))
        
        if not self.product_id.product_tmpl_id.allow_out_of_warranty:
            raise UserError(_('Out-of-warranty service is not allowed for this product.'))
        
        return {
            'name': _('Create Out-of-Warranty Quotation'),
            'type': 'ir.actions.act_window',
            'res_model': 'warranty.out.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_claim_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_product_id': self.product_id.product_tmpl_id.service_product_id.id,
                'default_repair_cost': self.cost_estimate,
            }
        }

    def action_view_quotation(self):
        self.ensure_one()
        if not self.quotation_id:
            raise UserError(_('No quotation linked to this claim.'))
        
        return {
            'name': _('Sale Order'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.quotation_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_print_claim_form(self):
        self.ensure_one()
        return self.env.ref('buz_warranty_management.action_report_warranty_claim_form').report_action(self)

    @api.depends('rma_in_picking_ids', 'replacement_out_picking_ids')
    def _compute_picking_counts(self):
        for record in self:
            record.rma_in_count = len(record.rma_in_picking_ids)
            record.replacement_out_count = len(record.replacement_out_picking_ids)

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for record in self:
            record.invoice_count = len(record.invoice_ids)

    def action_create_rma_in(self):
        self.ensure_one()
        return {
            'name': _('Create RMA IN'),
            'type': 'ir.actions.act_window',
            'res_model': 'warranty.rma.receive.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_claim_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_product_id': self.product_id.id,
                'default_lot_id': self.lot_id.id,
            }
        }

    def action_issue_replacement(self):
        self.ensure_one()
        return {
            'name': _('Issue Replacement'),
            'type': 'ir.actions.act_window',
            'res_model': 'warranty.replacement.issue.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_claim_id': self.id,
                'default_partner_id': self.partner_id.id,
            }
        }

    def action_create_invoice(self):
        self.ensure_one()
        return {
            'name': _('Create Invoice'),
            'type': 'ir.actions.act_window',
            'res_model': 'warranty.invoice.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_claim_id': self.id,
                'default_partner_id': self.partner_id.id,
            }
        }

    def action_view_rma_in_pickings(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_picking_tree_all')
        action['domain'] = [('id', 'in', self.rma_in_picking_ids.ids)]
        action['context'] = {}
        return action

    def action_view_replacement_out_pickings(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_picking_tree_all')
        action['domain'] = [('id', 'in', self.replacement_out_picking_ids.ids)]
        action['context'] = {}
        return action

    def action_view_invoices(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_move_out_invoice_type')
        action['domain'] = [('id', 'in', self.invoice_ids.ids)]
        action['context'] = {}
        return action
