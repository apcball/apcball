# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    """Inherit account.move to insert the date-governance validation chokepoint.

    Spine coverage (full pipeline in later file-order steps):
      * BR-P04  fail-closed when no policy exists for the company
      * BR-B01  back-day ceiling (hard block in MVP; approval path later)
      * BR-F01  future-day ceiling (hard block in MVP; approval path later)
      * BR-L01  audit every committed create / date-write
    """

    _inherit = 'account.move'

    # ------------------------------------------------------------------
    # Policy resolution
    # ------------------------------------------------------------------
    @api.model
    def _buz_resolve_policy(self, company):
        """Return the active date policy for the given company (recordset)."""
        return self.env['buz.accounting.date.company.policy'].search(
            [('company_id', '=', company.id), ('active', '=', True)],
            limit=1,
        )

    # ------------------------------------------------------------------
    # Validation chokepoint (single entry point)
    # ------------------------------------------------------------------
    @api.model
    def _buz_validate_date(self, proposed_date, company):
        """Validate a proposed accounting date against the company policy.

        Raises UserError on any rejection. Returns None on success.

        Override path (BR-P02, no-approval variant): when the caller passes
        ``buz_override_date_control=True`` in the context AND the current user
        is an Accounting Date Administrator, policy enforcement is skipped.
        The audit row is still written by write(), tagged as an override.
        """
        if self.env.context.get('buz_override_date_control'):
            if not self.env.user.has_group(
                    'buz_accounting_date_control.group_date_admin'):
                raise UserError(_(
                    "Only Accounting Date Administrators may override the "
                    "accounting-date policy (BR-P02)."
                ))
            return

        policy = self._buz_resolve_policy(company)
        if not policy:
            raise UserError(_(
                "No Accounting Date Policy is configured for company '%(co)s'. "
                "Configure one before posting or dating entries "
                "(fail-closed, BR-P04)."
            ) % {'co': company.name})

        today = fields.Date.context_today(self)
        if proposed_date < today:
            back_days = (today - proposed_date).days
            if back_days > policy.max_back_days:
                raise UserError(_(
                    "Backdated entry refused: the proposed date %(d)s is "
                    "%(n)d days in the past, exceeding the company policy "
                    "ceiling of %(cap)d back-days (BR-B01)."
                ) % {'d': proposed_date, 'n': back_days,
                     'cap': policy.max_back_days})
        elif proposed_date > today:
            future_days = (proposed_date - today).days
            if future_days > policy.max_future_days:
                raise UserError(_(
                    "Future-dated entry refused: the proposed date %(d)s is "
                    "%(n)d days in the future, exceeding the company policy "
                    "ceiling of %(cap)d future-days (BR-F01)."
                ) % {'d': proposed_date, 'n': future_days,
                     'cap': policy.max_future_days})

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """Validate the accounting date on every create, then audit-log it."""
        for vals in vals_list:
            date_str = vals.get('date')
            proposed_date = (fields.Date.to_date(date_str)
                             if date_str else fields.Date.context_today(self))
            company = (self.env['res.company'].browse(vals['company_id'])
                       if vals.get('company_id') else self.env.company)
            self._buz_validate_date(proposed_date, company)
        moves = super().create(vals_list)
        AuditLog = self.env['buz.accounting.date.audit.log']
        for move in moves:
            AuditLog.log_event(
                res_model='account.move',
                res_id=move.id,
                event='create',
                severity='info',
                proposed_date=move.date,
                res_name=move.name or '',
                reason='account.move created',
                rule_refs='BR-L01',
                company_id=move.company_id,
            )
        return moves

    def write(self, vals):
        """Validate + audit-log every accounting-date change (BR-L01)."""
        if 'date' not in vals:
            return super().write(vals)

        is_override = bool(self.env.context.get('buz_override_date_control'))
        override_reason = self.env.context.get('buz_override_reason') or ''
        proposed_date = fields.Date.to_date(vals['date'])
        previous = {}
        for move in self:
            company = move.company_id or self.env.company
            previous[move.id] = move.date
            self._buz_validate_date(proposed_date, company)
        res = super().write(vals)
        AuditLog = self.env['buz.accounting.date.audit.log']
        for move in self:
            AuditLog.log_event(
                res_model='account.move',
                res_id=move.id,
                event='override' if is_override else 'write',
                severity='warning' if is_override else 'info',
                proposed_date=proposed_date,
                previous_date=previous.get(move.id),
                res_name=move.name or '',
                reason=override_reason or 'account.move date changed',
                rule_refs='BR-P02-OVERRIDE' if is_override else 'BR-L01',
                company_id=move.company_id,
            )
        return res
