from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class ICRequest(models.Model):
    _name = 'ic.request'
    _description = 'Internal Consumption Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_request desc, id desc'

    name = fields.Char(
        string='Reference',
        readonly=True,
        default=lambda self: _('New'),
        copy=False
    )
    date_request = fields.Date(
        string='Request Date',
        required=True,
        default=fields.Date.context_today,
        readonly=True
    )
    requester_id = fields.Many2one(
        'res.users',
        string='Requester',
        required=True,
        readonly=True,
        default=lambda self: self.env.user
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department'
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account'
    )
    analytic_tag_ids = fields.Many2many(
        'account.analytic.tag',
        string='Analytic Tags'
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Source Location',
        required=True,
        domain=[('usage', '=', 'internal')]
    )
    dest_location_id = fields.Many2one(
        'stock.location',
        string='Destination Location',
        default=lambda self: self.env['stock.location'].search([('usage', '=', 'consume')], limit=1),
        domain=[('usage', '=', 'consume')]
    )
    expense_policy = fields.Selection([
        ('valuation_based', 'Valuation Based'),
        ('standard_cost', 'Standard Cost'),
        ('fifo_layer', 'FIFO Layer'),
    ], string='Expense Policy', default='standard_cost'
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        domain=[('type', '=', 'general')]
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('manager_approved', 'Manager Approved'),
        ('store_done', 'Store Done'),
        ('accounted', 'Accounted'),
        ('canceled', 'Canceled'),
    ], string='Status', default='draft', tracking=True
    )
    line_ids = fields.One2many(
        'ic.request.line',
        'request_id',
        string='Request Lines',
        copy=True
    )
    amount_total_cost = fields.Monetary(
        string='Total Cost',
        compute='_compute_amount_total_cost',
        store=True,
        currency_field='currency_id'
    )
    note = fields.Text(string='Note')
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        readonly=True
    )

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('ic.request') or _('New')
        return super().create(vals)

    @api.depends('line_ids.subtotal_cost')
    def _compute_amount_total_cost(self):
        for record in self:
            record.amount_total_cost = sum(line.subtotal_cost for line in record.line_ids)

    def action_submit(self):
        """Submit the request for approval"""
        if not self.line_ids:
            raise ValidationError(_("Cannot submit a request without lines."))
        
        for line in self.line_ids:
            if line.qty <= 0:
                raise ValidationError(_("Quantity must be greater than 0 for all lines."))
        
        self.write({
            'state': 'submitted'
        })
        
        # Create activity for manager
        manager_group = self.env['ir.model.data'].xmlid_to_res_id('buz_internal_consumption.group_ic_manager')
        if manager_group:
            managers = self.env['res.users'].search([('groups_id', 'in', manager_group)])
        else:
            managers = self.env['res.users'].search([])
        
        # Get approval activity type with safe reference
        approval_activity = self.env.ref('mail.mail_activity_data_approval', raise_if_not_found=False)
        activity_vals = {
            'activity_type_id': approval_activity.id if approval_activity else False,
            'summary': _('Internal Consumption Request Approval'),
            'date_deadline': fields.Date.context_today(self),
            'user_id': managers[0].id if managers else self.env.user.id,
            'res_id': self.id,
            'res_model_id': self.env['ir.model'].search([('model', '=', 'ic.request')]).id,
        }
        self.env['mail.activity'].create(activity_vals)
        
        return True

    def action_approve(self):
        """Approve the request"""
        self.ensure_one()
        self.write({
            'state': 'manager_approved'
        })
        
        # Log activity
        self.activity_feedback(['mail.mail_activity_data_approval'], feedback=_('Approved'))
        
        return True

    def action_reject(self):
        """Reject the request"""
        self.ensure_one()
        self.write({
            'state': 'draft'
        })
        
        # Log activity
        self.activity_feedback(['mail.mail_activity_data_approval'], feedback=_('Rejected'))
        
        return True

    def action_done(self):
        """Create stock moves and mark as done"""
        self.ensure_one()
        
        # Create stock move for each line
        for line in self.line_ids:
            if not line.move_id:
                stock_move = self.env['stock.move'].create({
                    'name': f"{self.name} - {line.product_id.display_name}",
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.qty,
                    'product_uom': line.uom_id.id,
                    'location_id': self.location_id.id,
                    'location_dest_id': self.dest_location_id.id if self.dest_location_id else self.location_id.id,
                    'picking_type_id': self.env.ref('stock.picking_type_internal', raise_if_not_found=False).id if self.env.ref('stock.picking_type_internal', raise_if_not_found=False) else False,
                    'origin': self.name,
                    'state': 'confirmed',
                })
                
                # Validate the stock move
                stock_move._action_confirm()
                stock_move._action_assign()
                
                # For internal consumption, we need to validate the move
                if stock_move.state == 'assigned':
                    for move_line in stock_move.move_line_ids:
                        move_line.qty_done = move_line.reserved_uom_qty
                    stock_move._action_done()
                
                # Link the stock move to the line
                line.move_id = stock_move.id

        self.write({
            'state': 'store_done'
        })
        
        return True

    def action_create_account_move(self):
        """Create accounting entry"""
        self.ensure_one()
        
        if self.state != 'store_done':
            raise UserError(_("Cannot create accounting entry if stock moves are not done."))
        
        # Create account move
        account_move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': self.date_request,
            'ref': f"IC: {self.name}",
            'journal_id': self.journal_id.id if self.journal_id else self.env['account.journal'].search([('type', '=', 'general')], limit=1).id,
        })
        
        # Group lines by expense account
        grouped_lines = {}
        for line in self.line_ids:
            expense_account = line.expense_account_id or line.product_id.categ_id.property_account_expense_categ_id
            if not expense_account:
                expense_account = self.env.company.account_expense_product_categ_id
            
            key = (expense_account.id, line.analytic_account_id.id if line.analytic_account_id else None)
            if key not in grouped_lines:
                grouped_lines[key] = {'debit': 0.0, 'credit': 0.0, 'analytic_account_id': line.analytic_account_id.id}
            
            grouped_lines[key]['debit'] += line.subtotal_cost

        # Add inventory credit
        stock_valuation_account = self.env['account.account']
        for line in self.line_ids:
            stock_account = line.product_id.categ_id.property_stock_valuation_account_id
            if not stock_account:
                stock_account = self.env.company.property_stock_valuation_account_id
            
            if stock_account:
                # Add to existing valuation account or create new entry
                key = (stock_account.id, None)  # No analytic account for inventory credit
                if key not in grouped_lines:
                    grouped_lines[key] = {'debit': 0.0, 'credit': 0.0, 'analytic_account_id': None}
                
                grouped_lines[key]['credit'] += line.subtotal_cost

        # Create move lines
        move_lines = []
        for key, amounts in grouped_lines.items():
            account_id = key[0]
            analytic_account_id = amounts['analytic_account_id']
            
            if amounts['debit'] > 0:
                move_lines.append((0, 0, {
                    'account_id': account_id,
                    'debit': amounts['debit'],
                    'credit': 0.0,
                    'analytic_account_id': analytic_account_id,
                    'name': f"IC: {self.name}",
                }))
            
            if amounts['credit'] > 0:
                move_lines.append((0, 0, {
                    'account_id': account_id,
                    'debit': 0.0,
                    'credit': amounts['credit'],
                    'analytic_account_id': analytic_account_id,
                    'name': f"IC: {self.name}",
                }))
        
        account_move.write({
            'line_ids': move_lines
        })
        
        # Post the move if auto-posting is enabled
        if self.env.company.ic_auto_post_journal_entries:
            account_move.action_post()
        
        self.write({
            'state': 'accounted'
        })
        
        return True

    def action_cancel(self):
        """Cancel the request"""
        self.ensure_one()
        
        # Check if stock moves exist and handle them
        for line in self.line_ids:
            if line.move_id:
                if line.move_id.state == 'done':
                    raise UserError(_("Cannot cancel request with posted stock moves."))
                elif line.move_id.state in ['confirmed', 'assigned']:
                    line.move_id._action_cancel()
        
        # Also cancel any related journal entries
        related_moves = self.env['account.move'].search([('ref', 'like', f"IC: {self.name}")])
        for move in related_moves:
            if move.state == 'posted':
                move.button_draft()
            move.unlink()
        
        self.write({'state': 'canceled'})
        
        return True

    def action_reset_to_draft(self):
        """Reset to draft state"""
        self.ensure_one()
        self.write({'state': 'draft'})
        return True


