from odoo import api, fields, models

class RequisitionOrder(models.Model):
    _name = 'requisition.order'
    _description = 'Requisition Order'
    
    employee_signature = fields.Binary(
        string='Employee Signature',
        help="Signature of the employee who created this requisition"
    )
    check_signature = fields.Boolean(
        compute='_compute_check_signature',
        help="Check if user is the requisition creator and settings are enabled",
        string="Check Signature"
    )
    user_is_creator = fields.Boolean(
        string="Is Creator",
        compute="_compute_user_is_creator",
        help="Check if current user is the requisition creator"
    )
    settings_approval = fields.Boolean(
        string="Requisition approval enabled",
        compute="_compute_settings_approval",
        help="Check if requisition approval is enabled"
    )

    requisition_product_id = fields.Many2one(  # ใช้ชื่อเดียวกับที่อ้างอิงใน One2many
        'employee.purchase.requisition',
        string='Requisition Reference',
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True
    )
    description = fields.Text(string='Description')
    quantity = fields.Float(string='Quantity', default=1.0)
    uom = fields.Many2one(
        'uom.uom',
        string='Unit of Measure'
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor'
    )
    analytic_distribution = fields.Json(
        string="Analytic Distribution",
        compute="_compute_analytic_distribution",
        store=True,
        copy=True,
        precompute=True
    )
    analytic_precision = fields.Integer(
        string="Analytic Precision",
        default=lambda self: self.env['decimal.precision'].precision_get('Percentage Analytic')
    )
    
    @api.depends('product_id')
    def _compute_analytic_distribution(self):
        for record in self:
            if record.product_id and record.product_id.analytic_distribution:
                record.analytic_distribution = record.product_id.analytic_distribution
            else:
                record.analytic_distribution = False
    
    unit_price = fields.Float(
        string="Unit Price",
        help="Enter the custom unit price for this product"
    )

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.name
            self.uom = self.product_id.uom_id.id

    @api.depends('user_is_creator')
    def _compute_settings_approval(self):
        """Computes the settings_approval field based on settings"""
        for rec in self:
            rec.settings_approval = True if rec.env[
                'ir.config_parameter'].sudo().get_param(
                'purchase.requisition_document_approve') else False

    @api.depends('create_uid')
    def _compute_user_is_creator(self):
        """Computes if current user is the requisition creator"""
        for rec in self:
            rec.user_is_creator = True if rec.create_uid == rec.env.user else False

    @api.depends('user_is_creator')
    def _compute_check_signature(self):
        """Computes if signature should be checked based on settings and signature presence"""
        for rec in self:
            rec.check_signature = True if rec.env[
                'ir.config_parameter'].sudo().get_param(
                'purchase.requisition_document_approve') and rec.employee_signature else False