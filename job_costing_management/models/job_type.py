# -*- coding: utf-8 -*-

from odoo import models, fields, api


class JobType(models.Model):
    _name = 'job.type'
    _description = 'Job Type'
    _order = 'sequence, name'

    name = fields.Char(string='Job Type', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)
    color = fields.Integer(string='Color')
    
    # Statistics
    project_count = fields.Integer(string='Project Count', compute='_compute_project_count')
    
    @api.depends('name')
    def _compute_project_count(self):
        for record in self:
            record.project_count = self.env['project.project'].search_count([
                ('job_type_id', '=', record.id)
            ])
    
    def action_view_projects(self):
        return {
            'name': 'Projects',
            'type': 'ir.actions.act_window',
            'res_model': 'project.project',
            'view_mode': 'tree,form',
            'domain': [('job_type_id', '=', self.id)],
            'context': {'default_job_type_id': self.id}
        }
