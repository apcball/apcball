# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class Company(models.Model):
    """Inherit res.company to expose the accounting-date governance policy.

    The policy itself lives on its own model (one row per company) so it can
    own child policy lines (document-type / role) in later file-order steps.
    """

    _inherit = 'res.company'

    date_control_policy_id = fields.Many2one(
        comodel_name='buz.accounting.date.company.policy',
        string='Accounting Date Policy',
        compute='_compute_date_control_policy_id',
        search='_search_date_control_policy_id',
        help='Effective accounting-date policy for this company (fail-closed '
             'if none is configured).',
    )

    def _compute_date_control_policy_id(self):
        Policy = self.env['buz.accounting.date.company.policy']
        for company in self:
            company.date_control_policy_id = Policy.search(
                [('company_id', '=', company.id)], limit=1,
            )

    def _search_date_control_policy_id(self, operator, value):
        return [('company_id', operator, value)]


class BuzAccountingDateCompanyPolicy(models.Model):
    """Per-company floor policy for accounting dates.

    Holds the back-day / future-day ceilings consumed by the account.move
    validation chokepoint. Later steps add journal override, document-type
    lines and role lines on top of this model.
    """

    _name = 'buz.accounting.date.company.policy'
    _description = 'Accounting Date Policy (per company)'
    _order = 'company_id, id'

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
        ondelete='restrict',
    )
    active = fields.Boolean(default=True)
    max_back_days = fields.Integer(
        required=True,
        default=0,
        help='Maximum number of days an accounting date may precede today '
             '(BR-B01). 0 means only today is allowed.',
    )
    max_future_days = fields.Integer(
        required=True,
        default=0,
        help='Maximum number of days an accounting date may follow today '
             '(BR-F01). 0 means only today is allowed.',
    )

    _sql_constraints = [
        ('company_unique', 'unique(company_id)',
         'Each company may have only one accounting date policy.'),
    ]

    @api.constrains('max_back_days', 'max_future_days')
    def _check_days_non_negative(self):
        """BR-P-prefix invariants: ceilings cannot be negative."""
        for record in self:
            if record.max_back_days < 0 or record.max_future_days < 0:
                raise ValidationError(_(
                    "Back-day and future-day ceilings cannot be negative "
                    "(policy '%s')."
                ) % record.name)

    @api.model
    def _seed_default_policies(self):
        """Install-time seed: ensure every existing company has a policy.

        Seeds a permissive policy (365 back-days / 30 future-days) so the
        module is fail-closed yet non-disruptive on a live DEV database.
        Tighten (or replace) per company before production go-live.
        Idempotent: skips companies that already have a policy.
        """
        existing = self.search([('active', 'in', (True, False))])
        companies_with = existing.mapped('company_id')
        for company in self.env['res.company'].search([]):
            if company in companies_with:
                continue
            self.create({
                'name': _('%s — Default Date Policy') % company.name,
                'company_id': company.id,
                'max_back_days': 365,
                'max_future_days': 30,
            })
        return True
