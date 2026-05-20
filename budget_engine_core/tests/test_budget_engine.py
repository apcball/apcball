# -*- coding: utf-8 -*-
from unittest.mock import Mock, patch

from odoo.tests.common import TransactionCase


class TestBudgetEngine(TransactionCase):

    def test_reserve_budget_creates_reserved_commitment(self):
        engine = self.env['budget.engine']
        commitment_model = self.env['budget.commitment']
        created = Mock()

        with patch.object(type(engine), '_validate_context', return_value=None):
            with patch.object(type(commitment_model), 'sudo', return_value=commitment_model) as sudo_mock:
                with patch.object(type(commitment_model), 'create', return_value=created) as create_mock:
                    result = engine.reserve_budget({
                        'budget_source': 'monthly',
                        'document_model': 'purchase.order',
                        'document_id': 42,
                        'amount': 123.45,
                        'company_id': self.env.company.id,
                        'date': self.env.context.get('date') or None,
                    })

        sudo_mock.assert_called_once()
        create_mock.assert_called_once()
        self.assertIs(result, created)
        self.assertEqual(create_mock.call_args.args[0]['state'], 'reserved')

    def test_consume_budget_marks_existing_reservation_used(self):
        engine = self.env['budget.engine']
        commitment_model = self.env['budget.commitment']
        existing = Mock()

        with patch.object(type(engine), '_validate_context', return_value=None):
            with patch.object(type(commitment_model), 'sudo', return_value=commitment_model) as sudo_mock:
                with patch.object(type(commitment_model), 'search', return_value=existing) as search_mock:
                    result = engine.consume_budget({
                        'budget_source': 'monthly',
                        'document_model': 'purchase.order',
                        'document_id': 42,
                        'amount': 123.45,
                        'company_id': self.env.company.id,
                    })

        sudo_mock.assert_called_once()
        search_mock.assert_called_once()
        existing.action_mark_used.assert_called_once()
        self.assertIs(result, existing)

    def test_consume_budget_creates_used_when_no_reservation_exists(self):
        engine = self.env['budget.engine']
        commitment_model = self.env['budget.commitment']
        created = Mock()

        with patch.object(type(engine), '_validate_context', return_value=None):
            with patch.object(type(commitment_model), 'sudo', return_value=commitment_model) as sudo_mock:
                with patch.object(type(commitment_model), 'search', return_value=False):
                    with patch.object(type(commitment_model), 'create', return_value=created) as create_mock:
                        result = engine.consume_budget({
                            'budget_source': 'monthly',
                            'document_model': 'purchase.order',
                            'document_id': 42,
                            'amount': 123.45,
                            'company_id': self.env.company.id,
                        })

        self.assertEqual(sudo_mock.call_count, 2)
        create_mock.assert_called_once()
        self.assertIs(result, created)
        self.assertEqual(create_mock.call_args.args[0]['state'], 'used')

    def test_release_budget_releases_existing_commitments(self):
        engine = self.env['budget.engine']
        commitment_model = self.env['budget.commitment']
        existing = Mock()

        with patch.object(type(engine), '_validate_context', return_value=None):
            with patch.object(type(commitment_model), 'sudo', return_value=commitment_model) as sudo_mock:
                with patch.object(type(commitment_model), 'search', return_value=existing) as search_mock:
                    result = engine.release_budget({
                        'budget_source': 'monthly',
                        'document_model': 'purchase.order',
                        'document_id': 42,
                        'amount': 0,
                        'company_id': self.env.company.id,
                    })

        sudo_mock.assert_called_once()
        search_mock.assert_called_once()
        existing.action_release.assert_called_once()
        self.assertIs(result, existing)
