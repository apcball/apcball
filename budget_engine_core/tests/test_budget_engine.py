# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo import fields


class TestBudgetEngineReal(TransactionCase):
    """Test budget.engine with real DB — no mocks."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.engine = cls.env['budget.engine']
        cls.company = cls.env.company

    def _ctx(self, **overrides):
        base = {
            'budget_source': 'monthly',
            'document_model': 'test.document',
            'document_id': 1,
            'amount': 100.0,
            'company_id': self.company.id,
            'date': fields.Date.today(),
        }
        base.update(overrides)
        return base

    # ── _validate_context ────────────────────────────────────────

    def test_validate_context_passes_with_all_required_keys(self):
        """Should not raise when all required keys present."""
        self.engine._validate_context(self._ctx())

    def test_validate_context_raises_on_missing_keys(self):
        """Should raise ValidationError when required keys are missing."""
        with self.assertRaises(ValidationError):
            self.engine._validate_context({'budget_source': 'monthly'})

    def test_validate_context_missing_amount(self):
        with self.assertRaises(ValidationError):
            self.engine._validate_context(self._ctx(amount=None))

    def test_validate_context_missing_company_id(self):
        with self.assertRaises(ValidationError):
            self.engine._validate_context(self._ctx(company_id=None))

    # ── check_budget ─────────────────────────────────────────────

    def test_check_budget_default_returns_true(self):
        """Default check_budget always returns True."""
        result = self.engine.check_budget(self._ctx())
        self.assertTrue(result)

    # ── reserve_budget ────────────────────────────────────────────

    def test_reserve_budget_creates_commitment(self):
        """reserve_budget should create a budget.commitment in state 'reserved'."""
        result = self.engine.reserve_budget(self._ctx())
        self.assertEqual(result.state, 'reserved')
        self.assertEqual(result.amount, 100.0)
        self.assertEqual(result.budget_source, 'monthly')
        self.assertEqual(result.document_model, 'test.document')
        self.assertEqual(result.document_id, 1)

    def test_reserve_budget_with_optional_fields(self):
        ctx = self._ctx(analytic_account_id=99, note='test note')
        result = self.engine.reserve_budget(ctx)
        self.assertEqual(result.analytic_account_id.id, 99)
        self.assertEqual(result.note, 'test note')

    # ── consume_budget ────────────────────────────────────────────

    def test_consume_budget_marks_existing_reservation(self):
        """If a reserved commitment exists, consume should mark it used."""
        reserved = self.engine.reserve_budget(self._ctx())
        result = self.engine.consume_budget(self._ctx())
        self.assertEqual(result.state, 'used')
        self.assertIn(reserved.id, result.ids)

    def test_consume_budget_creates_used_when_no_reservation(self):
        """If no reservation exists, consume should create a new 'used' commitment."""
        result = self.engine.consume_budget(self._ctx())
        self.assertEqual(result.state, 'used')
        self.assertEqual(result.amount, 100.0)

    # ── release_budget ────────────────────────────────────────────

    def test_release_budget_releases_reserved(self):
        """Should release a reserved commitment."""
        self.engine.reserve_budget(self._ctx())
        result = self.engine.release_budget(self._ctx())
        for rec in result:
            self.assertEqual(rec.state, 'released')

    def test_release_budget_releases_used(self):
        """Should release a used commitment."""
        self.engine.consume_budget(self._ctx())
        result = self.engine.release_budget(self._ctx())
        for rec in result:
            self.assertEqual(rec.state, 'released')

    def test_release_budget_nothing_to_release(self):
        """Should return empty when no matching commitments."""
        result = self.engine.release_budget(self._ctx(document_id=99999))
        self.assertFalse(result)

    # ── full lifecycle ────────────────────────────────────────────

    def test_full_lifecycle_reserve_consume_release(self):
        """reserve → used → released"""
        c = self.engine.reserve_budget(self._ctx())
        self.assertEqual(c.state, 'reserved')

        self.engine.consume_budget(self._ctx())
        c.invalidate_recordset(['state'])
        self.assertEqual(c.state, 'used')

        self.engine.release_budget(self._ctx())
        c.invalidate_recordset(['state'])
        self.assertEqual(c.state, 'released')

    def test_multiple_reservations_same_document(self):
        """Multiple reserves create multiple commitments."""
        self.engine.reserve_budget(self._ctx())
        self.engine.reserve_budget(self._ctx())
        count = self.env['budget.commitment'].sudo().search_count([
            ('document_model', '=', 'test.document'),
            ('document_id', '=', 1),
            ('state', '=', 'reserved'),
        ])
        self.assertEqual(count, 2)
