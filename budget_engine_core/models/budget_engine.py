# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BudgetEngine(models.AbstractModel):
    """
    Abstract Budget Engine Service.

    This abstract model provides a standard interface for budget operations.
    Concrete budget modules (weekly, monthly, etc.) inherit from this model
    and implement or call these methods to enforce budget discipline.

    Usage:
        self.env['budget.engine'].check_budget(context_data)
        self.env['budget.engine'].reserve_budget(context_data)
        self.env['budget.engine'].consume_budget(context_data)
        self.env['budget.engine'].release_budget(context_data)

    context_data dict keys:
        - budget_source     (str)  'weekly' | 'monthly' | 'other'
        - document_model    (str)  e.g. 'purchase.requisition'
        - document_id       (int)  id of the source document
        - amount            (float)
        - date              (date)
        - company_id        (int)
        - analytic_account_id (int, optional)
        - note              (str, optional)
    """
    _name = 'budget.engine'
    _description = 'Budget Engine (Abstract Service)'

    # ── Public API ───────────────────────────────────────────────

    @api.model
    def check_budget(self, context_data):
        """
        Verify that a given amount is within the available budget.

        Returns True if the budget check passes.
        Raises odoo.exceptions.ValidationError if budget is exceeded.

        Designed to be overridden by concrete budget modules for
        type-specific checks (weekly, monthly, etc.).
        """
        self._validate_context(context_data)
        # Default implementation: always passes.
        # Concrete modules override this with real logic.
        return True

    @api.model
    def reserve_budget(self, context_data):
        """
        Create a budget.commitment record in state 'reserved'.

        Returns the newly created budget.commitment record.
        """
        self._validate_context(context_data)
        vals = self._build_commitment_vals(context_data, state='reserved')
        commitment = self.env['budget.commitment'].sudo().create(vals)
        return commitment

    @api.model
    def consume_budget(self, context_data):
        """
        Mark an existing 'reserved' commitment as 'used', or create a
        new commitment directly in 'used' state if no reservation exists.

        Looks up existing reservations by document_model + document_id.
        Returns the updated/created commitment record(s).
        """
        self._validate_context(context_data)
        existing = self._find_reservations(context_data)
        if existing:
            existing.action_mark_used()
            return existing
        # No prior reservation: create a usage record directly
        vals = self._build_commitment_vals(context_data, state='used')
        return self.env['budget.commitment'].sudo().create(vals)

    @api.model
    def release_budget(self, context_data):
        """
        Release an existing commitment created by this document.

        Looks up existing commitments by document_model + document_id.
        This is used both for cancelling a reservation before it is consumed
        and for undoing a consumed commitment when the source document is
        cancelled after confirmation.
        Returns the updated commitment record(s).
        """
        self._validate_context(context_data)
        domain = [
            ('document_model', '=', context_data['document_model']),
            ('document_id', '=', context_data['document_id']),
            ('state', 'in', ('reserved', 'used')),
            ('budget_source', '=', context_data['budget_source']),
        ]
        if context_data.get('analytic_account_id'):
            domain.append(('analytic_account_id', '=', context_data['analytic_account_id']))
        existing = self.env['budget.commitment'].sudo().search(domain)
        if existing:
            existing.action_release()
        return existing

    # ── Helpers ──────────────────────────────────────────────────

    @api.model
    def _validate_context(self, context_data):
        required = ['budget_source', 'document_model', 'document_id', 'amount', 'company_id']
        missing = [k for k in required if k not in context_data]
        if missing:
            raise ValidationError(
                _('Budget engine context is missing required keys: %s') % ', '.join(missing)
            )

    @api.model
    def _build_commitment_vals(self, context_data, state):
        return {
            'budget_source':        context_data['budget_source'],
            'document_model':       context_data['document_model'],
            'document_id':          context_data['document_id'],
            'amount':               context_data['amount'],
            'state':                state,
            'date':                 context_data.get('date', fields.Date.context_today(self)),
            'company_id':           context_data['company_id'],
            'analytic_account_id':  context_data.get('analytic_account_id'),
            'note':                 context_data.get('note', ''),
        }

    @api.model
    def _find_reservations(self, context_data):
        """Find existing reserved commitments for the given document."""
        domain = [
            ('document_model', '=', context_data['document_model']),
            ('document_id', '=', context_data['document_id']),
            ('state', '=', 'reserved'),
            ('budget_source', '=', context_data['budget_source']),
        ]
        if context_data.get('analytic_account_id'):
            domain.append(('analytic_account_id', '=', context_data['analytic_account_id']))
        return self.env['budget.commitment'].sudo().search(domain)
