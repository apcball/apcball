from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ITRequestProcurement(models.Model):
    _name = 'it.request.procurement'
    _description = 'IT Procurement Request - For requesting IT equipment procurement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    
    active = fields.Boolean(default=True)

    name = fields.Char('Request Number', required=True, copy=False, readonly=True, 
                       default=lambda self: _('New'))
    requester_id = fields.Many2one('hr.employee', string='Requester', required=True,
                                   default=lambda self: self.env.user.employee_id)
    department_id = fields.Many2one('hr.department', string='Department', required=True)
    justification = fields.Text('Justification', required=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    
    manager_id = fields.Many2one('hr.employee', string='Approving Manager')
    approval_note = fields.Text('Manager Approval Note')
    
    it_operator_id = fields.Many2one('hr.employee', string='IT Operator')
    it_spec_note = fields.Text('IT Specification Note')
    
    line_ids = fields.One2many('it.procurement.line', 'request_id', string='Procurement Lines')
    
    # Only purchase_order_id is available in standard Odoo 17
    # purchase_request_id field removed as purchase.request model doesn't exist
    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('to_manager_approve', 'To Manager Approve'),
        ('manager_approved', 'Manager Approved'),
        ('to_it', 'To IT'),
        ('it_reviewed', 'IT Reviewed'),
        ('pr_created', 'Purchase Request Created'),
        ('done', 'Done')
    ], string='State', default='draft', tracking=True)

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('it.request.procurement') or _('New')
        # Set department based on requester if not specified
        if 'department_id' not in vals and 'requester_id' in vals:
            requester = self.env['hr.employee'].browse(vals['requester_id'])
            if requester.department_id:
                vals['department_id'] = requester.department_id.id
        return super().create(vals)

    @api.model
    def _get_it_employees(self):
        """Get employees from IT department"""
        it_department = self.env.ref('hr.dep_it', False)
        if it_department:
            return self.env['hr.employee'].search([('department_id', '=', it_department.id)]).ids
        return []

    @api.onchange('requester_id')
    def _onchange_requester_id(self):
        """Set department based on requester"""
        if self.requester_id and self.requester_id.department_id and not self.department_id:
            self.department_id = self.requester_id.department_id

    def action_submit_for_approval(self):
        """Submit request for manager approval"""
        if not self.justification:
            raise ValidationError(_("Justification is required before submitting for approval."))
        if not self.line_ids:
            raise ValidationError(_("At least one procurement line is required."))
            
        # Set manager to requester's parent by default if not set
        if not self.manager_id and self.requester_id.parent_id:
            self.manager_id = self.requester_id.parent_id
            
        self.write({'state': 'to_manager_approve'})
        
        # Create activity for manager
        if self.manager_id and self.manager_id.user_id:
            self.activity_schedule(
                'buz_it_request.activity_manager_approval',
                user_id=self.manager_id.user_id.id,
                note=_('Procurement request requires your approval')
            )

    def action_manager_approve(self):
        """Manager approves the request"""
        # Ensure the form is saved before checking the approval note
        self.ensure_one()
        if not self.approval_note:
            raise ValidationError(_("Approval note is required for manager approval. Please add an approval note before approving."))
        self.write({'state': 'manager_approved'})
        
        # Create activity for IT
        it_users = self.env['hr.employee'].search([('id', 'in', self._get_it_employees())], limit=1)
        if it_users and it_users[0].user_id:
            self.activity_schedule(
                'buz_it_request.activity_it_action',
                user_id=it_users[0].user_id.id,
                note=_('Procurement request approved and requires IT review')
            )

    def action_manager_reject(self):
        """Manager rejects the request"""
        self.write({'state': 'draft'})  # Return to requester
        self.activity_unlink('buz_it_request.activity_manager_approval')

    def action_send_to_it(self):
        """Send approved request to IT team"""
        if self.state != 'manager_approved':
            raise ValidationError(_("Request must be manager approved before sending to IT."))
        self.write({'state': 'to_it'})
        
        # Create activity for IT
        it_users = self.env['hr.employee'].search([('id', 'in', self._get_it_employees())], limit=1)
        if it_users and it_users[0].user_id:
            self.activity_schedule(
                'buz_it_request.activity_it_action',
                user_id=it_users[0].user_id.id,
                note=_('Procurement request ready for IT review')
            )

    def action_it_review(self):
        """IT reviews the request"""
        if not self.it_spec_note:
            raise ValidationError(_("IT specification note is required for IT review."))
        self.write({'state': 'it_reviewed'})

    def action_create_pr(self):
        """Create purchase request from this procurement request"""
        # In Odoo 17, a purchase order requires a vendor
        # We'll redirect user to purchase order creation form with pre-filled data
        # This allows user to select a vendor before creating the order
        
        # Prepare line data for the purchase order
        line_vals = []
        for line in self.line_ids:
            if not line.product_id:
                raise ValidationError(_("All procurement lines must have a product specified."))
            line_vals.append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.description or line.product_id.name,
                'product_qty': line.qty,
                'product_uom': line.uom_id.id if line.uom_id else line.product_id.uom_po_id.id,
                'price_unit': 0.0,  # Will be filled by vendor
            }))
        
        # Return action to open purchase order creation form with pre-filled data
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Purchase Order'),
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'view_id': self.env.ref('purchase.purchase_order_form').id,
            'target': 'current',
            'context': {
                'default_origin': self.name,
                'default_order_line': line_vals,
            }
        }
        
        # Create lines in RFQ
        for line in self.line_ids:
            if not line.product_id:
                raise ValidationError(_("All procurement lines must have a product specified."))
            rfq_line_vals = {
                'order_id': rfq.id,
                'product_id': line.product_id.id,
                'name': line.description or line.product_id.name,
                'product_qty': line.qty,
                'product_uom': line.uom_id.id if line.uom_id else line.product_id.uom_po_id.id,
                'price_unit': 0.0,  # Will be filled by vendor
            }
            self.env['purchase.order.line'].create(rfq_line_vals)
            
        self.write({
            'purchase_order_id': rfq.id,
            'state': 'pr_created'
        })
        
        # Add a message to the chatter
        self.message_post(body=_("RFQ %s has been created.") % rfq.name)

    def action_receive_goods(self):
        """Mark procurement as done when goods are received"""
        # This would be called when the purchase order is confirmed and goods received
        self.write({'state': 'done'})

    def action_view_pr(self):
        """Smart button action to view related purchase order (RFQ)"""
        action = self.env["ir.actions.actions"]._for_xml_id("purchase.purchase_order_action")
        if self.purchase_order_id:
            action['views'] = [(self.env.ref('purchase.purchase_order_form').id, 'form')]
            action['res_id'] = self.purchase_order_id.id
        return action
    
    def action_view_po(self):
        """Smart button action to view related purchase order (PO)"""
        # This method is kept for compatibility but may not be used
        action = self.env["ir.actions.actions"]._for_xml_id("purchase.purchase_order_action")
        if self.purchase_order_id:
            action['views'] = [(self.env.ref('purchase.purchase_order_form').id, 'form')]
            action['res_id'] = self.purchase_order_id.id
        return action


class ITProcurementLine(models.Model):
    _name = 'it.procurement.line'
    _description = 'IT Procurement Request Line'

    request_id = fields.Many2one('it.request.procurement', string='Request Reference', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product')
    description = fields.Char('Description')
    qty = fields.Float('Quantity', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    est_price = fields.Float('Estimated Price')
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Update UOM when product is selected"""
        if self.product_id:
            self.uom_id = self.product_id.uom_po_id
            if not self.description:
                self.description = self.product_id.name