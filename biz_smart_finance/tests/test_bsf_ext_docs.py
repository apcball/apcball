# -*- coding: utf-8 -*-
"""ข้อมูลภายนอกชุดที่สอง: ใบแจ้งหนี้/บิลค้าง (AR/AP) และงบศูนย์ต้นทุน

ทุก assert ตัวเลขทำบน**บริษัทที่สร้างใหม่** (ยอดตั้งต้นศูนย์) และคูณอัตรา
แลกเปลี่ยนของ engine เสมอ — dev DB ตั้งสกุลนำเสนอไว้คนละสกุลกับบริษัท"""
import base64
from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class ExtDocCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "BSF ExtDoc Co"})
        cls.env.user.company_ids = [(4, cls.company.id)]
        cls.Invoice = cls.env["biz.smart.finance.ext.invoice"]
        cls.Budget = cls.env["biz.smart.finance.ext.budget"]
        cls.engine = cls.env["biz.smart.finance.dashboard"]
        cls.today = fields.Date.context_today(cls.env.user)

    def _invoice(self, **vals):
        base = {
            "company_id": self.company.id,
            "doc_type": "ar",
            "number": "EXT-1",
            "partner_name": "ACME",
            "date": self.today,
            "amount_total": 100.0,
            "amount_residual": 100.0,
        }
        base.update(vals)
        return self.Invoice.create(base)


class TestBsfExtInvoiceModel(ExtDocCommon):
    def test_residual_cannot_exceed_total(self):
        with self.assertRaises(ValidationError):
            self._invoice(amount_total=100.0, amount_residual=150.0)

    def test_residual_sign_must_match_total(self):
        with self.assertRaises(ValidationError):
            self._invoice(amount_total=100.0, amount_residual=-50.0)

    def test_credit_note_allowed_when_both_negative(self):
        doc = self._invoice(
            number="CN-1", amount_total=-100.0, amount_residual=-100.0)
        self.assertEqual(doc.amount_residual, -100.0)

    def test_due_date_before_document_date_raises(self):
        with self.assertRaises(ValidationError):
            self._invoice(date_due=self.today - timedelta(days=1))

    def test_duplicate_number_per_type_raises(self):
        self._invoice(number="DUP-1")
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), \
                self.env.cr.savepoint():
            self._invoice(number="DUP-1")
            self.env.flush_all()

    def test_same_number_other_doc_type_is_fine(self):
        self._invoice(number="SAME-1", doc_type="ar")
        self._invoice(number="SAME-1", doc_type="ap")
        self.assertEqual(
            self.Invoice.search_count([
                ("company_id", "=", self.company.id),
                ("number", "=", "SAME-1"),
            ]), 2)

    def test_upsert_replaces_by_doc_type_and_number(self):
        rows = [{
            "doc_type": "ar", "number": "UP-1", "partner_name": "ACME",
            "date": self.today, "amount_total": 100.0,
            "amount_residual": 100.0,
        }]
        self.Invoice.upsert_invoices(self.company, rows, source="manual")
        rows[0]["amount_residual"] = 40.0
        self.Invoice.upsert_invoices(self.company, rows, source="api")
        docs = self.Invoice.search([("company_id", "=", self.company.id)])
        self.assertEqual(len(docs), 1, "upsert ต้องทับ ไม่ใช่เพิ่มซ้ำ")
        self.assertEqual(docs.amount_residual, 40.0)
        self.assertEqual(docs.source, "api")


class TestBsfExtBudgetModel(ExtDocCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plan = cls.env["account.analytic.plan"].search(
            [("parent_id", "=", False)], limit=1)
        cls.analytic = cls.env["account.analytic.account"].create({
            "name": "BSF Ext Cost Centre",
            "plan_id": cls.plan.id,
            "company_id": cls.company.id,
        })

    def test_reversed_range_raises(self):
        with self.assertRaises(ValidationError):
            self.Budget.create({
                "company_id": self.company.id,
                "analytic_account_id": self.analytic.id,
                "date_from": "2026-12-31", "date_to": "2026-01-01",
                "amount": 100.0,
            })

    def test_upsert_replaces_same_centre_and_range(self):
        rows = [{
            "analytic_account_id": self.analytic.id,
            "date_from": "2026-01-01", "date_to": "2026-12-31",
            "amount": 1000.0,
        }]
        self.Budget.upsert_budgets(self.company, rows, source="manual")
        rows[0]["amount"] = 2500.0
        self.Budget.upsert_budgets(self.company, rows, source="import")
        budgets = self.Budget.search([("company_id", "=", self.company.id)])
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets.amount, 2500.0)


