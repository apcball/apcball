# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo import fields


class TestBudgetCommitment(TransactionCase):
    """Test budget.commitment model — state transitions, computed fields."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def _create_commitment(self, **overrides):
        vals = {
            'budget_source': 'monthly',
            'document_model': 'test.document',
            'document_id': 1,
            'amount': 100.0,
            'state': 'reserved',
            'date': fields.Date.today(),
            'company_id': self.company.id,
        }
        vals.update(overrides)
        return self.env['budget.commitment'].sudo().create(vals)

    # ── create generates sequence ────────────────────────────────

    def test_create_generates_name(self):
        c = self._create_commitment()
        self.assertNotEqual(c.name, 'New')
        self.assertTrue(c.name)

    # ── state transitions ────────────────────────────────────────

    def test_action_mark_used(self):
        c = self._create_commitment(state='reserved')
        c.action_mark_used()
        self.assertEqual(c.state, 'used')

    def test_action_mark_used_skips_non_reserved(self):
        c = self._create_commitment(state='used')
        c.action_mark_used()
        # Already used, should stay used
        self.assertEqual(c.state, 'used')

    def test_action_release_from_reserved(self):
        c = self._create_commitment(state='reserved')
        c.action_release()
        self.assertEqual(c.state, 'released')

    def test_action_release_from_used(self):
        c = self._create_commitment(state='used')
        c.action_release()
        self.assertEqual(c.state, 'released')

    def test_action_release_skips_already_released(self):
        c = self._create_commitment(state='released')
        c.action_release()
        self.assertEqual(c.state, 'released')

    # ── document_ref compute ─────────────────────────────────────

    def test_document_ref_empty_for_fake_model(self):
        c = self._create_commitment(document_model='fake.model', document_id=99999)
        self.assertFalse(c.document_ref)

    def test_document_ref_empty_when_no_model(self):
        c = self._create_commitment()
        c.write({'document_model': False})
        self.assertFalse(c.document_ref)

    # ── action_open_document ──────────────────────────────────────

    def test_action_open_document_returns_action(self):
        partner = self.env['res.partner'].create({'name': 'Test'})
        c = self._create_commitment(document_model='res.partner', document_id=partner.id)
        action = c.action_open_document()
        self.assertEqual(action['res_model'], 'res.partner')
        self.assertEqual(action['res_id'], partner.id)

    def test_action_open_document_returns_none_when_no_model(self):
        c = self._create_commitment()
        c.write({'document_model': False})
        self.assertFalse(c.action_open_document())
