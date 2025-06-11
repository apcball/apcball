# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MarginApprovalRule(models.Model):
    _name = 'margin.approval.rule'
    _description = 'Margin Approval Rule'
    _order = 'min_margin'

    name = fields.Char(string='Rule Name', required=True)
    active = fields.Boolean(default=True)
    min_margin = fields.Float(string='Minimum Margin %', required=True,
                              help="Minimum margin percentage that triggers this rule")
    max_margin = fields.Float(string='Maximum Margin %', required=True,
                              help="Maximum margin percentage for this rule")
    user_ids = fields.Many2many('res.users', string='Approvers',
                                help="Users who can approve sales orders that fall under this margin rule")
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.company)
    send_email = fields.Boolean(string='Send Email Notification', default=True,
                               help="If checked, an email notification will be sent to approvers when approval is requested")
    
    @api.constrains('min_margin', 'max_margin')
    def _check_margin_values(self):
        for rule in self:
            if rule.min_margin >= rule.max_margin:
                raise UserError(_("Minimum margin must be less than maximum margin"))
            
            # Check for overlapping rules
            overlapping = self.search([
                ('id', '!=', rule.id),
                ('company_id', '=', rule.company_id.id),
                '|',
                '&', ('min_margin', '<=', rule.min_margin), ('max_margin', '>=', rule.min_margin),
                '&', ('min_margin', '<=', rule.max_margin), ('max_margin', '>=', rule.max_margin),
            ])
            if overlapping:
                raise UserError(_(f"This rule overlaps with existing rule: {overlapping[0].name}"))
    
    def get_applicable_rule(self, margin_percentage, company_id):
        """Find the applicable rule for a given margin percentage"""
        rule = self.search([
            ('min_margin', '<=', margin_percentage),
            ('max_margin', '>', margin_percentage),
            ('company_id', '=', company_id),
            ('active', '=', True),
        ], limit=1)
        return rule
