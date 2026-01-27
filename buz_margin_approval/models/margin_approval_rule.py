# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class MarginApprovalRule(models.Model):
    _name = 'margin.approval.rule'
    _description = 'Margin Approval Rule'
    _order = 'name'

    name = fields.Char(string='Rule Name', required=True)
    active = fields.Boolean(default=True)
    user_ids = fields.Many2many(
        'res.users', 
        'margin_rule_user_rel', 
        'rule_id', 
        'user_id',
        string='Sales Users',
        help="Sales users who must follow this rule"
    )
    company_id = fields.Many2one(
        'res.company', 
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    line_ids = fields.One2many(
        'margin.approval.rule.line', 
        'rule_id', 
        string='Margin Lines',
        help="Define margin ranges and their approvers"
    )
    
    @api.constrains('user_ids', 'company_id', 'active')
    def _check_unique_user(self):
        """A Sales user can belong to only one active rule per company"""
        for rule in self.filtered('active'):
            for user in rule.user_ids:
                other_rules = self.search([
                    ('id', '!=', rule.id),
                    ('active', '=', True),
                    ('company_id', '=', rule.company_id.id),
                    ('user_ids', 'in', user.id)
                ])
                if other_rules:
                    raise ValidationError(
                        _("User %s is already assigned to rule '%s' in company %s. "
                          "A user can only belong to one active rule per company.") % 
                        (user.name, other_rules[0].name, rule.company_id.name)
                    )
    
    def get_applicable_rule_for_user(self, user_id, company_id):
        """Find the applicable rule for a given user"""
        rule = self.search([
            ('user_ids', 'in', user_id),
            ('company_id', '=', company_id),
            ('active', '=', True),
        ], limit=1)
        return rule


class MarginApprovalRuleLine(models.Model):
    _name = 'margin.approval.rule.line'
    _description = 'Margin Approval Rule Line'
    _order = 'min_margin'

    rule_id = fields.Many2one(
        'margin.approval.rule', 
        string='Rule', 
        required=True, 
        ondelete='cascade'
    )
    min_margin = fields.Float(string='Minimum Margin %', required=True)
    max_margin = fields.Float(string='Maximum Margin %', required=True)
    approver_ids = fields.Many2many(
        'res.users',
        'margin_line_approver_rel',
        'line_id',
        'user_id',
        string='Approvers',
        help="Users who can approve orders in this margin range"
    )
    approval_type = fields.Selection([
        ('any', 'Any One Approver'),
        ('all', 'All Approvers'),
    ], string='Approval Type', default='any', required=True)
    company_id = fields.Many2one(
        'res.company',
        related='rule_id.company_id',
        store=True,
        string='Company'
    )
    
    @api.constrains('min_margin', 'max_margin')
    def _check_margin_values(self):
        for line in self:
            if line.min_margin > line.max_margin:
                raise ValidationError(_("Minimum margin must be less than or equal to maximum margin"))
            
            # Check for overlapping ranges within the same rule
            overlapping = self.search([
                ('id', '!=', line.id),
                ('rule_id', '=', line.rule_id.id),
                '|',
                '&', ('min_margin', '<=', line.max_margin), ('max_margin', '>=', line.min_margin),
                '&', ('min_margin', '>=', line.min_margin), ('max_margin', '<=', line.max_margin),
            ])
            if overlapping:
                raise ValidationError(
                    _("Margin range %.2f%% - %.2f%% overlaps with existing range in this rule") % 
                    (line.min_margin, line.max_margin)
                )
    
    def get_applicable_line(self, margin_percentage):
        """Find the applicable line for a given margin percentage"""
        line = self.search([
            ('rule_id', '=', self.rule_id.id),
            ('min_margin', '<=', margin_percentage),
            ('max_margin', '>=', margin_percentage),
        ], limit=1)
        return line
    
    def name_get(self):
        """Custom display name showing margin range"""
        result = []
        for line in self:
            name = "%.1f%% - %.1f%%" % (line.min_margin, line.max_margin)
            if line.approver_ids:
                approver_names = ', '.join(line.approver_ids.mapped('name')[:2])
                if len(line.approver_ids) > 2:
                    approver_names += ', ...'
                name += " (%s)" % approver_names
            result.append((line.id, name))
        return result
