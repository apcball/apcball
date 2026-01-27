# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    is_clearing_entry = fields.Boolean(
        string='Is Clearing Entry', readonly=True,
        help='Indicates if this journal entry is a clearing entry for inter-customer payment'
    )
    clearing_payment_id = fields.Many2one(
        'account.payment', string='Clearing Payment', readonly=True,
        help='Payment that triggered this clearing entry'
    )


class AccountPartialReconcile(models.Model):
    _inherit = 'account.partial.reconcile'

    is_clearing_reconcile = fields.Boolean(
        string='Is Clearing Reconcile', readonly=True,
        help='Indicates if this reconciliation is part of inter-customer clearing'
    )
    clearing_payment_id = fields.Many2one(
        'account.payment', string='Clearing Payment', readonly=True,
        help='Payment that triggered this clearing reconciliation'
    )