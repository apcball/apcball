import base64
import io
from datetime import date
from unittest.mock import patch
from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged
from ..models.bsf_cost_math import cost_metrics, normalized_savings


@tagged('post_install', '-at_install')
class TestBsfStrategy(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'CFO Test Company'})
        cls.other = cls.env['res.company'].create({'name': 'CFO Other Company'})
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=[cls.company.id]))
        cls.Period = cls.env['biz.smart.finance.cost.period']
        cls.Action = cls.env['biz.smart.finance.action']
        cls.Scenario = cls.env['biz.smart.finance.cost.scenario']
        cls.month = date(2026, 8, 1)
        def user(login, groups, company):
            return cls.env['res.users'].with_context(no_reset_password=True).create({
                'name': login, 'login': login, 'email': login + '@example.invalid', 'notification_type': 'inbox', 'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
                'groups_id': [(6, 0, [cls.env.ref('base.group_user').id] + [cls.env.ref('biz_smart_finance.' + g).id for g in groups])]})
        cls.manager = user('bsf_strategy_manager', ['group_bsf_manager'], cls.company)
        cls.owner = user('bsf_strategy_owner', ['group_bsf_action_owner'], cls.company)
        cls.viewer = user('bsf_strategy_viewer', ['group_bsf_user'], cls.company)
        cls.stranger = user('bsf_strategy_stranger', ['group_bsf_action_owner'], cls.company)
        cls.forecast = {'months': [
            {'label': 'Aug', 'date_from': '2026-08-01', 'is_tail': False},
            {'label': 'Sep', 'date_from': '2026-09-01', 'is_tail': False},
            {'label': 'หลังจากนี้', 'date_from': '2026-10-01', 'is_tail': True}],
            'cash': {'closing': [100, 200, 250], 'min_cash': 50}}

    def period(self, sales=10000000, variable=6000000, fixed=5000000, month=None, company=None):
        return self.Period.create({'company_id': (company or self.company).id, 'month': month or self.month,
            'complete': True, 'line_ids': [
                (0, 0, {'name': 'Sales', 'category': 'sales', 'amount': sales, 'fixed_pct': 0}),
                (0, 0, {'name': 'Variable', 'category': 'material', 'amount': variable, 'fixed_pct': 0}),
                (0, 0, {'name': 'Salary', 'category': 'salary', 'amount': fixed, 'fixed_pct': 100})]})

    def action(self):
        return self.Action.create({'name': 'Reduce OT', 'company_id': self.company.id, 'owner_id': self.owner.id,
            'instructions': 'จัดตาราง OT และรักษากำลังบริการ', 'due_date': date(2026, 8, 31)})

    def scenario(self, period):
        return self.Scenario.create({'name': 'Mixed', 'company_id': self.company.id, 'base_period_id': period.id,
            'start_month': self.month, 'assumptions': 'กำลังผลิตคงเดิม คุณภาพไม่ลด', 'months': 3})

    def forecast_patch(self):
        return patch.object(type(self.env['biz.smart.finance.dashboard']), 'get_forecast_data', return_value={'forecast': self.forecast})

    def test_break_even_and_target(self):
        p = self.period()
        m = p._metrics()
        self.assertEqual(m['contribution_pct'], 40)
        self.assertEqual(m['break_even'], 12500000)
        self.assertEqual(m['operating_profit'], -1000000)
        p.target_profit = 1000000
        self.assertEqual(p._metrics()['target_sales'], 15000000)
        p.line_ids.filtered(lambda l: l.category == 'salary').amount = 4000000
        self.assertEqual(p._metrics()['break_even'], 10000000)

    def test_invalid_calculations(self):
        for sales, variable, complete in [(0, 0, True), (10, 12, True), (10, 10, True), (10, 6, False)]:
            result = cost_metrics(sales, variable, 5, complete=complete)
            self.assertIsNone(result['break_even'])
            self.assertTrue(result['reason'])
        self.assertEqual(cost_metrics(10, 6, 5, one_off=1)['break_even'], 15)

    def test_mixed_cost_personnel_interest_and_tax(self):
        p = self.period()
        self.env['biz.smart.finance.cost.line'].create([
            {'period_id': p.id, 'name': 'OT mixed', 'category': 'ot', 'amount': 100, 'fixed_pct': 25},
            {'period_id': p.id, 'name': 'Interest', 'category': 'interest', 'amount': 999},
            {'period_id': p.id, 'name': 'Tax', 'category': 'tax', 'amount': 99},
            {'period_id': p.id, 'name': 'Once', 'category': 'other', 'amount': 20, 'one_off': True}])
        m = p._metrics()
        self.assertEqual(m['fixed'], 5000025)
        self.assertEqual(m['variable'], 6000075)
        self.assertEqual(m['one_off'], 20)
        self.assertEqual(m['personnel'], 5000100)
        self.assertEqual(m['interest_tax'], 1098)

    def test_confirmation_and_revision_lock(self):
        p = self.period()
        p.with_user(self.manager).action_confirm()
        for record, vals in [(p, {'target_profit': 1}), (p.line_ids[:1], {'amount': 1})]:
            with self.assertRaises(UserError): record.write(vals)
        with self.assertRaises(AccessError): p.write({'state': 'draft'})
        with self.assertRaises(UserError): p.line_ids.unlink()
        with self.assertRaises(UserError):
            self.env['biz.smart.finance.cost.line'].create({'period_id': p.id, 'name': 'Bypass', 'category': 'other', 'amount': 1})
        revised = self.Period.browse(p.action_revision()['res_id'])
        revised.complete = True
        revised.action_confirm()
        self.assertEqual(p.state, 'superseded')
        self.assertEqual(revised.state, 'confirmed')
        with self.assertRaises(UserError): self.period().action_confirm()

    def test_department_and_staffing(self):
        p = self.period()
        dept = self.env['biz.smart.finance.cost.department'].create({'company_id': self.company.id, 'name': 'Sales', 'revenue_center': True})
        p.line_ids.write({'department_id': dept.id, 'allocation_complete': True})
        self.assertEqual(p._metrics(dept.id)['break_even'], p._metrics()['break_even'])
        dept.revenue_center = False
        self.assertIsNone(p._metrics(dept.id)['break_even'])
        self.env['biz.smart.finance.cost.staffing'].create({'period_id': p.id, 'department_id': dept.id, 'headcount': 10, 'fte': 8, 'complete': True})
        self.assertEqual(p._metrics()['sales_per_fte'], 1250000)

    def test_import_repeat_and_preview_validation(self):
        p = self.Period.create({'company_id': self.company.id, 'month': self.month})
        data = 'source_key,name,department,category,amount,fixed_pct,one_off,allocation_complete\na,Sales,,sales,100,0,0,1\nb,Salary,,salary,50,100,0,1\n'
        w = self.env['biz.smart.finance.cost.import'].create({'company_id': self.company.id, 'period_id': p.id, 'file_name': 'cost.csv', 'file_data': base64.b64encode(data.encode())})
        w.action_preview()
        self.assertEqual(w.error_count, 0)
        w.action_import()
        w.action_import()
        self.assertEqual(len(p.line_ids), 2)
        w.line_ids.filtered(lambda l: l.source_key == 'b').amount = -1
        with self.assertRaises(UserError): w.action_import()
        self.assertEqual(p.line_ids.filtered(lambda l: l.source_key == 'b').amount, 50)

    def test_xlsx_template_import(self):
        p = self.Period.create({'company_id': self.company.id, 'month': self.month})
        w = self.env['biz.smart.finance.cost.import'].create({'company_id': self.company.id, 'period_id': p.id})
        w.action_template_xlsx()
        w.write({'file_name': 'cost.xlsx', 'file_data': w.template_data})
        w.action_preview()
        self.assertEqual(w.error_count, 0)
        w.action_import()
        p.complete = True
        p.action_confirm()
        self.assertEqual(p._metrics()['break_even'], 12500000)

    def test_access_and_workflow(self):
        a = self.action()
        with self.assertRaises(AccessError): a.with_user(self.owner).write({'state': 'done'})
        with self.assertRaises(AccessError): a.with_user(self.owner).write({'owner_id': self.stranger.id})
        with self.assertRaises(AccessError): a.with_user(self.stranger).read(['name'])
        with self.assertRaises(AccessError): a.with_user(self.owner).read(['expected_saving'])
        with self.assertRaises(AccessError): self.env['biz.smart.finance.strategy.service'].with_user(self.owner).get_cost_data({})
        a.with_user(self.manager).action_submit()
        with self.assertRaises(AccessError): a.with_user(self.owner).action_approve()
        a.with_user(self.manager).action_approve()
        a.with_user(self.owner).action_start()
        a.with_user(self.owner).write({'progress': 80, 'result_evidence': 'หลักฐานตาราง OT และคุณภาพการส่งมอบ'})
        a.with_user(self.owner).action_verify()
        with self.assertRaises(UserError): a.with_user(self.manager).action_done()
        r = self.env['biz.smart.finance.action.review'].create({'action_id': a.id, 'month': self.month, 'evidence': 'ตรวจผล KPI ผ่าน ผลประหยัดยังไม่รับรู้'})
        r.with_user(self.manager).action_accept()
        a.with_user(self.manager).action_done()
        self.assertEqual(a.state, 'done')
        a.action_reopen(); a.action_approve(); a.action_start(); a.action_verify()
        with self.assertRaises(UserError): a.action_done()
        with self.assertRaises(AccessError): r.write({'accepted_saving': 999})

    def test_approved_plan_edits_require_review(self):
        a = self.action()
        a.action_submit(); a.action_approve()
        a.write({'instructions': 'Changed plan'})
        self.assertEqual(a.state, 'review')
        self.assertFalse(a.approved_by)

    def test_cross_company(self):
        p = self.period(company=self.other)
        with self.assertRaises(AccessError): p.with_user(self.manager).action_confirm()
        with self.assertRaises(AccessError):
            self.env['biz.smart.finance.strategy.service'].with_user(self.manager).get_cost_data({'company_id': self.other.id})

    def test_simulation_and_duplicate_reduction(self):
        p = self.period(); p.action_confirm()
        s = self.scenario(p)
        with self.forecast_patch():
            s.action_capture()
            line = p.line_ids.filtered(lambda l: l.category == 'salary')
            self.env['biz.smart.finance.cost.effect'].create({'scenario_id': s.id, 'source_line_id': line.id, 'monthly_saving': 1000000})
            s.one_time_cost = 100000
            s.action_simulate()
            self.assertEqual(s.result_json['after']['break_even'], 10000000)
            self.assertEqual(s.result_json['net_benefit'], 2900000)
            self.assertEqual(p.fixed, 5000000)
            self.env['biz.smart.finance.cost.effect'].create({'scenario_id': s.id, 'source_line_id': line.id, 'monthly_saving': 4500000})
            self.assertFalse(s.result_json)
            with self.assertRaises(UserError): s.action_simulate()

    def test_cash_timing_overflow_and_stale(self):
        p = self.period(); p.action_confirm()
        s = self.scenario(p)
        with self.forecast_patch():
            s.action_capture()
            self.env['biz.smart.finance.cost.cash.effect'].create([
                {'scenario_id': s.id, 'reference': 'old', 'month': self.month, 'delta': -50, 'note': 'เลื่อนเงินรับออก'},
                {'scenario_id': s.id, 'reference': 'new', 'month': date(2026, 12, 1), 'delta': 50, 'note': 'เงินรับใหม่'}])
            s.cash_complete = True
            s.action_simulate()
            cash = s.result_json['cash']
            self.assertEqual(cash['total_delta'], 0)
            self.assertEqual(cash['overflow_delta'], 50)
            self.assertEqual(cash['rows'][0]['after'], 50)
            self.assertEqual(cash['rows'][-1]['after'], 250)
        with patch.object(type(self.env['biz.smart.finance.dashboard']), 'get_forecast_data', return_value={'forecast': {}}):
            s.action_simulate()
            self.assertTrue(s.stale)
            self.assertFalse(s.result_json)

    def test_normalized_savings_and_double_acceptance(self):
        self.assertEqual(normalized_savings(100, 60, 20, 50, 30, 20), 0)
        self.assertIsNone(normalized_savings(0, 0, 0, 1, 0, 0))
        b = self.period(); b.action_confirm()
        actual = self.period(sales=5000000, variable=3000000, fixed=4000000, month=date(2026, 9, 1)); actual.action_confirm()
        a = self.action(); a.action_submit(); a.action_approve(); a.action_start()
        a.result_evidence = 'ต้นทุนลดลงพร้อมรักษาคุณภาพ'; a.action_verify()
        Review = self.env['biz.smart.finance.action.review']
        r = Review.create({'action_id': a.id, 'month': actual.month, 'base_period_id': b.id, 'actual_period_id': actual.id, 'evidence': 'ตรวจบัญชีและจัดสรรให้แผนนี้', 'accepted_saving': 1000000})
        self.assertEqual(r.raw_reduction, 4000000)
        self.assertEqual(r.normalized_saving, 1000000)
        r.action_accept()
        a2 = self.action(); a2.action_submit(); a2.action_approve(); a2.action_start(); a2.result_evidence = 'proof'; a2.action_verify()
        duplicate = Review.create({'action_id': a2.id, 'month': actual.month, 'base_period_id': b.id, 'actual_period_id': actual.id, 'evidence': 'duplicate', 'accepted_saving': 1})
        with self.assertRaises(UserError): duplicate.action_accept()

    def test_cost_rules_idempotent(self):
        p = self.period(); p.action_confirm()
        service = self.env['biz.smart.finance.strategy.service'].with_user(self.manager)
        with patch.object(type(service), '_operating_candidates', return_value=[]):
            service.action_evaluate({'company_id': self.company.id, 'year': 2026, 'month': 8})
            before = self.env['biz.smart.finance.issue'].search_count([('company_id', '=', self.company.id)])
            service.action_evaluate({'company_id': self.company.id, 'year': 2026, 'month': 8})
            self.assertEqual(before, self.env['biz.smart.finance.issue'].search_count([('company_id', '=', self.company.id)]))
            self.assertGreater(before, 0)

    def test_service_real_engine_and_empty_states(self):
        service = self.env['biz.smart.finance.strategy.service'].with_user(self.manager)
        data = service.get_cost_data({'company_id': self.company.id, 'year': 2026, 'month': 8})
        self.assertIsNone(data['companies'][0]['current'])
        p = self.period(); p.action_confirm()
        data = service.get_cost_data({'company_id': self.company.id, 'year': 2026, 'month': 8})
        self.assertEqual(data['companies'][0]['current']['break_even'], 12500000)
        service.action_evaluate({'company_id': self.company.id, 'year': 2026, 'month': 8})
        self.assertTrue(service.get_strategy_data({'company_id': self.company.id, 'year': 2026, 'month': 8})['issues'])

    def test_overdue_cron_no_duplicates(self):
        a = self.action(); a.action_submit(); a.action_approve()
        self.Action._cron_overdue()
        first = len(a.activity_ids)
        self.Action._cron_overdue()
        self.assertEqual(first, len(a.activity_ids))

    def test_context_default_cannot_add_confirmed_line(self):
        p = self.period(); p.action_confirm()
        with self.assertRaises(UserError):
            self.env['biz.smart.finance.cost.line'].with_context(default_period_id=p.id).create({'name': 'Bypass', 'category': 'other', 'amount': 10})

    def test_company_fiscal_year_and_currency(self):
        self.company.write({'fiscalyear_last_month': '3', 'fiscalyear_last_day': 31})
        p = self.period(month=date(2026, 4, 1)); p.action_confirm()
        service = self.env['biz.smart.finance.strategy.service'].with_user(self.manager)
        prior = self.period(month=date(2025, 4, 1)); prior.action_confirm()
        result = service.get_cost_data({'company_id': self.company.id, 'year': 2026, 'month': 1})
        self.assertEqual(result['companies'][0]['month'], '2025-04-01')
        self.assertEqual(result['companies'][0]['ytd']['sales'], 10000000)
        self.assertEqual(result['companies'][0]['currency'], self.company.currency_id.name)

    def test_external_reconciliation(self):
        p = self.period(sales=100, variable=50, fixed=50); p.action_confirm()
        self.env['biz.smart.finance.config'].create({'company_id': self.company.id, 'gl_source': 'external'})
        Account = self.env['biz.smart.finance.ext.account']
        income = Account.create({'company_id': self.company.id, 'code': 'QA4000', 'name': 'Sales', 'account_type': 'income'})
        expense = Account.create({'company_id': self.company.id, 'code': 'QA5000', 'name': 'Expense', 'account_type': 'expense'})
        gl = self.env['biz.smart.finance.ext.gl'].create({'company_id': self.company.id, 'date_from': self.month, 'date_to': date(2026,8,31), 'line_ids':[
            (0,0,{'ext_account_id': income.id, 'debit': 0, 'credit': 100}),
            (0,0,{'ext_account_id': expense.id, 'debit': 100, 'credit': 0})]})
        gl.action_post()
        result = self.env['biz.smart.finance.strategy.service'].with_user(self.manager).get_cost_data({'company_id': self.company.id, 'year':2026, 'month':8})
        reconciliation = result['companies'][0]['reconciliation']
        self.assertEqual(reconciliation['sales_difference'], 0)
        self.assertEqual(reconciliation['cost_difference'], 0)

    def test_shift_group_conserves_cash(self):
        p = self.period(); p.action_confirm(); s = self.scenario(p)
        with self.forecast_patch():
            s.action_capture()
            self.env['biz.smart.finance.cost.cash.effect'].create({'scenario_id':s.id,'reference':'move','shift_key':'invoice-1','month':self.month,'delta':-50,'note':'shift'})
            s.cash_complete=True
            with self.assertRaises(UserError): s.action_simulate()

    def test_alternative_actions_cannot_combine(self):
        p = self.period(); p.action_confirm(); s = self.scenario(p)
        with self.forecast_patch():
            s.action_capture()
            source = p.line_ids.filtered(lambda l:l.category=='salary')
            for action in (self.action(), self.action()):
                self.env['biz.smart.finance.cost.effect'].create({'scenario_id':s.id,'source_line_id':source.id,'action_id':action.id,'monthly_saving':100,'alternative_group':'staffing'})
            with self.assertRaises(UserError):s.action_simulate()

    def test_context_cannot_forge_confirmations(self):
        with self.assertRaises(AccessError):
            self.Period.with_context(default_state='confirmed').create({'company_id': self.company.id, 'month': self.month})
        with self.assertRaises(AccessError):
            self.Action.with_context(default_state='done').create({'company_id': self.company.id, 'name': 'Bypass', 'instructions': 'No', 'owner_id': self.owner.id})
        a = self.action()
        with self.assertRaises(AccessError):
            self.env['biz.smart.finance.action.review'].with_context(default_verified=True).create({'action_id': a.id, 'month': self.month, 'evidence': 'Bypass'})

    def test_forecast_currency_is_converted_to_cost_currency(self):
        p = self.period(); p.action_confirm(); s = self.scenario(p)
        other_currency = self.env.ref('base.EUR')
        payload = {'forecast': self.forecast, 'filters': {'currency': other_currency.name, 'as_of': '2026-08-31'}}
        with patch.object(type(self.env['biz.smart.finance.dashboard']), 'get_forecast_data', return_value=payload):
            with patch.object(type(other_currency), '_convert', return_value=2):
                s.action_capture()
                self.assertEqual(s.forecast_json['cash']['closing'], [200,400,500])
                self.assertEqual(s.forecast_json['cash_currency'], self.company.currency_id.name)
                self.assertEqual(s.forecast_json['source_forecast']['cash']['closing'], [100,200,250])
