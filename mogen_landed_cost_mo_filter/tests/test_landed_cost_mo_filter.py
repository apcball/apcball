from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestLandedCostMOFilter(TransactionCase):
    """Behavioural coverage for the landed-cost MO selection helper."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.LandedCost = cls.env['stock.landed.cost']
        cls.Production = cls.env['mrp.production']
        cls.Analytic = cls.env['account.analytic.account']
        cls.AnalyticPlan = cls.env['account.analytic.plan']
        cls.company = cls.env.company
        cls.product = cls.env['product.product'].create({
            'name': 'MO filter test product',
            'type': 'product',
        })
        cls.plan = cls.AnalyticPlan.create({'name': 'MO filter test plan'})
        cls.analytic_a = cls.Analytic.create({
            'name': 'MO filter group A',
            'company_id': cls.company.id,
            'plan_id': cls.plan.id,
        })
        cls.analytic_b = cls.Analytic.create({
            'name': 'MO filter group B',
            'company_id': cls.company.id,
            'plan_id': cls.plan.id,
        })

    def _production(self, name, analytic, state='done', finished='2026-07-15 08:00:00'):
        return self.Production.create({
            'name': name,
            'product_id': self.product.id,
            'product_qty': 1,
            'product_uom_id': self.product.uom_id.id,
            'company_id': self.company.id,
            'analytic_account_ids': [fields.Command.link(analytic.id)],
            'state': state,
            'date_finished': finished,
        })

    def _landed_cost(self, productions=None):
        values = {
            'company_id': self.company.id,
            'target_model': 'manufacturing',
        }
        if productions:
            values['mrp_production_ids'] = [
                fields.Command.link(production.id) for production in productions
            ]
        return self.LandedCost.create(values)

    def test_filter_by_analytic_account_and_date(self):
        selected = self._production('MO A', self.analytic_a)
        self._production('MO B', self.analytic_b)
        landed_cost = self._landed_cost()
        landed_cost.write({
            'mo_filter_analytic_account_id': self.analytic_a.id,
            'mo_filter_date_from': '2026-07-01',
            'mo_filter_date_to': '2026-07-31',
        })
        landed_cost.action_search_manufacturing_orders()
        self.assertEqual(landed_cost.mrp_production_ids, selected)

    def test_filter_excludes_other_dates_state_and_company(self):
        selected = self._production('MO in range', self.analytic_a, state='done')
        self._production('MO before range', self.analytic_a, finished='2026-06-30 08:00:00')
        self._production('MO after range', self.analytic_a, finished='2026-08-01 08:00:00')
        self._production('MO confirmed', self.analytic_a, state='confirmed')
        other_company = self.env['res.company'].search([
            ('id', '!=', self.company.id),
        ], limit=1)
        if not other_company:
            self.skipTest('DEV database has only one company')
        other_analytic = self.Analytic.create({
            'name': 'MO filter other company account',
            'company_id': other_company.id,
            'plan_id': self.plan.id,
        })
        self.Production.create({
            'name': 'MO other company',
            'product_id': self.product.id,
            'product_qty': 1,
            'product_uom_id': self.product.uom_id.id,
            'company_id': other_company.id,
            'analytic_account_ids': [fields.Command.link(other_analytic.id)],
            'state': 'done',
            'date_finished': '2026-07-15 08:00:00',
        })
        landed_cost = self._landed_cost()
        landed_cost.write({
            'mo_filter_analytic_account_id': self.analytic_a.id,
            'mo_filter_date_from': '2026-07-01',
            'mo_filter_date_to': '2026-07-31',
        })
        landed_cost.action_search_manufacturing_orders()
        self.assertEqual(landed_cost.mrp_production_ids, selected)

    def test_replace_and_add_modes_do_not_duplicate(self):
        old = self._production('MO old', self.analytic_a, finished='2026-06-15 08:00:00')
        new = self._production('MO new', self.analytic_a, finished='2026-07-20 08:00:00')
        landed_cost = self._landed_cost(old)
        landed_cost.write({
            'mo_filter_analytic_account_id': self.analytic_a.id,
            'mo_filter_date_from': '2026-07-01',
            'mo_filter_date_to': '2026-07-31',
            'mo_filter_mode': 'add',
        })
        landed_cost.action_search_manufacturing_orders()
        self.assertEqual(landed_cost.mrp_production_ids, new | old)
        landed_cost.mo_filter_mode = 'replace'
        landed_cost.action_search_manufacturing_orders()
        self.assertEqual(landed_cost.mrp_production_ids, new)

    def test_validation_errors(self):
        landed_cost = self._landed_cost()
        with self.assertRaises(UserError):
            landed_cost.action_search_manufacturing_orders()
        landed_cost.mo_filter_analytic_account_id = self.analytic_a
        with self.assertRaises(UserError):
            landed_cost.action_search_manufacturing_orders()
        landed_cost.mo_filter_date_from = '2026-08-01'
        landed_cost.mo_filter_date_to = '2026-07-01'
        with self.assertRaises(ValidationError):
            landed_cost.action_search_manufacturing_orders()

    def test_no_result_keeps_existing_orders(self):
        existing = self._production('MO existing', self.analytic_a)
        landed_cost = self._landed_cost(existing)
        landed_cost.write({
            'mo_filter_analytic_account_id': self.analytic_b,
            'mo_filter_date_from': '2026-07-01',
            'mo_filter_date_to': '2026-07-31',
        })
        result = landed_cost.action_search_manufacturing_orders()
        self.assertEqual(landed_cost.mrp_production_ids, existing)
        self.assertEqual(result['params']['type'], 'warning')

    def test_search_is_limited_to_draft_manufacturing_landed_costs(self):
        landed_cost = self._landed_cost()
        landed_cost.target_model = 'picking'
        landed_cost.write({
            'mo_filter_analytic_account_id': self.analytic_a.id,
            'mo_filter_date_from': '2026-07-01',
            'mo_filter_date_to': '2026-07-31',
        })
        with self.assertRaises(UserError):
            landed_cost.action_search_manufacturing_orders()

    def test_filter_view_uses_responsive_bootstrap_columns(self):
        """Keep filter controls readable at every supported form width."""
        view = self.env.ref(
            'mogen_landed_cost_mo_filter.view_mrp_landed_costs_form_inherit_mo_filter'
        )
        arch = view.arch_db
        self.assertIn('expr="//sheet/group[1]"', arch)
        self.assertIn('class="o_mo_filter"', arch)
        self.assertIn('class="row g-3"', arch)
        self.assertEqual(arch.count('class="col-12 col-lg-6"'), 5)
        self.assertIn(
            'class="col-12 col-lg-6 d-flex align-items-end justify-content-end"',
            arch,
        )