class ICRequestLine(models.Model):
    _name = 'ic.request.line'
    _description = 'Internal Consumption Request Line'

    request_id = fields.Many2one(
        'ic.request',
        string='Request Reference',
        required=True,
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain=[('type', '=', 'product')],  # Only stockable products
        ondelete='restrict'
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        required=True
    )
    qty = fields.Float(
        string='Quantity',
        required=True,
        digits='Product Unit of Measure',
        default=1.0
    )
    available_qty = fields.Float(
        string='Available Quantity',
        compute='_compute_available_qty'
    )
    expense_account_id = fields.Many2one(
        'account.account',
        string='Expense Account',
        domain=[('deprecated', '=', False)]
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account'
    )
    analytic_tag_ids = fields.Many2many(
        'account.analytic.tag',
        string='Analytic Tags'
    )
    unit_cost = fields.Monetary(
        string='Unit Cost',
        compute='_compute_unit_cost',
        store=True,
        currency_field='currency_id'
    )
    subtotal_cost = fields.Monetary(
        string='Subtotal Cost',
        compute='_compute_subtotal_cost',
        store=True,
        currency_field='currency_id'
    )
    move_id = fields.Many2one(
        'stock.move',
        string='Stock Move',
        readonly=True
    )

    valuation_layer_ids = fields.Many2many(
        'stock.valuation.layer',
        string='Valuation Layers'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='request_id.currency_id',
        store=True
    )

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Set UOM when product changes"""
        if self.product_id:
            self.uom_id = self.product_id.uom_id
            self.unit_cost = self.product_id.standard_price

    @api.depends('product_id', 'request_id.location_id')
    def _compute_available_qty(self):
        """Compute available quantity for the product at location"""
        for line in self:
            if line.product_id and line.request_id.location_id:
                line.available_qty = line.product_id.with_context(
                    location=line.request_id.location_id.id
                ).qty_available
            else:
                line.available_qty = 0.0

    @api.depends('product_id', 'request_id.expense_policy')
    def _compute_unit_cost(self):
        """Compute unit cost based on the expense policy"""
        for line in self:
            if line.request_id.expense_policy == 'standard_cost':
                line.unit_cost = line.product_id.standard_price
            elif line.request_id.expense_policy == 'fifo_layer':
                # For FIFO, we'd need to implement a custom method to get cost
                line.unit_cost = line.product_id.standard_price  # Fallback for now
            elif line.request_id.expense_policy == 'valuation_based':
                # Use the standard price as default for now
                line.unit_cost = line.product_id.standard_price
            else:
                line.unit_cost = line.product_id.standard_price

    @api.depends('qty', 'unit_cost')
    def _compute_subtotal_cost(self):
        """Compute subtotal cost"""
        for line in self:
            line.subtotal_cost = line.qty * line.unit_cost