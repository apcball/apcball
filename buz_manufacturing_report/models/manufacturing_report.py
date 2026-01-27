# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta


class ManufacturingReport(models.Model):
    _name = 'manufacturing.report'
    _description = 'Manufacturing Report'
    _order = 'id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    # Use delegation to mrp.production to avoid copying its fields (prevents many2many table conflicts)
    _inherits = {'mrp.production': 'production_id'}

    department_id = fields.Many2one('hr.department', string='Department')
    date_planned_finished = fields.Datetime(string='Planned End Date')

    name = fields.Char(string='Name', required=True, copy=False, readonly=True,
                       default=lambda self: _('New'))
    # delegation field to mrp.production (used by _inherits)
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', related='production_id.product_id', store=True)
    product_qty = fields.Float(string='Quantity', related='production_id.product_qty', store=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', related='production_id.product_uom_id', store=True)
    # In Odoo 17, the field names for planned dates have changed
    date_planned_start = fields.Datetime(string='Planned Start Date', store=True)
    date_planned_finished = fields.Datetime(string='Planned End Date', store=True)
    # These fields might also need to be updated if they've changed in Odoo 17
    date_start = fields.Datetime(string='Start Date', store=True)
    date_finished = fields.Datetime(string='End Date', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('progress', 'In Progress'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')], string='Status',
        related='production_id.state', store=True)
    company_id = fields.Many2one('res.company', string='Company', related='production_id.company_id', store=True)
    user_id = fields.Many2one('res.users', string='Responsible', related='production_id.user_id', store=True)
    workorder_ids = fields.One2many('mrp.workorder', string='Work Orders', related='production_id.workorder_ids')
    move_raw_ids = fields.One2many('stock.move', string='Raw Materials', related='production_id.move_raw_ids')
    move_finished_ids = fields.One2many('stock.move', string='Finished Products', related='production_id.move_finished_ids')
    report_date = fields.Date(string='Report Date', default=fields.Date.today, required=True)
    notes = fields.Text(string='Notes')
    note = fields.Text(string='Notes')  # Add this line to define the note field
    date_planned_finished = fields.Datetime(string='Planned End Date', store=True)

    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('manufacturing.report') or _('New')
        records = super(ManufacturingReport, self).create(vals_list)
        # Update planned dates from production orders
        for record in records:
            if record.production_id:
                record._update_planned_dates()
        return records
    
    @api.onchange('production_id')
    def _onchange_production_id(self):
        if self.production_id:
            self._update_planned_dates()
    
    def _update_planned_dates(self):
        """Update planned dates based on the production order"""
        if self.production_id:
            # Get the dates from the production order
            # In Odoo 17, these might be in different fields or computed differently
            # Using direct assignment instead of related fields
            production = self.production_id
            
            # Try to get the planned dates from various possible field names
            # that might exist in Odoo 17
            if hasattr(production, 'date_planned_start'):
                self.date_planned_start = production.date_planned_start
            elif hasattr(production, 'date_planned'):
                self.date_planned_start = production.date_planned
            else:
                self.date_planned_start = fields.Datetime.now()
                
            if hasattr(production, 'date_planned_finished'):
                self.date_planned_finished = production.date_planned_finished
            elif hasattr(production, 'date_deadline'):
                self.date_planned_finished = production.date_deadline
            else:
                self.date_planned_finished = fields.Datetime.now()
                
            # Update actual start and end dates
            self.date_start = production.date_start if hasattr(production, 'date_start') else False
            self.date_finished = production.date_finished if hasattr(production, 'date_finished') else False
    
    def action_print_report(self):
        return self.env.ref('buz_manufacturing_report.action_report_manufacturing').report_action(self)
    
    def action_send_email(self):
        '''Send the report by email'''
        self.ensure_one()
        template = self.env.ref('buz_manufacturing_report.email_template_manufacturing_report')
        if template:
            template.send_mail(self.id, force_send=True)
            return {'type': 'ir.actions.act_window_close'}
        return False