class TestBsfExtDocsEngine(ExtDocCommon):
    """บริษัทที่ตั้งแหล่งใบแจ้งหนี้/งบเป็นระบบภายนอก — ตัวเลขต้องไหลถึงทุกแท็บ"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["biz.smart.finance.config"].create({
            "company_id": cls.company.id,
            "invoice_source": "external",
            "budget_source": "external",
        })
        cls.overdue = cls.Invoice.create({
            "company_id": cls.company.id, "doc_type": "ar",
            "number": "AR-OVERDUE", "partner_name": "ลูกค้าเก่า",
            "date": cls.today - cls._days(40), "date_due": cls.today - cls._days(10),
            "amount_total": 1000.0, "amount_residual": 1000.0,
        })
        cls.current = cls.Invoice.create({
            "company_id": cls.company.id, "doc_type": "ar",
            "number": "AR-CURRENT", "partner_name": "ลูกค้าใหม่",
            "date": cls.today, "date_due": cls.today + cls._days(20),
            "amount_total": 500.0, "amount_residual": 500.0,
        })
        cls.paid = cls.Invoice.create({
            "company_id": cls.company.id, "doc_type": "ar",
            "number": "AR-PAID", "partner_name": "ลูกค้าเก่า",
            "date": cls.today, "amount_total": 300.0, "amount_residual": 0.0,
        })
        cls.bill = cls.Invoice.create({
            "company_id": cls.company.id, "doc_type": "ap",
            "number": "AP-1", "partner_name": "ผู้ขาย ก",
            "date": cls.today - cls._days(5), "date_due": cls.today + cls._days(7),
            "amount_total": 700.0, "amount_residual": 700.0,
        })

    @staticmethod
    def _days(count):
        return timedelta(days=count)

    def _payload(self, **filters):
        return self.engine.get_dashboard_data(
            dict({"company_id": self.company.id}, **filters))

    def _rate(self, payload):
        as_of = fields.Date.to_date(payload["filters"]["as_of"])
        presentation = self.engine._presentation_currency(self.company)
        return self.engine._fx_rates(
            [self.company.id], as_of, presentation)[self.company.id]

    def test_ar_aging_uses_external_documents(self):
        payload = self._payload()
        rate = self._rate(payload)
        aging = payload["statements"]["ar_aging"]
        self.assertEqual(aging["source"], "external")
        self.assertAlmostEqual(aging["total"], 1500.0 * rate, places=2)
        self.assertAlmostEqual(
            aging["buckets"]["b1_30"], 1000.0 * rate, places=2)
        self.assertAlmostEqual(
            aging["buckets"]["current"], 500.0 * rate, places=2)
        # ใบที่ปิดแล้ว (residual 0) ต้องไม่โผล่ในยอดค้าง
        self.assertEqual(len(aging["customers"]), 2)
        names = {row["name"] for row in aging["customers"]}
        self.assertEqual(names, {"ลูกค้าเก่า", "ลูกค้าใหม่"})
        # ไม่ได้ผูก res.partner → ต้องไม่ส่ง id ปลอมให้ client ไป drill
        self.assertEqual({row["partner_id"] for row in aging["customers"]}, {0})

    def test_ap_aging_and_calendar_use_external_documents(self):
        payload = self._payload()
        rate = self._rate(payload)
        ap = payload["ap"]
        self.assertEqual(ap["source"], "external")
        self.assertAlmostEqual(ap["aging"]["total"], 700.0 * rate, places=2)
        self.assertAlmostEqual(
            ap["aging"]["current"], 700.0 * rate, places=2)
        self.assertAlmostEqual(
            sum(row["approved"] for row in ap["calendar"]),
            700.0 * rate, places=2)

    def test_cash_forecast_collects_external_invoices(self):
        payload = self._payload()
        rate = self._rate(payload)
        rows = payload["cash"]["forecast"]["rows"]
        self.assertAlmostEqual(
            sum(row["inflow_collections"] for row in rows),
            1500.0 * rate, places=2)
        self.assertAlmostEqual(
            sum(row["outflow_ap"] for row in rows), 700.0 * rate, places=2)

    def test_sales_funnel_and_dso_use_external_invoices(self):
        payload = self._payload()
        rate = self._rate(payload)
        metrics = payload["sales"]["metrics"]
        self.assertAlmostEqual(metrics["total_ar"], 1500.0 * rate, places=2)
        stages = {s["stage"]: s["value"] for s in payload["sales"]["funnel"]}
        # ออกใบแจ้งหนี้ปีงบนี้ 1,800 (รวมใบที่เก็บเงินแล้ว 300)
        self.assertAlmostEqual(stages["invoice"], 1800.0 * rate, places=2)
        self.assertAlmostEqual(stages["collection"], 300.0 * rate, places=2)

    def test_hint_when_external_source_has_no_document(self):
        self.Invoice.search([("company_id", "=", self.company.id)]).unlink()
        codes = {h["code"] for h in self._payload()["empty_hints"]}
        self.assertIn("no_ext_invoices", codes)
        self.assertIn("no_ext_budget", codes)

    def test_controlling_uses_external_budget(self):
        plan = self.env["account.analytic.plan"].search(
            [("parent_id", "=", False)], limit=1)
        analytic = self.env["account.analytic.account"].create({
            "name": "BSF Ext CC", "plan_id": plan.id,
            "company_id": self.company.id,
        })
        # รอบแรก: อ่านช่วงวันที่ของจอ แล้วตั้งงบให้ตรงช่วงพอดี → ไม่ต้องเฉลี่ย
        first = self._payload(plan_id=plan.id)["controlling"]
        if not first.get("configured"):
            self.skipTest("แผนวิเคราะห์ยังไม่มีคอลัมน์บน analytic line")
        self.Budget.create({
            "company_id": self.company.id,
            "analytic_account_id": analytic.id,
            "date_from": first["date_from"], "date_to": first["date_to"],
            "amount": 1200.0,
        })
        payload = self._payload(plan_id=plan.id)
        rate = self._rate(payload)
        co = payload["controlling"]
        self.assertEqual(co["budget_source"], "external")
        self.assertTrue(co["budget_available"])
        row = next(r for r in co["rows"] if r["analytic_id"] == analytic.id)
        self.assertAlmostEqual(row["budget"], 1200.0 * rate, places=2)
        self.assertAlmostEqual(row["available"], 1200.0 * rate, places=2)


class TestBsfDocImportWizard(ExtDocCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plan = cls.env["account.analytic.plan"].search(
            [("parent_id", "=", False)], limit=1)
        cls.analytic = cls.env["account.analytic.account"].create({
            "name": "BSF Import CC", "code": "BSF-IMP-CC",
            "plan_id": cls.plan.id, "company_id": cls.company.id,
        })

    def _wizard(self, mode, text, name="docs.csv"):
        return self.env["biz.smart.finance.doc.import"].create({
            "company_id": self.company.id,
            "mode": mode,
            "file_name": name,
            "file_data": base64.b64encode(text.encode("utf-8")),
        })

    def test_invoice_csv_preview_and_import(self):
        wizard = self._wizard("invoice",
            "doc_type,number,partner,date,date_due,amount_total,"
            "amount_untaxed,amount_residual\n"
            "ar,INV-1,ACME,2026-06-01,2026-07-01,\"1,070\",1000,1070\n"
            "ap,BILL-1,ผู้ขาย ก,2026-06-05,2026-07-05,500,500,200\n")
        wizard.action_preview()
        self.assertEqual(wizard.error_count, 0)
        self.assertEqual(wizard.valid_count, 2)
        wizard.action_import()
        docs = self.Invoice.search([("company_id", "=", self.company.id)])
        self.assertEqual(len(docs), 2)
        ar = docs.filtered(lambda d: d.doc_type == "ar")
        self.assertEqual(ar.amount_total, 1070.0)
        self.assertEqual(ar.amount_untaxed, 1000.0)
        self.assertEqual(set(docs.mapped("source")), {"import"})

    def test_invoice_residual_over_total_flagged(self):
        wizard = self._wizard("invoice",
            "doc_type,number,partner,date,date_due,amount_total,"
            "amount_untaxed,amount_residual\n"
            "ar,INV-2,ACME,2026-06-01,,100,,500\n")
        wizard.action_preview()
        self.assertEqual(wizard.error_count, 1)
        with self.assertRaises(UserError):
            wizard.action_import()

    def test_budget_csv_resolves_cost_centre_by_code(self):
        wizard = self._wizard("budget",
            "analytic,date_from,date_to,amount\n"
            "BSF-IMP-CC,2026-01-01,2026-12-31,\"1,500,000\"\n")
        wizard.action_preview()
        self.assertEqual(wizard.error_count, 0)
        self.assertEqual(wizard.line_ids.analytic_account_id, self.analytic)
        wizard.action_import()
        budget = self.Budget.search([("company_id", "=", self.company.id)])
        self.assertEqual(len(budget), 1)
        self.assertEqual(budget.amount, 1500000.0)

    def test_budget_unknown_cost_centre_blocks_import(self):
        wizard = self._wizard("budget",
            "analytic,date_from,date_to,amount\n"
            "ไม่มีศูนย์นี้,2026-01-01,2026-12-31,1000\n")
        wizard.action_preview()
        self.assertEqual(wizard.error_count, 1)
        self.assertIn("ไม่พบศูนย์ต้นทุน", wizard.line_ids.warning)
        with self.assertRaises(UserError):
            wizard.action_import()

    def test_wrong_header_for_mode_raises(self):
        wizard = self._wizard("budget",
            "doc_type,number,partner,date,date_due,amount_total,"
            "amount_untaxed,amount_residual\nar,INV-1,ACME,2026-06-01,,1,,1\n")
        with self.assertRaises(UserError):
            wizard.action_preview()


class TestBsfSourceServiceDocs(ExtDocCommon):
    """adapter API — เขียนผ่าน upsert เดียวกัน และรายงาน error แทนการเดา"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plan = cls.env["account.analytic.plan"].search(
            [("parent_id", "=", False)], limit=1)
        cls.analytic = cls.env["account.analytic.account"].create({
            "name": "BSF API CC", "code": "BSF-API-CC",
            "plan_id": cls.plan.id, "company_id": cls.company.id,
        })
        cls.service = cls.env["biz.smart.finance.source"]

    def _payload(self, **extra):
        return dict({
            "company_code": "X",
            "as_of": str(self.today),
            "currency": self.company.currency_id.name,
        }, **extra)

    def test_store_invoices_and_budgets(self):
        result = self.service._store(self.company, self._payload(
            invoices=[{
                "doc_type": "ap", "number": "API-1", "partner": "ผู้ขาย ข",
                "date": str(self.today), "date_due": str(self.today),
                "total": 900.0, "untaxed": 900.0, "residual": 900.0,
            }],
            budgets=[{
                "analytic": "BSF-API-CC", "date_from": "2026-01-01",
                "date_to": "2026-12-31", "amount": 4000.0,
            }],
        ))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["errors"], [])
        doc = self.Invoice.search([("company_id", "=", self.company.id)])
        self.assertEqual(doc.number, "API-1")
        self.assertEqual(doc.source, "api")
        self.assertEqual(
            self.Budget.search([("company_id", "=", self.company.id)]).amount,
            4000.0)

    def test_unknown_cost_centre_reports_error_and_writes_nothing(self):
        result = self.service._store(self.company, self._payload(
            budgets=[{"analytic": "ไม่มีจริง", "date_from": "2026-01-01",
                      "date_to": "2026-12-31", "amount": 10.0}],
        ))
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("ศูนย์ต้นทุน" in e for e in result["errors"]))
        self.assertFalse(
            self.Budget.search([("company_id", "=", self.company.id)]))
