"""Regression coverage for editable previews, file templates and shared validation."""
import base64
import io
from datetime import datetime

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase

from ..wizard.bsf_import_templates import build_template


@tagged('post_install', '-at_install')
class TestFinanceImportWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.other = cls.env['res.company'].create({'name': 'Import Other Company'})
        cls.env.user.company_ids |= cls.other
        cls.plan = cls.env['account.analytic.plan'].create({'name': 'Import Test Plan'})
        cls.analytic = cls.env['account.analytic.account'].create({
            'name': 'Import Centre', 'code': 'IMP001', 'plan_id': cls.plan.id,
            'company_id': cls.company.id})

    def wizard(self, kind='doc', text=None, **values):
        defaults = {'company_id': self.company.id}
        if kind == 'fact':
            defaults['date'] = '2026-01-31'
        if kind == 'tb':
            defaults.update(date_from='2026-01-01', date_to='2026-01-31')
        if text is not None:
            defaults.update(file_data=base64.b64encode(text.encode()), file_name='input.csv')
        defaults.update(values)
        return self.env['biz.smart.finance.%s.import' % kind].create(defaults)

    def test_edit_invalid_preview_then_import(self):
        w = self.wizard(text='number,date,amount_total,amount_residual\nEDIT-1,2026-01-01,100,-50\n')
        w.action_preview()
        self.assertEqual(w.error_count, 1)
        w.line_ids.amount_residual = 50
        self.assertEqual(w.error_count, 0)
        w.action_validate()
        self.assertEqual(w.line_ids.amount_residual, 50)
        w.action_import()
        doc = self.env['biz.smart.finance.ext.invoice'].search([('number', '=', 'EDIT-1')])
        self.assertEqual(doc.amount_residual, 50)

    def test_parse_errors_preserve_other_values_and_explicit_zero(self):
        w = self.wizard(text='number,date,amount_total,amount_residual\nBAD-DATE,wrong,100,abc\n')
        w.action_preview()
        self.assertEqual(w.line_ids.amount_total, 100)
        self.assertEqual(w.error_count, 1)
        w.line_ids.date = '2026-01-01'
        self.assertEqual(w.error_count, 1)
        with self.assertRaises(UserError):
            w.action_import()
        w.line_ids.write({'amount_residual': 0})
        self.assertEqual(w.error_count, 0)
        w.action_import()

    def test_valid_preview_becomes_invalid_and_duplicates(self):
        w = self.wizard('fact', 'kind,amount\ninventory,100\n')
        w.action_preview()
        self.assertEqual(w.valid_count, 1)
        w.line_ids.amount = float('inf')
        self.assertEqual(w.error_count, 1)
        with self.assertRaises(UserError):
            w.action_import()
        w.line_ids.amount = 100
        w.write({'line_ids': [fields.Command.create({'kind': 'inventory', 'metric_key': 'inventory_value', 'amount': 200})]})
        self.assertEqual(w.error_count, 1)
        w.line_ids[-1].unlink()
        self.assertEqual(w.error_count, 0)

    def test_tb_live_totals_and_new_accounts(self):
        w = self.wizard('tb', 'code,account_type,debit,credit\n000TEST,asset_cash,100,0\n')
        w.action_preview()
        self.assertEqual(w.new_account_count, 1)
        w.line_ids.debit = 250
        self.assertEqual(w.dr_total, 250)
        self.assertEqual(w.diff, 250)
        w.action_validate()
        self.assertEqual(w.line_ids.debit, 250)
        action = w.action_import()
        gl = self.env['biz.smart.finance.ext.gl'].browse(action['res_id'])
        self.assertEqual(gl.state, 'draft')
        with self.assertRaises(ValidationError):
            gl.action_post()
        gl.line_ids.credit = 250
        gl.action_post()
        self.assertEqual(gl.state, 'posted')

    def test_file_change_and_mode_change_discard_preview(self):
        w = self.wizard(text='number,date,amount_total,amount_residual\nOLD,2026-01-01,100,100\n')
        w.action_preview()
        w.file_data = base64.b64encode(b'number,date,amount_total,amount_residual\nNEW,2026-01-01,200,200\n')
        self.assertFalse(w.line_ids)
        self.assertEqual(w.state, 'draft')
        with self.assertRaises(UserError):
            w.action_import()
        w.action_preview()
        self.assertEqual(w.line_ids.number, 'NEW')
        w.mode = 'budget'
        self.assertFalse(w.line_ids)

    def test_company_context_and_analytic_scope(self):
        self.env['account.analytic.account'].create({
            'name': self.analytic.name, 'code': self.analytic.code, 'plan_id': self.plan.id,
            'company_id': self.other.id})
        w = self.wizard(text='analytic,date_from,date_to,amount\nIMP001,2026-01-01,2026-01-31,100\n', mode='budget')
        w = w.with_context(allowed_company_ids=[self.company.id, self.other.id])
        w.action_preview()
        self.assertEqual(w.line_ids.analytic_account_id, self.analytic)
        self.assertEqual(w.error_count, 0)
        w.company_id = self.other
        self.assertEqual(w.error_count, 1)
        with self.assertRaises(UserError):
            w.action_import()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['biz.smart.finance.ext.budget'].create({
                'company_id': self.other.id, 'analytic_account_id': self.analytic.id,
                'date_from': '2026-01-01', 'date_to': '2026-01-31', 'amount': 100})

    def test_shared_partner_and_manual_import_parity(self):
        partner = self.env['res.partner'].create({'name': 'Import Shared Partner', 'company_id': False})
        w = self.wizard(text='number,partner,date,amount_total,amount_residual\nCREDIT-1,Import Shared Partner,2026-01-01,-100,-50\n')
        w.action_preview()
        self.assertEqual(w.line_ids.partner_id, partner)
        w.action_import()
        model = self.env['biz.smart.finance.ext.invoice']
        imported = model.search([('number', '=', 'CREDIT-1')])
        with Form(model) as form:
            form.number = 'CREDIT-MANUAL'
            form.partner_id = partner
            form.date = fields.Date.to_date('2026-01-01')
            form.amount_total = -100
            form.amount_residual = -50
        manual = form.record
        for name in ('partner_name', 'partner_id', 'date', 'date_due', 'amount_total', 'amount_residual'):
            self.assertEqual(imported[name], manual[name])

    def test_bad_headers_extra_cells_and_nonfinite(self):
        for text in ('amount,amount\n1,2\n', 'amount\n1,2\n', 'amount,unknown\n1,2\n'):
            with self.subTest(text=text), self.assertRaises(UserError):
                self.wizard('fact', text).action_preview()
        for value in ('NaN', 'inf', '-Infinity'):
            w = self.wizard('fact', 'kind,amount\ninventory,%s\n' % value)
            w.action_preview()
            self.assertEqual(w.error_count, 1)
            with self.assertRaises(UserError):
                w.action_import()

    def test_real_excel_dates_and_account_codes(self):
        from openpyxl import Workbook
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(['number', 'date', 'amount_total', 'amount_residual'])
        sheet.append(['000123', datetime(2026, 1, 15), 100, 50])
        stream = io.BytesIO()
        workbook.save(stream)
        workbook.close()
        w = self.wizard(file_name='dates.xlsx', file_data=base64.b64encode(stream.getvalue()))
        w.action_preview()
        self.assertEqual(w.line_ids.number, '000123')
        self.assertEqual(w.line_ids.date, fields.Date.to_date('2026-01-15'))
        self.assertEqual(w.error_count, 0)

    def test_corrupt_files(self):
        for name, data in [('broken.xlsx', b'not zip'), ('broken.csv', b'\xff\xfe'), ('old.xls', b'data')]:
            with self.subTest(name=name), self.assertRaises(UserError):
                self.wizard(file_name=name, file_data=base64.b64encode(data)).action_preview()

    def test_all_templates_roundtrip_and_download(self):
        for kind, mode in [('fact', None), ('doc', 'invoice'), ('doc', 'budget'), ('tb', None)]:
            for extension in ('csv', 'xlsx'):
                with self.subTest(kind=kind, mode=mode, extension=extension):
                    w = self.wizard(kind, **({'mode': mode} if mode else {}))
                    content, name = build_template(w, extension)
                    w.write({'file_name': name, 'file_data': base64.b64encode(content)})
                    w.action_preview()
                    self.assertEqual(w.error_count, 0, w.line_ids.mapped('warning'))
                    if kind == 'tb':
                        self.assertEqual(w.line_ids[0].code, '001001')
                    action = w._download_template(extension)
                    self.assertIn('download=true', action['url'])
                    self.assertTrue(w.template_data)
                    w.action_import()

    def test_replace_and_atomic_failure(self):
        w = self.wizard(text='number,date,amount_total,amount_residual\nREPLACE-1,2026-01-01,100,100\n')
        w.action_preview()
        w.action_import()
        w.line_ids.amount_residual = 50
        w.action_import()
        model = self.env['biz.smart.finance.ext.invoice']
        doc = model.search([('number', '=', 'REPLACE-1')])
        self.assertEqual(len(doc), 1)
        self.assertEqual(doc.amount_residual, 50)
        rows = [{'doc_type': 'ar', 'number': 'REPLACE-1', 'partner_name': 'X',
                 'date': '2026-01-01', 'amount_total': 100, 'amount_residual': 10},
                {'doc_type': 'ar', 'number': 'BAD-2', 'partner_name': 'X',
                 'date': '2026-01-01', 'amount_total': 100, 'amount_residual': 200}]
        with self.assertRaises(ValidationError):
            model.upsert_invoices(self.company, rows, source='import')
        self.assertTrue(doc.exists())
        self.assertEqual(doc.amount_residual, 50)
        self.assertFalse(model.search([('number', '=', 'BAD-2')]))

    def test_preview_onchange_updates_summary(self):
        w = self.wizard('tb', 'code,account_type,debit,credit\nONCHANGE,asset_cash,100,0\n')
        w.action_preview()
        with Form(w) as form:
            with form.line_ids.edit(0) as line:
                line.debit = 345
            self.assertEqual(form.dr_total, 345)
        self.assertEqual(w.dr_total, 345)

    def test_form_add_remove_and_company_period_edits(self):
        w = self.wizard('tb', 'code,account_type,debit,credit\nFORM-ADD,asset_cash,100,0\n')
        w.action_preview()
        with Form(w) as form:
            with form.line_ids.new() as line:
                line.code = 'FORM-CREDIT'
                line.account_type = 'income'
                line.credit = 100
            self.assertEqual(form.diff, 0)
            self.assertEqual(form.valid_count, 2)
            form.line_ids.remove(1)
            self.assertEqual(form.diff, 100)
            self.assertEqual(form.valid_count, 1)
            form.date_to = fields.Date.to_date('2025-12-31')
            self.assertEqual(form.error_count, 1)
        with self.assertRaises(UserError):
            w.action_import()

    def test_fact_and_budget_manual_import_parity(self):
        for kind, model_name, kwargs in [
                ('fact', 'biz.smart.finance.ext.fact', {}),
                ('doc', 'biz.smart.finance.ext.budget', {'mode': 'budget'})]:
            w = self.wizard(kind, **kwargs)
            content, name = build_template(w, 'csv')
            w.write({'file_data': base64.b64encode(content), 'file_name': name})
            w.action_preview()
            w.action_import()
            model = self.env[model_name]
            domain = [('company_id', '=', self.company.id), ('source', '=', 'import')]
            imported = model.search(domain, limit=1)
            self.assertTrue(imported)
            names = ('kind', 'metric_key', 'label', 'amount', 'qty') if kind == 'fact' else ('analytic_account_id', 'amount')
            values = {key: imported[key].id if model._fields[key].type == 'many2one' else imported[key] for key in names}
            values['company_id'] = self.company.id
            if kind == 'fact':
                values['date'] = '2026-02-28'
            else:
                values.update(date_from='2026-02-01', date_to='2026-02-28')
            manual = model.create(values)
            for key in names:
                self.assertEqual(manual[key], imported[key])

    def test_foreign_partner_and_gl_account_blocked(self):
        partner = self.env['res.partner'].create({'name': 'Other Partner', 'company_id': self.other.id})
        w = self.wizard(text='number,date,amount_total,amount_residual\nOTHER,2026-01-01,100,100\n')
        w.action_preview()
        w.line_ids.partner_id = partner
        self.assertEqual(w.error_count, 1)
        with self.assertRaises(UserError):
            w.action_import()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['biz.smart.finance.ext.invoice'].create({
                'company_id': self.company.id, 'doc_type': 'ar', 'number': 'OTHER', 'partner_name': 'Other Partner',
                'partner_id': partner.id, 'date': '2026-01-01', 'amount_total': 100, 'amount_residual': 100})
        account = self.env['biz.smart.finance.ext.account'].create({
            'company_id': self.other.id, 'name': 'Foreign Account', 'code': 'FOREIGN', 'account_type': 'asset_cash'})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['biz.smart.finance.ext.gl'].create({
                'company_id': self.company.id, 'date_from': '2026-01-01', 'date_to': '2026-01-31',
                'line_ids': [fields.Command.create({'ext_account_id': account.id, 'debit': 100})]})

    def test_xlsx_formula_and_invalid_selection_remain_errors(self):
        from openpyxl import Workbook
        workbook = Workbook()
        workbook.active.append(['kind', 'amount'])
        workbook.active.append(['inventory', '=1+1'])
        stream = io.BytesIO()
        workbook.save(stream)
        workbook.close()
        with self.assertRaises(UserError):
            self.wizard('fact', file_data=base64.b64encode(stream.getvalue()), file_name='formula.xlsx').action_preview()
        w = self.wizard('fact', 'kind,metric_key,amount\nwrong,inventory_value,100\n')
        w.action_preview()
        self.assertEqual(w.error_count, 1)
        self.assertEqual(w.line_ids.amount, 100)
        w.action_validate()
        self.assertEqual(w.error_count, 1)
        w.line_ids.kind = 'inventory'
        self.assertEqual(w.error_count, 0)
        w.action_import()
