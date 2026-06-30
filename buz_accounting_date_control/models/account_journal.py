# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, AccessError


class AccountJournal(models.Model):
    """Inherit account.journal to expose accounting-date governance controls.

    Adds two concerns consumed by the account.move validation chokepoint:
      * ``date_control_disabled``  Admin flag exempting a journal from date
        governance (e.g. system reconciliation journals). BR-J02: exemption
        is logged at WARNING severity when exercised.
      * ``journal_policy_id``      Computed link to the per-journal override
        policy (F2), if one exists for this journal.
    """

    _inherit = 'account.journal'

    date_control_disabled = fields.Boolean(
        string='Disable Date Control',
        default=False,
        copy=False,
        help='When set, this journal is exempt from accounting-date '
             'governance. The exemption is logged at WARNING severity each '
             'time it is exercised (BR-J02). Administrator only.',
    )
    journal_policy_id = fields.Many2one(
        comodel_name='buz.accounting.date.journal.policy',
        string='Date Policy Override',
        compute='_compute_journal_policy_id',
        help='Per-journal override policy that tightens (or, with Admin '
             'sign-off, loosens) the company policy for this journal only.',
    )

    def _compute_journal_policy_id(self):
        """Resolve the single override policy for each journal, if any."""
        Policy = self.env['buz.accounting.date.journal.policy']
        for journal in self:
            journal.journal_policy_id = Policy.search(
                [('journal_id', '=', journal.id)], limit=1,
            )


class BuzAccountingDateJournalPolicy(models.Model):
    """Per-journal override of the company accounting-date policy (F2).

    Effective-policy merge rule (Phase 2 Section 10):
      * Override fields use sentinel ``-1`` = "inherit from company".
      * Any value ``>= 0`` tightens the company ceiling
        (effective = min(company, override)).
      * With ``may_loosen = True`` (Admin sign-off, BR-P02) the override may
        exceed the company ceiling; the sign-off identity and timestamp are
        recorded for audit.

    The merge itself is performed in ``account.move._buz_resolve_policy``
    (activated by a focused follow-up edit, see assumptions).
    """

    _name = 'buz.accounting.date.journal.policy'
    _description = 'Accounting Date Policy Override (per journal)'
    _inherit = ['mail.thread']
    _order = 'company_id, journal_id'
    _rec_name = 'journal_id'

    INHERIT = -1  # sentinel: field unset -> inherit company ceiling

    journal_id = fields.Many2one(
        comodel_name='account.journal',
        required=True,
        ondelete='restrict',
        check_company=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='journal_id.company_id',
        store=True,
        readonly=True,
    )
    active = fields.Boolean(default=True)
    max_back_days_override = fields.Integer(
        default=INHERIT,
        tracking=True,
        help='Sentinel -1 = inherit company ceiling. Any value >= 0 '
             'tightens the company ceiling (effective = min).',
    )
    max_future_days_override = fields.Integer(
        default=INHERIT,
        tracking=True,
        help='Sentinel -1 = inherit company ceiling. Any value >= 0 '
             'tightens the company ceiling (effective = min).',
    )
    may_loosen = fields.Boolean(
        default=False,
        tracking=True,
        help='Allow this override to relax the company ceiling. Requires '
             'Administrator sign-off (BR-P02).',
    )
    may_loosen_set_by = fields.Many2one(
        comodel_name='res.users',
        string='Loosen Signed-off By',
        readonly=True,
        tracking=True,
    )
    may_loosen_set_at = fields.Datetime(
        string='Loosen Signed-off At',
        readonly=True,
        tracking=True,
    )

    _sql_constraints = [
        ('journal_unique', 'unique(journal_id)',
         'Each journal may have only one accounting date policy override.'),
    ]

    @api.constrains('max_back_days_override', 'max_future_days_override')
    def _check_override_values(self):
        """Override fields must be the inherit sentinel (-1) or >= 0."""
        for record in self:
            for value, label in (
                (record.max_back_days_override, 'max_back_days_override'),
                (record.max_future_days_override, 'max_future_days_override'),
            ):
                if value != self.INHERIT and value < 0:
                    raise ValidationError(_(
                        "%(field)s must be %(sentinel)d (inherit) or a "
                        "non-negative integer (policy for journal %(journal)s)."
                    ) % {
                        'field': label,
                        'sentinel': self.INHERIT,
                        'journal': record.journal_id.display_name,
                    })

    @api.model_create_multi
    def create(self, vals_list):
        """BR-P02: creating a loosening override requires the Admin group
        and records the sign-off identity + timestamp."""
        for vals in vals_list:
            if vals.get('may_loosen'):
                self._check_loosen_authorization()
                vals.setdefault('may_loosen_set_by', self.env.user.id)
                vals.setdefault('may_loosen_set_at', fields.Datetime.now())
        return super().create(vals_list)

    def write(self, vals):
        """BR-P02: enabling may_loosen requires the Admin group and records
        the sign-off identity + timestamp."""
        if vals.get('may_loosen'):
            self._check_loosen_authorization()
            vals.setdefault('may_loosen_set_by', self.env.user.id)
            vals.setdefault('may_loosen_set_at', fields.Datetime.now())
        return super().write(vals)

    def _check_loosen_authorization(self):
        """Raise AccessError unless the acting user holds the Admin group."""
        if not self.user_has_groups(
                'buz_accounting_date_control.group_date_admin'):
            raise AccessError(_(
                "Enabling 'may_loosen' on a journal policy requires the "
                "Accounting Date Control Administrator group (BR-P02)."
            ))
