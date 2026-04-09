from odoo import models, fields, api

class FifoResetLog(models.Model):
    _name = 'fifo.reset.log'
    _description = 'FIFO Reset Execution Log'
    _order = 'execution_time desc'

    execution_time = fields.Datetime(string="Execution Time", default=fields.Datetime.now, required=True, readonly=True)
    user_id = fields.Many2one('res.users', string="User", default=lambda self: self.env.user, required=True, readonly=True)
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.company, readonly=True)
    reset_date = fields.Date(string="Reset ณ วันที่", readonly=True)
    
    warehouse_ids = fields.Many2many('stock.warehouse', string="Warehouses", readonly=True)
    progress_detail = fields.Text(string="Progress Detail", readonly=True,
                                  help="Per-warehouse processing status")
    
    total_products = fields.Integer(string="Total Products Affected", readonly=True)
    total_quants = fields.Integer(string="Total Quants Updated", readonly=True)
    
    before_value = fields.Float(string="Valuation Before", digits='Account', readonly=True)
    after_value = fields.Float(string="Valuation After", digits='Account', readonly=True)
    
    status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
    ], string="Status", required=True, readonly=True)
    
    error_message = fields.Text(string="Error Message", readonly=True)
    is_dry_run = fields.Boolean(string="Is Dry Run", readonly=True)
