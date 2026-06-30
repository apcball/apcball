# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests.common import tagged


@tagged('post_install', '-at_install')
class TestBackdateSmoke(TransactionCase):
    """Smoke test for the accounting-date governance spine.

    Exercises the MVP slice of Phase 2:
      * BR-P04  fail-closed without a policy
      * BR-B01  back-day ceiling (block + allow)
      * BR-F01  future-day ceiling (block)
      * BR-L01  audit-log row written on governed create
      * BR-L02  audit log immutability (write / unlink forbidden)
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Policy = cls.env['buz.accounting.date.company.policy']
        cls.policy = cls.Policy.search(
            [('company_id', '=', cls.company.id)], limit=1,
        )
        if cls.policy:
            cls.policy.write({'max_back_days': 5, 'max_future_days': 5})
        else:
            cls.policy = cls.Policy.create({
                'name': 'TEST POLICY',
                'company_id': cls.company.id,
                'max_back_days': 5,
                'max_future_days': 5,
            })
        cls.journal = cls.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', cls.company.id)],
            limit=1,
        )
        if not cls.journal:
            cls.journal = cls.env['account.journal'].create({
                'name': 'Test Sales',
                'code': 'TSL',
                'type': 'sale',
                'company_id': cls.company.id,
            })
        cls.partner = cls.env['res.partner'].create({'name': 'Smoke Partner'})

    def _move_vals(self, date):
        return {
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
            'date': date,
            'invoice_line_ids': [(0, 0, {
                'name': 'smoke line',
                'quantity': 1,
                'price_unit': 100.0,
            })],
        }

    # -- BR-P04: fail-closed without a policy ------------------------
    def test_01_fail_closed_without_policy(self):
        self.policy.write({'active': False})
        today = fields.Date.context_today(self.env['account.move'])
        with self.assertRaises(UserError):
            self.env['account.move'].create(self._move_vals(today))

    # -- BR-B01 allow: back-date within ceiling ----------------------
    def test_02_backdate_within_policy_ok(self):
        today = fields.Date.context_today(self.env['account.move'])
        ok_date = today - timedelta(days=3)
        move = self.env['account.move'].create(self._move_vals(ok_date))
        self.assertEqual(move.date, ok_date)
        log = self.env['buz.accounting.date.audit.log'].sudo().search([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', move.id),
            ('event', '=', 'create'),
        ])
        self.assertTrue(log, 'Audit log row must be written on governed create.')

    # -- BR-B01 block: back-date beyond ceiling ----------------------
    def test_03_backdate_exceeds_policy_blocked(self):
        today = fields.Date.context_today(self.env['account.move'])
        bad_date = today - timedelta(days=10)
        with self.assertRaises(UserError):
            self.env['account.move'].create(self._move_vals(bad_date))

    # -- BR-F01 block: future-date beyond ceiling --------------------
    def test_04_future_date_exceeds_policy_blocked(self):
        today = fields.Date.context_today(self.env['account.move'])
        bad_date = today + timedelta(days=10)
        with self.assertRaises(UserError):
            self.env['account.move'].create(self._move_vals(bad_date))

    # -- BR-L02: audit log immutability ------------------------------
    def test_05_audit_log_immutable(self):
        today = fields.Date.context_today(self.env['account.move'])
        move = self.env['account.move'].create(self._move_vals(today))
        log = self.env['buz.accounting.date.audit.log'].sudo().search([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', move.id),
        ], limit=1)
        self.assertTrue(log, 'Audit log row must exist for the created move.')
        with self.assertRaises(UserError):
            log.write({'reason': 'tamper attempt'})
        with self.assertRaises(UserError):
            log.unlink()
