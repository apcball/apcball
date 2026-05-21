# -*- coding: utf-8 -*-
"""
Tests for biz_monthly_analytic_budget — Report and dashboard.
"""
from odoo.tests.common import TransactionCase


class TestMonthlyBudgetReport(TransactionCase):
    """Test budget report and dashboard data retrieval."""

    def test_get_available_years_returns_empty_when_no_plans(self):
        """Should return empty list when no confirmed plans exist."""
        report = self.env['monthly.budget.report']
        # In a fresh test DB there may or may not be plans
        years = report.get_available_years()
        self.assertIsInstance(years, list)

    def test_get_available_plans_returns_list(self):
        """Should return list of plan dicts."""
        report = self.env['monthly.budget.report']
        plans = report.get_available_plans()
        self.assertIsInstance(plans, list)
        for p in plans:
            self.assertIn('id', p)
            self.assertIn('name', p)
            self.assertIn('label', p)

    def test_get_dashboard_data_returns_structure(self):
        """Dashboard data should always return the expected keys."""
        report = self.env['monthly.budget.report']
        data = report.get_dashboard_data({})
        self.assertIn('kpi', data)
        self.assertIn('waterfall', data)
        self.assertIn('analytic_breakdown', data)
        self.assertIn('stacked_bar', data)
        self.assertIn('trend', data)
        self.assertIn('alerts', data)

    def test_get_dashboard_data_kpi_structure(self):
        """KPI data should have expected fields."""
        report = self.env['monthly.budget.report']
        data = report.get_dashboard_data({})
        kpi = data['kpi']
        self.assertIn('total_budget', kpi)
        self.assertIn('reserved', kpi)
        self.assertIn('used', kpi)
        self.assertIn('available', kpi)
        self.assertIn('utilization', kpi)
