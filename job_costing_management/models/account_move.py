# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    job_cost_sheet_id = fields.Many2one('job.cost.sheet', string='Job Cost Sheet')
    project_id = fields.Many2one('project.project', string='Project')
    job_order_id = fields.Many2one('job.order', string='Job Order')


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    job_cost_line_id = fields.Many2one('job.cost.line', string='Job Cost Line')
    
    @api.onchange('analytic_distribution')
    def _onchange_analytic_distribution(self):
        if self.analytic_distribution:
            # Get the first analytic account from distribution
            analytic_account_id = list(self.analytic_distribution.keys())[0] if self.analytic_distribution else False
            
            if analytic_account_id:
                analytic_account = self.env['account.analytic.account'].browse(int(analytic_account_id))
                
                # Find related job cost sheet
                cost_sheet = self.env['job.cost.sheet'].search([
                    ('analytic_account_id', '=', analytic_account.id),
                    ('state', '=', 'approved')
                ], limit=1)
                
                if cost_sheet:
                    domain = [('cost_sheet_id', '=', cost_sheet.id)]
                    return {'domain': {'job_cost_line_id': domain}}
