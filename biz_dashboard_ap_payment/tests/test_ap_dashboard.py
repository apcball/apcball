# -*- coding: utf-8 -*-
"""Engine tests for biz.ap.dashboard.

The test DB is the shared dev database, so every assertion is a
baseline-delta: capture the payload before creating fixtures, then assert the
difference. Fixtures use the far-future period YEAR-03 / YEAR-04 so they do
not collide with real data (except approval requests, whose create_date is
server-set, so those use the current month and their own baseline).
"""
import json
import xml.etree.ElementTree as ElementTree
import zipfile
from datetime import date
from io import BytesIO

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase

SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
# three years ahead: inside monthly.budget.plan's year selection (today +/-5) and
# far from real data
YEAR, MONTH = fields.Date.today().year + 3, 3


def D(month, day):
    return '%04d-%02d-%02d' % (YEAR, month, day)


class TestApDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # buz_partner_required_fields blocks bare test partners / users
        cls.env = cls.env(context=dict(
            cls.env.context, skip_partner_required_fields=True))
        env = cls.env
        if 'buz.accounting.date.company.policy' in env:
            # test data sits ~3 years ahead; rolled back with the test transaction
            env['buz.accounting.date.company.policy'].sudo().search(
                [('company_id', '=', env.company.id)]).write({'max_future_days': 2000})
        cls.company = env.company
        cls.currency = cls.company.currency_id
        Users = env['res.users']
        cls.plain_user = Users.create({
            'name': 'APD Plain', 'login': 'apd_plain_user',
            'groups_id': [(6, 0, [env.ref('base.group_user').id])],
            'company_id': cls.company.id,
            'company_ids': [(6, 0, [cls.company.id])],
        })
        cls.viewer = Users.create({
            'name': 'APD Viewer', 'login': 'apd_viewer_user',
            'groups_id': [(6, 0, [
                env.ref('base.group_user').id,
                env.ref('biz_monthly_analytic_budget.group_monthly_budget_user').id,
            ])],
            'company_id': cls.company.id,
            'company_ids': [(6, 0, [cls.company.id])],
        })
        cls.engine = env['biz.ap.dashboard'].with_user(cls.viewer)
        cls.F = {'month': MONTH, 'year': YEAR, 'company_id': cls.company.id}
        cls.baseline = cls.engine.get_dashboard_data(cls.F)

        # --- master data -------------------------------------------------
        cls.analytic_plan = env['account.analytic.plan'].create({'name': 'APD Plan'})
        cls.analytic = env['account.analytic.account'].create({
            'name': 'APD Analytic', 'company_id': cls.company.id,
            'plan_id': cls.analytic_plan.id})
        cls.plans = env['monthly.budget.plan']
        for month in ('2', '3', '4', '5'):
            plan = env['monthly.budget.plan'].create({
                'month': month, 'year': str(YEAR),
                'total_budget': 100000000.0,
                'company_id': cls.company.id,
            })
            env['monthly.budget.line'].create({
                'plan_id': plan.id, 'analytic_account_id': cls.analytic.id,
                'percentage': 100.0,
            })
            plan.action_confirm()
            cls.plans |= plan

        Term = env['account.payment.term']
        cls.term_now = Term.create({
            'name': 'APD Immediate', 'company_id': cls.company.id,
            'line_ids': [(0, 0, {'value': 'percent', 'value_amount': 100, 'nb_days': 0,
                                 'delay_type': 'days_after'})],
        })
        cls.term_30 = Term.create({
            'name': 'APD 30 Days', 'company_id': cls.company.id,
            'line_ids': [(0, 0, {'value': 'percent', 'value_amount': 100, 'nb_days': 30,
                                 'delay_type': 'days_after'})],
        })
        cls.term_eom = Term.create({
            'name': 'APD End of Month', 'company_id': cls.company.id,
            'line_ids': [(0, 0, {'value': 'percent', 'value_amount': 100, 'nb_days': 0,
                                 'delay_type': 'days_after_end_of_month'})],
        })
        Partner = env['res.partner']
        cls.v1 = Partner.create({'name': 'APD Vendor One', 'supplier_rank': 1, 'is_company': True})
        cls.v2 = Partner.create({'name': 'APD Vendor Two', 'supplier_rank': 1, 'is_company': True})
        Project = env['project.project']
        cls.p1 = cls._project('APD Project One')
        cls.p2 = cls._project('APD Project Two')
        if not (cls.p1 and cls.p2):
            # stale NOT NULL column (billing_type) from an uninstalled module can
            # block creation on the shared dev DB -> reuse existing projects
            existing = Project.search(
                [('company_id', 'in', [cls.company.id, False])], order='id', limit=2)
            cls.p1 = existing[:1] or None
            cls.p2 = existing[1:2] or None
        cls.baseline_p1 = (
            cls.engine.get_dashboard_data(dict(cls.F, project_id=cls.p1.id)) if cls.p1 else None)
        Categ = env['product.category']
        cls.c1 = Categ.create({'name': 'APD Categ One'})
        cls.c2 = Categ.create({'name': 'APD Categ Two'})
        Product = env['product.product']
        cls.prod1 = Product.create({
            'name': 'APD Product One', 'type': 'consu', 'categ_id': cls.c1.id,
            'purchase_method': 'purchase', 'standard_price': 100.0,
        })
        cls.prod2 = Product.create({
            'name': 'APD Product Two', 'type': 'consu', 'categ_id': cls.c2.id,
            'purchase_method': 'purchase', 'standard_price': 100.0,
        })
        cls.tax7 = env['account.tax'].create({
            'name': 'APD VAT 7%', 'amount': 7.0, 'amount_type': 'percent',
            'type_tax_use': 'purchase', 'company_id': cls.company.id,
        })

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @classmethod
    def _project(cls, name):
        try:
            with cls.env.cr.savepoint():
                return cls.env['project.project'].create({
                    'name': name, 'company_id': cls.company.id})
        except Exception:  # noqa: BLE001 - leftover DB constraint, see setUpClass
            return None

    @classmethod
    def _bill(cls, vendor, invoice_date, amount, term=None, due=None, project=None,
              refund=False, lines=None, taxes=None):
        vals = {
            'move_type': 'in_refund' if refund else 'in_invoice',
            'partner_id': vendor.id,
            'company_id': cls.company.id,
            'invoice_date': invoice_date,
            'invoice_payment_term_id': term.id if term else False,
            'project_id': project.id if project else False,
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id, 'name': product.name, 'quantity': 1,
                'price_unit': price,
                'tax_ids': [(6, 0, taxes.ids)] if taxes else [(5, 0, 0)],
            }) for product, price in (lines or [(cls.prod1, amount)])],
        }
        if due and not term:
            vals['invoice_date_due'] = due
        bill = cls.env['account.move'].create(vals)
        cls._fill_tax_invoice(bill, invoice_date)
        bill.action_post()
        return bill

    @staticmethod
    def _fill_tax_invoice(bill, invoice_date):
        # l10n_th_account_tax blocks posting purchase VAT lines without a tax invoice
        if 'tax_invoice_ids' in bill._fields and bill.tax_invoice_ids:
            bill.tax_invoice_ids.write({
                'tax_invoice_number': 'APD-TI-%d' % bill.id,
                'tax_invoice_date': invoice_date,
            })

    @classmethod
    def _po(cls, vendor, payment_date, amount, term=None, project=None, taxes=None,
            lines=None, confirm=True):
        po = cls.env['purchase.order'].create({
            'partner_id': vendor.id,
            'company_id': cls.company.id,
            'payment_date': payment_date,
            'payment_term_id': term.id if term else False,
            'project_id': project.id if project else False,
            'order_line': [(0, 0, {
                'product_id': product.id, 'name': product.name, 'product_qty': 1,
                'price_unit': price, 'date_planned': fields.Date.today(),
                    'analytic_distribution': {str(cls.analytic.id): 100.0},
                'taxes_id': [(6, 0, taxes.ids)] if taxes else [(5, 0, 0)],
            }) for product, price in (lines or [(cls.prod1, amount)])],
        })
        if confirm:
            po.approval_state = 'approved'
            po.button_confirm()
        return po

    def _data(self, **extra):
        return self.engine.get_dashboard_data(dict(self.F, **extra))

    @staticmethod
    def _row(payload, tab, key):
        for row in payload['tables'][tab]['rows']:
            if row['key'] == key:
                return row
        return None

    def _row_value(self, payload, tab, key, field):
        row = self._row(payload, tab, key)
        return row[field] if row else 0.0

    def _delta_row(self, payload, tab, key, field):
        return self._row_value(payload, tab, key, field) - self._row_value(self.baseline, tab, key, field)

    def _delta(self, payload, *path):
        new = payload
        old = self.baseline
        for step in path:
            new = new[step]
            old = old[step]
        return new - old

    # ------------------------------------------------------------------
    # tests
    # ------------------------------------------------------------------
    def test_access_gate(self):
        with self.assertRaises(AccessError):
            self.env['biz.ap.dashboard'].with_user(self.plain_user).get_dashboard_data(self.F)
        other = self.env['res.company'].search([('id', '!=', self.company.id)], limit=1)
        if other:
            with self.assertRaises(AccessError):
                self.engine.get_dashboard_data(dict(self.F, company_id=other.id))
        self.assertEqual(self.baseline['filters']['company_id'], self.company.id)

    def test_is_cash_term(self):
        is_cash = self.env['biz.ap.dashboard']._is_cash_term
        self.assertTrue(is_cash(False))
        self.assertTrue(is_cash(self.term_now))
        self.assertFalse(is_cash(self.term_30))
        self.assertFalse(is_cash(self.term_eom))
        self.assertTrue(is_cash(self.term_30, date(2031, 3, 10), date(2031, 3, 10)))
        self.assertFalse(is_cash(self.term_30, date(2031, 3, 10), date(2031, 4, 9)))

    def test_pure_helpers(self):
        engine = self.env['biz.ap.dashboard']
        self.assertEqual([engine._week_index(d) for d in (1, 7, 8, 14, 15, 21, 22, 31)],
                         [0, 0, 1, 1, 2, 2, 3, 3])
        self.assertEqual(engine._month_range(2031, 2), (date(2031, 2, 1), date(2031, 2, 28)))
        self.assertEqual(engine._next_month(2031, 12), (2032, 1))
        self.assertEqual(engine._next_month(2031, 3), (2031, 4))

    def test_month_bucketing_cash_credit(self):
        self._bill(self.v1, D(3, 5), 1000.0, term=self.term_now)      # cash, week 1
        self._bill(self.v1, D(2, 18), 2000.0, term=self.term_30)       # due 2031-03-20, credit, week 3
        self._bill(self.v2, D(3, 31), 500.0, due=D(3, 31), refund=True)  # cash refund, week 4
        self._bill(self.v2, D(2, 10), 700.0, due=D(2, 28))         # previous month: excluded
        payload = self._data()
        self.assertAlmostEqual(self._delta(payload, 'kpi_payment', 'total'), 2500.0, places=2)
        self.assertAlmostEqual(self._delta(payload, 'kpi_payment', 'cash'), 500.0, places=2)
        self.assertAlmostEqual(self._delta(payload, 'kpi_payment', 'credit'), 2000.0, places=2)
        self.assertEqual(self._delta(payload, 'kpi_payment', 'count'), 3)
        weekly = payload['weekly']
        base = self.baseline['weekly']
        self.assertAlmostEqual(weekly[0]['cash'] - base[0]['cash'], 1000.0, places=2)
        self.assertAlmostEqual(weekly[2]['credit'] - base[2]['credit'], 2000.0, places=2)
        self.assertAlmostEqual(weekly[3]['cash'] - base[3]['cash'], -500.0, places=2)
        self.assertEqual(len(weekly), 4)
        self.assertEqual(weekly[0]['range'], '1-7 มี.ค.')
        self.assertEqual(weekly[3]['range'], '22-31 มี.ค.')
        self.assertEqual(payload['filters']['month_label'], 'มีนาคม %d' % YEAR)
        self.assertEqual(payload['filters']['next_month_label'], 'เมษายน %d' % YEAR)

    def test_paid_and_residual(self):
        journal = self.env['account.journal'].search(
            [('type', 'in', ('bank', 'cash')), ('company_id', '=', self.company.id)], limit=1)
        if not journal:
            self.skipTest('No bank/cash journal in the test company')
        bill = self._bill(self.v1, D(2, 18), 2000.0, term=self.term_30)
        self._bill(self.v1, D(3, 12), 300.0, term=self.term_now)
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=bill.ids).create({
                'journal_id': journal.id, 'payment_date': D(3, 20),
                'cheque_amount': 0.0,
            })
        wizard.action_create_payments()
        payload = self._data()
        self.assertAlmostEqual(self._delta(payload, 'kpi_payment', 'paid'), 2000.0, places=2)
        self.assertAlmostEqual(self._delta(payload, 'kpi_payment', 'residual'), 300.0, places=2)
        key = 'p:%d' % self.v1.id
        self.assertAlmostEqual(self._delta_row(payload, 'vendor', key, 'month_paid'), 2000.0, places=2)
        self.assertAlmostEqual(self._delta_row(payload, 'vendor', key, 'month_residual'), 300.0, places=2)

    def test_vendor_rows_and_donut(self):
        self._bill(self.v1, D(3, 3), 1500.0, term=self.term_now)
        self._bill(self.v2, D(3, 4), 900.0, term=self.term_now)
        payload = self._data()
        k1, k2 = 'p:%d' % self.v1.id, 'p:%d' % self.v2.id
        self.assertAlmostEqual(self._delta_row(payload, 'vendor', k1, 'month_total'), 1500.0, places=2)
        self.assertAlmostEqual(self._delta_row(payload, 'vendor', k2, 'month_total'), 900.0, places=2)
        self.assertEqual(self._row(payload, 'vendor', k1)['name'], 'APD Vendor One')
        rows = payload['tables']['vendor']['rows']
        self.assertEqual([r['seq'] for r in rows], list(range(1, len(rows) + 1)))
        footer = payload['tables']['vendor']['footer']
        self.assertEqual(footer['name'], 'รวมทั้งสิ้น')
        self.assertAlmostEqual(
            footer['month_total'] - self.baseline['tables']['vendor']['footer']['month_total'],
            2400.0, places=2)
        self.assertAlmostEqual(footer['month_total'], payload['kpi_payment']['total'], places=2)
        share = payload['vendor_share']
        self.assertAlmostEqual(share['total'], payload['kpi_payment']['total'], places=2)
        self.assertLessEqual(len(share['items']), 6)
        if share['items']:
            self.assertAlmostEqual(sum(i['amount'] for i in share['items']),
                                   sum(r['month_total'] for r in rows if r['month_total'] > 0), places=2)
        # filter by vendor: only that vendor's rows remain
        only_v2 = self._data(partner_id=self.v2.id)
        self.assertAlmostEqual(only_v2['kpi_payment']['total'], 900.0, places=2)
        self.assertEqual([r['key'] for r in only_v2['tables']['vendor']['rows'] if r['month_total']], [k2])

    def test_project_filter_and_tab(self):
        if not (self.p1 and self.p2):
            self.skipTest('Need two projects')
        self._bill(self.v1, D(3, 6), 1000.0, term=self.term_now, project=self.p1)
        self._bill(self.v1, D(3, 7), 2000.0, term=self.term_now, project=self.p2)
        self._bill(self.v2, D(3, 8), 400.0, term=self.term_now)
        payload = self._data()
        self.assertAlmostEqual(self._delta_row(payload, 'project', 'p:%d' % self.p1.id, 'month_total'), 1000.0, places=2)
        self.assertAlmostEqual(self._delta_row(payload, 'project', 'p:%d' % self.p2.id, 'month_total'), 2000.0, places=2)
        self.assertAlmostEqual(self._delta_row(payload, 'project', 'none', 'month_total'), 400.0, places=2)
        self.assertEqual(self._row(payload, 'project', 'none')['name'], 'ไม่ระบุโครงการ')
        only_p1 = self._data(project_id=self.p1.id)
        self.assertAlmostEqual(
            only_p1['kpi_payment']['total'] - self.baseline_p1['kpi_payment']['total'], 1000.0, places=2)
        self.assertEqual(only_p1['filters']['project_id'], self.p1.id)

    def test_category_tab_balances(self):
        self._bill(self.v1, D(3, 9), 0.0, term=self.term_now,
                   lines=[(self.prod1, 1000.0), (self.prod2, 500.0)], taxes=self.tax7)
        payload = self._data()
        c1, c2 = 'cat:%d' % self.c1.id, 'cat:%d' % self.c2.id
        self.assertAlmostEqual(self._delta_row(payload, 'category', c1, 'month_total'), 1000.0, places=2)
        self.assertAlmostEqual(self._delta_row(payload, 'category', c2, 'month_total'), 500.0, places=2)
        self.assertAlmostEqual(self._delta_row(payload, 'category', 'tax', 'month_total'), 105.0, places=2)
        self.assertAlmostEqual(self._delta(payload, 'kpi_payment', 'total'), 1605.0, places=2)
        footer = payload['tables']['category']['footer']
        self.assertAlmostEqual(footer['month_total'], payload['kpi_payment']['total'], places=2)
        self.assertAlmostEqual(footer['month_cash'], payload['kpi_payment']['cash'], places=2)

    def test_po_budget_columns(self):
        po = self._po(self.v1, D(3, 10), 10000.0, term=self.term_now, taxes=self.tax7, project=self.p1)
        self.assertEqual(po.state, 'purchase')
        payload = self._data()
        key = 'p:%d' % self.v1.id
        self.assertAlmostEqual(self._delta_row(payload, 'vendor', key, 'budget_approved'), 10700.0, places=2)
        self.assertAlmostEqual(self._delta_row(payload, 'vendor', key, 'budget_used'), 0.0, places=2)
        self.assertAlmostEqual(self._delta_row(payload, 'vendor', key, 'budget_remaining'), 10700.0, places=2)
        if self.p1:
            # project budget columns come from monthly.budget.line, not the PO
            self.assertAlmostEqual(self._delta_row(payload, 'project', 'p:%d' % self.p1.id, 'budget_approved'), 0.0, places=2)
        self.assertAlmostEqual(self._delta_row(payload, 'category', 'cat:%d' % self.c1.id, 'budget_approved'), 10700.0, places=2)

        # bill the PO in full -> used = approved, remaining = 0
        po.with_context(default_invoice_date=D(3, 10)).action_create_invoice()
        bill = po.invoice_ids[:1]
        self.assertTrue(bill)
        bill.write({'invoice_date': D(3, 10)})
        self._fill_tax_invoice(bill, D(3, 10))
        bill.action_post()
        self.assertAlmostEqual(self.engine._po_unbilled(po), 0.0, places=2)
        payload = self._data()
        self.assertAlmostEqual(self._delta_row(payload, 'vendor', key, 'budget_used'), 10700.0, places=2)
        self.assertAlmostEqual(self._delta_row(payload, 'vendor', key, 'budget_remaining'), 0.0, places=2)
        row = self._row(payload, 'vendor', key)
        self.assertAlmostEqual(row['budget_pct'], 100.0 * row['budget_used'] / row['budget_approved'], places=1)
        # the bill itself is due in March -> month_total also moved
        self.assertAlmostEqual(self._delta_row(payload, 'vendor', key, 'month_total'), 10700.0, places=2)

    def test_forecast_next_month(self):
        self._bill(self.v1, D(3, 11), 3000.0, term=self.term_30)          # due 2031-04-10, credit, unpaid
        self._po(self.v1, D(4, 20), 4000.0, term=self.term_now)            # unbilled, cash, week 3
        self._po(self.v2, D(4, 2), 1000.0, term=self.term_30, confirm=False)  # draft: excluded
        payload = self._data()
        self.assertAlmostEqual(self._delta(payload, 'kpi_forecast', 'total'), 7000.0, places=2)
        self.assertAlmostEqual(self._delta(payload, 'kpi_forecast', 'cash'), 4000.0, places=2)
        self.assertAlmostEqual(self._delta(payload, 'kpi_forecast', 'credit'), 3000.0, places=2)
        self.assertAlmostEqual(self._delta(payload, 'kpi_forecast', 'from_bills'), 3000.0, places=2)
        self.assertAlmostEqual(self._delta(payload, 'kpi_forecast', 'from_po'), 4000.0, places=2)
        fw, base = payload['forecast_weekly'], self.baseline['forecast_weekly']
        self.assertAlmostEqual(fw[1]['credit'] - base[1]['credit'], 3000.0, places=2)
        self.assertAlmostEqual(fw[2]['cash'] - base[2]['cash'], 4000.0, places=2)
        self.assertEqual(fw[3]['range'], '22-30 เม.ย.')
        key = 'p:%d' % self.v1.id
        self.assertAlmostEqual(self._delta_row(payload, 'vendor', key, 'next_total'), 7000.0, places=2)
        self.assertAlmostEqual(self._delta_row(payload, 'vendor', key, 'next_cash'), 4000.0, places=2)
        self.assertAlmostEqual(self._delta_row(payload, 'category', 'cat:%d' % self.c1.id, 'next_total'), 7000.0, places=2)
        # March KPI must not include next-month items
        self.assertAlmostEqual(self._delta(payload, 'kpi_payment', 'total'), 0.0, places=2)

    def test_budget_plan_kpi(self):
        payload = self._data()
        budget = payload['kpi_budget']
        # the two confirmed plans created in setUpClass (100M, March) are visible
        self.assertGreaterEqual(budget['approved'] - self.baseline['kpi_budget']['approved'], 100000000.0 - 0.01)
        self.assertAlmostEqual(
            budget['remaining'], budget['approved'] - budget['reserved'] - budget['used'], places=2)
        self.assertTrue(budget['scope_note'])
        # project / vendor filters do not change the plan-level KPI
        filtered = self._data(partner_id=self.v1.id)
        self.assertAlmostEqual(filtered['kpi_budget']['approved'], budget['approved'], places=2)

    def test_budget_kpi_includes_closed_plan(self):
        plan = self.plans[-1]  # month 5
        f = dict(self.F, month=5)
        confirmed = self.engine.get_dashboard_data(f)['kpi_budget']
        self.assertGreaterEqual(confirmed['approved'], 100000000.0 - 0.01)
        plan.action_close()
        self.assertEqual(plan.state, 'closed')
        closed = self.engine.get_dashboard_data(f, refresh=True)['kpi_budget']
        self.assertAlmostEqual(closed['approved'], confirmed['approved'], places=2)
        self.assertEqual(closed['plan_count'], confirmed['plan_count'])

    def test_budget_line_project_and_category(self):
        if not self.p1:
            self.skipTest('no project available on this DB')
        plan = self.plans[1]
        self.env['monthly.budget.line'].create({
            'plan_id': plan.id, 'analytic_account_id': self.analytic.id,
            'project_id': self.p1.id, 'category': 'capex', 'percentage': 1.0,  # 1% of 100M
        })
        payload = self._data(project_id=self.p1.id)
        base = self.baseline_p1['kpi_budget']
        self.assertAlmostEqual(payload['kpi_budget']['approved'] - base['approved'], 1000000.0, places=2)
        row = self._row(payload, 'project', 'p:%d' % self.p1.id)
        self.assertTrue(row and row['budget_approved'] >= 1000000.0 - 0.01)
        cat = self._row(payload, 'category', 'budget:capex')
        self.assertTrue(cat and cat['budget_approved'] >= 1000000.0 - 0.01)

    def test_approval_requests(self):
        today = fields.Date.today()
        f_now = {'month': today.month, 'year': today.year, 'company_id': self.company.id}
        before = self.engine.get_dashboard_data(f_now)
        po = self._po(self.v1, D(3, 15), 100.0, project=self.p1, confirm=False)
        Request = self.env['buz.monthly.budget.approval.request']
        reqs = Request
        for overage in (100.0, 200.0, 300.0):
            reqs |= Request.create({
                'document_type': 'po', 'ref_po_id': po.id,
                'amount_requested': overage, 'amount_overage': overage + 1000.0,  # cumulative line overrun, not summed
                'company_id': self.company.id,
            })
        reqs[1].write({'state': 'approved'})
        reqs[2].write({'state': 'rejected'})
        after = self.engine.get_dashboard_data(f_now)
        req = after['kpi_request']
        base = before['kpi_request']
        self.assertAlmostEqual(req['pending']['amount'] - base['pending']['amount'], 100.0, places=2)
        self.assertAlmostEqual(req['approved']['amount'] - base['approved']['amount'], 200.0, places=2)
        self.assertAlmostEqual(req['rejected']['amount'] - base['rejected']['amount'], 300.0, places=2)
        self.assertAlmostEqual(req['total'] - base['total'], 600.0, places=2)
        self.assertEqual(req['pending']['count'] - base['pending']['count'], 1)

        def row_val(payload, tab, key, field):
            row = self._row(payload, tab, key)
            return row[field] if row else 0.0
        key = 'p:%d' % self.v1.id
        self.assertAlmostEqual(
            row_val(after, 'vendor', key, 'req_approved') - row_val(before, 'vendor', key, 'req_approved'),
            200.0, places=2)
        if self.p1:
            self.assertAlmostEqual(
                row_val(after, 'project', 'p:%d' % self.p1.id, 'req_rejected')
                - row_val(before, 'project', 'p:%d' % self.p1.id, 'req_rejected'), 300.0, places=2)
        # vendor filter on another vendor excludes these requests entirely
        other = self.engine.get_dashboard_data(dict(f_now, partner_id=self.v2.id))
        self.assertAlmostEqual(other['kpi_request']['total'], 0.0, places=2)

    def test_approval_request_po_currency_converted(self):
        # amount_requested of a PO request is in the PO currency, not company currency
        usd = self.env.ref('base.USD')
        foreign = usd if usd != self.currency else self.env.ref('base.EUR')
        rate = self.env['res.currency.rate'].create({
            'currency_id': foreign.id, 'company_id': self.company.id,
            'name': fields.Date.today(), 'rate': 0.5,  # 1 company currency = 0.5 foreign
        })
        self.assertTrue(rate)
        today = fields.Date.today()
        f_now = {'month': today.month, 'year': today.year, 'company_id': self.company.id}
        before = self.engine.get_dashboard_data(f_now)
        po = self._po(self.v1, D(3, 15), 100.0, project=self.p1, confirm=False)
        po.currency_id = foreign
        self.env['buz.monthly.budget.approval.request'].create({
            'document_type': 'po', 'ref_po_id': po.id,
            'amount_requested': 100.0, 'company_id': self.company.id,
        })
        after = self.engine.get_dashboard_data(f_now)
        # 100 foreign units at 0.5 foreign per company unit = 200 company currency
        self.assertAlmostEqual(
            after['kpi_request']['pending']['amount'] - before['kpi_request']['pending']['amount'],
            200.0, places=2)

    def test_payload_shape_and_serializable(self):
        payload = self._data()
        json.dumps(payload)
        for key in ('filters', 'currency', 'as_of', 'updated_at', 'options', 'kpi_payment',
                    'kpi_budget', 'kpi_request', 'kpi_forecast', 'weekly', 'forecast_weekly',
                    'vendor_share', 'tables', 'tabs'):
            self.assertIn(key, payload)
        self.assertEqual(len(payload['weekly']), 4)
        self.assertEqual(len(payload['forecast_weekly']), 4)
        self.assertEqual([t['id'] for t in payload['tabs']], ['vendor', 'project', 'category'])
        expected = {'seq', 'id', 'key', 'name', 'budget_pct',
                    'month_total', 'month_cash', 'month_credit', 'month_paid', 'month_residual',
                    'budget_approved', 'budget_used', 'budget_remaining',
                    'req_pending', 'req_approved', 'req_rejected',
                    'next_total', 'next_cash', 'next_credit'}
        for tab in ('vendor', 'project', 'category'):
            table = payload['tables'][tab]
            for row in table['rows']:
                self.assertEqual(set(row), expected)
            self.assertEqual(set(table['footer']), expected)
        self.assertEqual(len(payload['options']['months']), 12)
        self.assertIn(YEAR, payload['options']['years'])
        self.assertTrue(any(c['id'] == self.company.id for c in payload['options']['companies']))
        # unknown / 'all' filter values fall back gracefully
        fallback = self.engine.get_dashboard_data({'month': 'all', 'year': 'x', 'company_id': 'all'})
        self.assertEqual(fallback['filters']['month'], fields.Date.today().month)
        self.assertFalse(fallback['filters']['company_id'])

    def test_cache(self):
        from odoo.addons.biz_dashboard_ap_payment.models import ap_dashboard
        ap_dashboard.clear_cache()
        self.addCleanup(ap_dashboard.clear_cache)
        cached_engine = self.engine.with_context(ap_dashboard_cache=True)
        first = cached_engine.get_dashboard_data(self.F)
        self.assertFalse(first['from_cache'])
        self.assertGreater(first['cache_ttl'], 0)
        self._bill(self.v1, D(3, 5), 1000.0, term=self.term_now)
        second = cached_engine.get_dashboard_data(self.F)
        self.assertTrue(second['from_cache'])
        self.assertAlmostEqual(second['kpi_payment']['total'], first['kpi_payment']['total'], places=2)
        # other filters are a different entry; refresh recomputes and replaces
        other = cached_engine.get_dashboard_data(dict(self.F, partner_id=self.v1.id))
        self.assertFalse(other['from_cache'])
        fresh = cached_engine.get_dashboard_data(self.F, refresh=True)
        self.assertFalse(fresh['from_cache'])
        self.assertAlmostEqual(
            fresh['kpi_payment']['total'] - first['kpi_payment']['total'], 1000.0, places=2)
        again = cached_engine.get_dashboard_data(self.F)
        self.assertTrue(again['from_cache'])
        self.assertAlmostEqual(again['kpi_payment']['total'], fresh['kpi_payment']['total'], places=2)
        # the access gate still runs on a cache hit
        with self.assertRaises(AccessError):
            self.env['biz.ap.dashboard'].with_user(self.plain_user).with_context(
                ap_dashboard_cache=True).get_dashboard_data(self.F)
        # disabled by system parameter
        self.env['ir.config_parameter'].sudo().set_param(ap_dashboard.CACHE_TTL_PARAM, '0')
        self.assertFalse(cached_engine.get_dashboard_data(self.F)['from_cache'])
        # tests never use the cache unless they opt in
        self.assertFalse(self.engine.get_dashboard_data(self.F)['from_cache'])

    # ------------------------------------------------------------------
    # export
    # ------------------------------------------------------------------
    def _sheet_names(self, content):
        book = zipfile.ZipFile(BytesIO(content))
        return [
            sheet.get('name')
            for sheet in ElementTree.fromstring(book.read('xl/workbook.xml')).iter('%ssheet' % SHEET_NS)
        ]

    def test_export_xlsx(self):
        self._bill(self.v1, D(3, 5), 1000.0, term=self.term_now)
        content = self.engine.build_export(self.F, 'all')
        self.assertTrue(content.startswith(b'PK'))
        self.assertEqual(self._sheet_names(content), ['สรุป', 'ร้านค้า', 'โครงการ', 'หมวดค่าใช้จ่าย'])
        self.assertEqual(self._sheet_names(self.engine.build_export(self.F, 'vendor')), ['สรุป', 'ร้านค้า'])
        self.assertEqual(self._sheet_names(self.engine.build_export(self.F, 'category')),
                         ['สรุป', 'หมวดค่าใช้จ่าย'])
        with self.assertRaises(ValueError):
            self.engine.build_export(self.F, 'bogus')
        with self.assertRaises(AccessError):
            self.env['biz.ap.dashboard'].with_user(self.plain_user).build_export(self.F, 'all')
