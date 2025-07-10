# -*- coding: utf-8 -*-

from odoo import models, fields, api


class JobStage(models.Model):
    _name = 'job.stage'
    _description = 'Job Stage'
    _order = 'sequence, name'

    name = fields.Char(string='Stage Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    description = fields.Text(string='Description')
    fold = fields.Boolean(string='Folded in Kanban', 
                         help='This stage is folded in the kanban view when there are no records in that stage to display.')
    active = fields.Boolean(string='Active', default=True)
    
    # Stage properties
    is_draft = fields.Boolean(string='Is Draft Stage', default=False)
    is_done = fields.Boolean(string='Is Done Stage', default=False)
    is_cancelled = fields.Boolean(string='Is Cancelled Stage', default=False)
    
    # Mail template
    mail_template_id = fields.Many2one('mail.template', string='Email Template',
                                      domain=[('model', '=', 'job.order')])
    
    # Statistics
    job_order_count = fields.Integer(string='Job Order Count', compute='_compute_job_order_count')
    
    @api.depends('name')
    def _compute_job_order_count(self):
        for record in self:
            record.job_order_count = self.env['job.order'].search_count([
                ('stage_id', '=', record.id)
            ])
    
    def action_view_job_orders(self):
        return {
            'name': 'Job Orders',
            'type': 'ir.actions.act_window',
            'res_model': 'job.order',
            'view_mode': 'tree,form,kanban',
            'domain': [('stage_id', '=', self.id)],
            'context': {'default_stage_id': self.id}
        }
