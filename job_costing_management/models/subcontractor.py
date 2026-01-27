# -*- coding: utf-8 -*-

from datetime import timedelta
from odoo import models, fields, api
from datetime import timedelta


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Remove the is_subcontractor field and use supplier_rank instead
    subcontractor_type = fields.Selection([
        ('individual', 'Individual'),
        ('company', 'Company')
    ], string='Subcontractor Type', default='company')

    # Subcontractor specific fields
    trade_license = fields.Char(string='Trade License')
    license_expiry = fields.Date(string='License Expiry Date')
    specialization_ids = fields.Many2many('job.type', string='Specializations')
    rating = fields.Selection([
        ('1', '⭐'),
        ('2', '⭐⭐'),
        ('3', '⭐⭐⭐'),
        ('4', '⭐⭐⭐⭐'),
        ('5', '⭐⭐⭐⭐⭐')
    ], string='Rating')

    # Contact details
    contact_person = fields.Char(string='Contact Person')
    emergency_contact = fields.Char(string='Emergency Contact')

    # Project relations
    project_ids = fields.Many2many('project.project', 'project_subcontractor_rel', 
                                  'partner_id', 'project_id', 
                                  string='Projects')

    # Statistics
    project_count = fields.Integer(string='Projects', compute='_compute_project_count', store=True)
    total_contract_value = fields.Float(string='Total Contract Value', compute='_compute_contract_stats', store=True)
    completed_projects = fields.Integer(string='Completed Projects', compute='_compute_contract_stats', store=True)

    @api.depends('project_ids')
    def _compute_project_count(self):
        for record in self:
            record.project_count = len(record.project_ids)

    @api.depends('project_ids')
    def _compute_contract_stats(self):
        for record in self:
            projects = record.project_ids
            if hasattr(projects, 'contract_amount'):
                record.total_contract_value = sum(projects.mapped('contract_amount'))
            else:
                record.total_contract_value = sum(projects.mapped('planned_amount') or [0])

            completed_stages = ['done', 'completed', 'finished', 'closed']
            record.completed_projects = len(projects.filtered(
                lambda p: p.stage_id and p.stage_id.name.lower() in completed_stages
            ))

    def action_view_projects(self):
        return {
            'name': 'Projects',
            'type': 'ir.actions.act_window',
            'res_model': 'project.project',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.project_ids.ids)],
        }

    @api.model
    def get_subcontractors_by_specialization(self, specialization_name):
        specialization = self.env['job.type'].search([('name', '=', specialization_name)], limit=1)
        if specialization:
            return self.search([
                ('supplier_rank', '>', 0),
                ('specialization_ids', 'in', specialization.ids)
            ])
        return self.browse()

    @api.model
    def get_available_subcontractors(self, project_id=None):
        today = fields.Date.context_today(self)
        domain = [
            ('supplier_rank', '>', 0),
            '|',
            ('license_expiry', '=', False),
            ('license_expiry', '>', today)
        ]
        return self.search(domain)

    def get_performance_rating(self):
        if self.project_count == 0:
            return 0
        completion_rate = self.completed_projects / self.project_count
        return min(5, max(1, int(completion_rate * 5) + 1))

    @api.model
    def send_license_expiry_reminders(self):
        expiry_date = fields.Date.context_today(self) + timedelta(days=30)
        expiring_licenses = self.search([
            ('supplier_rank', '>', 0),
            ('license_expiry', '!=', False),
            ('license_expiry', '<=', expiry_date)
        ])

        for subcontractor in expiring_licenses:
            subcontractor.message_post(
                body=f"License expiry reminder: {subcontractor.trade_license} expires on {subcontractor.license_expiry}",
                subject="License Expiry Reminder"
            )

        return True

    def action_set_as_subcontractor(self):
        """Manual action to set partner as subcontractor."""
        self.write({
            'supplier_rank': 1
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'{len(self)} partner(s) set as subcontractor(s).',
                'type': 'success',
            }
        }


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    dest_location_id = fields.Many2one('stock.location', string='Destination Location',
                                      help='Default destination location for material requisitions')


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    dest_location_id = fields.Many2one('stock.location', string='Department Location',
                                      help='Default destination location for department material requisitions')
