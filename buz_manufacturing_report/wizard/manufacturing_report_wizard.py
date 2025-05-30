# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta


class ManufacturingReportWizard(models.TransientModel):
    _name = 'manufacturing.report.wizard'
    _description = 'Manufacturing Report Wizard'

    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', required=True)
    report_date = fields.Date(string='Report Date', default=fields.Date.today, required=True)
    notes = fields.Text(string='Notes')
    
    @api.onchange('production_id')
    def _onchange_production_id(self):
        if self.production_id:
            self.notes = f"Report for manufacturing order {self.production_id.name} generated on {fields.Date.today()}"
    
    def action_generate_report(self):
        self.ensure_one()
        if not self.production_id:
            raise UserError(_('Please select a manufacturing order.'))
        
        # Create the report record
        report_vals = {
            'production_id': self.production_id.id,
            'report_date': self.report_date,
            'notes': self.notes,
        }
        report = self.env['manufacturing.report'].create(report_vals)
        
        # Return the action to view the created report
        return {
            'name': _('Manufacturing Report'),
            'view_mode': 'form',
            'res_model': 'manufacturing.report',
            'res_id': report.id,
            'type': 'ir.actions.act_window',
            'context': {'form_view_initial_mode': 'edit'},
        }
    
    def action_print_report(self):
        self.ensure_one()
        if not self.production_id:
            raise UserError(_('Please select a manufacturing order.'))
        
        # Create the report record
        report_vals = {
            'production_id': self.production_id.id,
            'report_date': self.report_date,
            'notes': self.notes,
        }
        report = self.env['manufacturing.report'].create(report_vals)
        
        # Print the report directly
        return self.env.ref('buz_manufacturing_report.action_report_manufacturing').report_action(report)
    
    def action_print_xlsx_report(self):
        self.ensure_one()
        if not self.production_id:
            raise UserError(_('Please select a manufacturing order.'))
        
        # Create the report record
        report_vals = {
            'production_id': self.production_id.id,
            'report_date': self.report_date,
            'notes': self.notes,
        }
        report = self.env['manufacturing.report'].create(report_vals)
        
        # Print the XLSX report directly
        return self.env.ref('buz_manufacturing_report.action_report_manufacturing_xlsx').report_action(report)