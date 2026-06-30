# -*- coding: utf-8 -*-
import hashlib
import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BuzAccountingDateAuditLog(models.Model):
    """Immutable, hash-chained audit log for every accounting-date event.

    Design (Phase 2 §13 / ADR-08):
      * Append-only: write() and unlink() raise UserError.
      * Tamper-evidence: each row's row_hash = SHA-256(previous_hash +
        canonical payload). The previous row is the latest row for the same
        company (indexed lookup).
      * Single write API: log_event() classmethod. Direct create() without
        supplying both hash fields is blocked by the required constraint.

    Fail-event persistence note: events that raise UserError roll back the
    whole transaction, so a hard-rejection row is not persisted by default.
    The full build adds a savepoint-based path for fail-event logging; the
    spine logs every committed create/write of governed moves.
    """

    _name = 'buz.accounting.date.audit.log'
    _description = 'Immutable Accounting Date Audit Log'
    _order = 'create_date desc, id desc'
    _rec_name = 'event'

    res_model = fields.Char(string='Target Model', required=True)
    res_id = fields.Integer(string='Target ID', required=True)
    res_name = fields.Char(string='Target Name')
    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
    )
    event = fields.Selection(
        selection=[
            ('create', 'Create'),
            ('write', 'Write'),
            ('override', 'Admin Override'),
            ('post', 'Post'),
            ('validation_pass', 'Validation Pass'),
            ('validation_fail', 'Validation Fail'),
        ],
        required=True,
    )
    severity = fields.Selection(
        selection=[
            ('info', 'Info'),
            ('warning', 'Warning'),
            ('critical', 'Critical'),
        ],
        required=True,
        default='info',
    )
    user_id = fields.Many2one(
        comodel_name='res.users',
        required=True,
        default=lambda self: self.env.user,
    )
    proposed_date = fields.Date()
    previous_date = fields.Date()
    reason = fields.Text()
    rule_refs = fields.Char(string='Rule References')
    previous_hash = fields.Char(required=True)
    row_hash = fields.Char(required=True, index=True)

    # -- Immutability -------------------------------------------------
    def write(self, vals):
        """Immutability guard (BR-L02)."""
        raise UserError(_(
            "Accounting date audit log rows are immutable and cannot be edited."
        ))

    def unlink(self):
        """Immutability guard (BR-L02)."""
        raise UserError(_(
            "Accounting date audit log rows are immutable and cannot be deleted."
        ))

    # -- Hash chain helpers ------------------------------------------
    @api.model
    def _canonical_payload(self, **payload):
        """Deterministic JSON encoding of the event payload for hashing."""
        return json.dumps(
            payload, sort_keys=True, default=str, separators=(',', ':'),
        )

    @api.model
    def log_event(self, res_model, res_id, event, severity='info',
                  proposed_date=None, previous_date=None, reason=None,
                  rule_refs=None, res_name=None, company_id=None):
        """Append one immutable audit row, hash-chained per company.

        :param str res_model:  technical name of the governed record
        :param int res_id:     id of the governed record (0 if not yet created)
        :param str event:      one of the event selection values
        :param str severity:   info | warning | critical
        :param res.company company_id:  company (defaults to current company)
        :return: the created audit log record
        """
        company = company_id or self.env.company
        last = self.sudo().search(
            [('company_id', '=', company.id)], order='id desc', limit=1,
        )
        previous_hash = last.row_hash if last else 'GENESIS'
        payload = self._canonical_payload(
            company_id=company.id,
            user_id=self.env.user.id,
            res_model=res_model,
            res_id=res_id,
            event=event,
            severity=severity,
            proposed_date=str(proposed_date) if proposed_date else '',
            previous_date=str(previous_date) if previous_date else '',
            reason=reason or '',
            rule_refs=rule_refs or '',
        )
        row_hash = hashlib.sha256(
            (previous_hash + payload).encode('utf-8'),
        ).hexdigest()
        return self.sudo().create({
            'res_model': res_model,
            'res_id': res_id,
            'res_name': res_name,
            'company_id': company.id,
            'event': event,
            'severity': severity,
            'user_id': self.env.user.id,
            'proposed_date': proposed_date,
            'previous_date': previous_date,
            'reason': reason,
            'rule_refs': rule_refs,
            'previous_hash': previous_hash,
            'row_hash': row_hash,
        })
