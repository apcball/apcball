# -*- coding: utf-8 -*-
"""Adapter ดึงตัวเลขจากระบบภายนอกเข้า External Figures (evidence-first)

สัญญาเดียวกับ hr.source.service: adapter ห้ามเดาค่าเอง — endpoint ไม่ตั้ง /
ตอบผิดรูป / สกุลเงินไม่ตรง = รายงาน error ตรง ๆ ไม่เขียนตัวเลขปลอมลงตาราง

รูปแบบ JSON ที่คาดหวังจาก GET {endpoint}?company={ext_company_code}&as_of=YYYY-MM-DD
(header: Authorization: Bearer {api_key}):

    {
      "company_code": "SRP",
      "as_of": "2026-06-30",
      "currency": "THB",                     # ต้องตรงสกุลเงินบริษัทใน Odoo
      "inventory": [                          # ทางเลือก
        {"category": "Raw Material", "value": 1250000.0, "qty": 320.0}
      ],
      "metrics": {                            # ทางเลือก — key ตาม METRIC_KEYS
        "total_assets": 99000000.0,
        "revenue_ytd": 45000000.0
      },
      "invoices": [                           # ทางเลือก — AR/AP คงค้าง
        {"doc_type": "ar", "number": "INV-2026-001", "partner": "ACME",
         "date": "2026-06-01", "date_due": "2026-07-01",
         "total": 107000.0, "untaxed": 100000.0, "residual": 107000.0}
      ],
      "budgets": [                            # ทางเลือก — งบศูนย์ต้นทุน
        {"analytic": "CC-100", "date_from": "2026-01-01",
         "date_to": "2026-12-31", "amount": 5000000.0}
      ]
    }

ศูนย์ต้นทุนอ้างด้วย code หรือชื่อของ account.analytic.account ที่มีอยู่จริง —
resolve ไม่ได้/กำกวม = ข้ามแถวนั้นแล้วรายงาน error ไม่เดาให้
"""
import logging
from collections import defaultdict

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

from .bsf_ext_fact import METRIC_KEY_SET

_logger = logging.getLogger(__name__)

TIMEOUT = 20


class BsfSourceService(models.AbstractModel):
    _name = "biz.smart.finance.source"
    _description = "Smart Finance External Source Adapter"

    @api.model
    def _config(self):
        icp = self.env["ir.config_parameter"].sudo()
        return {
            "endpoint": icp.get_param("biz_smart_finance.ext_endpoint"),
            "api_key": icp.get_param("biz_smart_finance.ext_api_key"),
        }

    @api.model
    def fetch_facts(self, company, as_of):
        """ดึงตัวเลขหนึ่งบริษัท — คืน contract dict ไม่ throw (ยกเว้นบั๊กจริง)

        {"source": "api", "status": "ok|unavailable|error",
         "as_of": date|None, "rows": n, "errors": [str]}"""
        cfg = self._config()
        Config = self.env["biz.smart.finance.config"]
        bsf_cfg = Config.get_for_companies(company.ids).get(company.id)
        if not cfg["endpoint"]:
            return self._result("unavailable", errors=[
                "ยังไม่ตั้ง endpoint (Settings › Smart Finance › External Source)"])
        if not bsf_cfg or not bsf_cfg.ext_company_code:
            return self._result("unavailable", errors=[
                "บริษัท %s ยังไม่ตั้งรหัสบริษัทในระบบภายนอก" % company.name])
        headers = {}
        if cfg["api_key"]:
            headers["Authorization"] = "Bearer %s" % cfg["api_key"]
        try:
            response = requests.get(
                cfg["endpoint"],
                params={"company": bsf_cfg.ext_company_code,
                        "as_of": str(as_of)},
                headers=headers, timeout=TIMEOUT)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            _logger.warning("BSF external sync failed for %s: %s",
                            company.name, exc)
            return self._result("error", errors=[str(exc)])
        return self._store(company, payload)

    def _store(self, company, payload):
        errors = []
        if not isinstance(payload, dict):
            return self._result("error", errors=["response ไม่ใช่ JSON object"])
        as_of = payload.get("as_of")
        try:
            as_of = fields.Date.to_date(as_of)
        except ValueError:
            as_of = None
        if not as_of:
            return self._result("error", errors=["as_of ในคำตอบไม่ใช่วันที่"])
        currency = (payload.get("currency") or "").upper()
        if currency and currency != company.currency_id.name:
            return self._result("error", errors=[
                "สกุลเงิน %s ไม่ตรงกับสกุลบริษัท %s — ไม่แปลงให้เอง"
                % (currency, company.currency_id.name)])

        Fact = self.env["biz.smart.finance.ext.fact"]
        total = 0
        inv_rows = []
        for item in payload.get("inventory") or []:
            category = (item.get("category") or "").strip()
            try:
                value = float(item.get("value"))
            except (TypeError, ValueError):
                errors.append("inventory '%s': value ไม่ใช่ตัวเลข" % category)
                continue
            inv_rows.append({
                "metric_key": "inventory_value",
                "label": category,
                "amount": value,
                "qty": float(item.get("qty") or 0.0),
            })
        if inv_rows:
            total += Fact.upsert_facts(
                company, as_of, "inventory", inv_rows, source="api")

        metric_rows = []
        for key, value in (payload.get("metrics") or {}).items():
            if key not in METRIC_KEY_SET:
                errors.append("metric '%s' ไม่รู้จัก — ข้าม" % key)
                continue
            try:
                metric_rows.append({"metric_key": key, "amount": float(value)})
            except (TypeError, ValueError):
                errors.append("metric '%s': ค่าไม่ใช่ตัวเลข" % key)
        if metric_rows:
            total += Fact.upsert_facts(
                company, as_of, "ratio_input", metric_rows, source="api")

        total += self._store_invoices(company, payload, errors)
        total += self._store_budgets(company, payload, errors)

        if not total:
            errors.append(
                "คำตอบไม่มีข้อมูล inventory/metrics/invoices/budgets ที่ใช้ได้")
        return self._result("ok" if total else "error", as_of=as_of,
                            rows=total, errors=errors)

    def _unique_by(self, model, field, values):
        """{ค่า: id} เฉพาะค่าที่ตรงตัวและเจอ **รายการเดียว**

        กติกาเดียวกับการ search ทีละแถวแบบเดิม (เจอ 0 หรือ >1 = ข้าม) แต่ยิง
        คิวรีเดียวต่อ payload แทนหนึ่งคิวรีต่อรายการ"""
        wanted = sorted({(v or "").strip() for v in values if (v or "").strip()})
        if not wanted:
            return {}
        found = defaultdict(list)
        for row in model.search_read([(field, "in", wanted)], [field]):
            found[row[field]].append(row["id"])
        return {key: ids[0] for key, ids in found.items() if len(ids) == 1}

    def _store_invoices(self, company, payload, errors):
        """ใบแจ้งหนี้/บิลคงค้าง — คีย์ (doc_type, number) แถวเดิมถูกทับ"""
        rows = []
        items = payload.get("invoices") or []
        partner_ids = self._unique_by(
            self.env["res.partner"], "name",
            (item.get("partner") for item in items))
        for item in items:
            number = (item.get("number") or "").strip()
            doc_type = (item.get("doc_type") or "").strip().lower()
            if doc_type not in ("ar", "ap"):
                errors.append(
                    "invoice '%s': doc_type ต้องเป็น ar หรือ ap" % number)
                continue
            if not number:
                errors.append("invoice: ไม่มี number — ข้าม")
                continue
            try:
                date = fields.Date.to_date(item.get("date"))
                date_due = fields.Date.to_date(item.get("date_due"))
            except (ValueError, TypeError):
                errors.append("invoice '%s': วันที่ผิดรูปแบบ" % number)
                continue
            if not date:
                errors.append("invoice '%s': ไม่มีวันที่เอกสาร" % number)
                continue
            try:
                total = float(item.get("total"))
                residual = float(item.get("residual"))
                untaxed = float(item.get("untaxed") or 0.0)
            except (TypeError, ValueError):
                errors.append("invoice '%s': ยอดเงินไม่ใช่ตัวเลข" % number)
                continue
            partner_name = (item.get("partner") or "").strip()
            rows.append({
                "doc_type": doc_type,
                "number": number,
                "partner_id": partner_ids.get(partner_name, False),
                "partner_name": partner_name or "ไม่ระบุ",
                "date": date,
                "date_due": date_due,
                "amount_total": total,
                "amount_untaxed": untaxed,
                "amount_residual": residual,
            })
        if not rows:
            return 0
        return self.env["biz.smart.finance.ext.invoice"].upsert_invoices(
            company, rows, source="api")

    def _store_budgets(self, company, payload, errors):
        """งบศูนย์ต้นทุน — ต้อง resolve เป็น analytic account จริงเท่านั้น"""
        Analytic = self.env["account.analytic.account"].sudo()
        rows = []
        items = payload.get("budgets") or []
        codes = [item.get("analytic") for item in items]
        # รหัสก่อนแล้วค่อยชื่อ เหมือนเดิม — แต่สองคิวรีต่อ payload ไม่ใช่ต่อแถว
        by_code = self._unique_by(Analytic, "code", codes)
        by_name = self._unique_by(Analytic, "name", codes)
        for item in items:
            code = (item.get("analytic") or "").strip()
            analytic_id = by_code.get(code) or by_name.get(code)
            if not analytic_id:
                errors.append(
                    "budget '%s': หาศูนย์ต้นทุนไม่เจอหรือกำกวม — ข้าม" % code)
                continue
            try:
                date_from = fields.Date.to_date(item.get("date_from"))
                date_to = fields.Date.to_date(item.get("date_to"))
            except (ValueError, TypeError):
                errors.append("budget '%s': วันที่ผิดรูปแบบ" % code)
                continue
            if not (date_from and date_to) or date_to < date_from:
                errors.append("budget '%s': ช่วงวันที่ไม่ถูกต้อง" % code)
                continue
            try:
                amount = float(item.get("amount"))
            except (TypeError, ValueError):
                errors.append("budget '%s': amount ไม่ใช่ตัวเลข" % code)
                continue
            rows.append({
                "analytic_account_id": analytic_id,
                "date_from": date_from,
                "date_to": date_to,
                "amount": amount,
            })
        if not rows:
            return 0
        return self.env["biz.smart.finance.ext.budget"].upsert_budgets(
            company, rows, source="api")

    @staticmethod
    def _result(status, as_of=None, rows=0, errors=None):
        return {
            "source": "api",
            "status": status,
            "as_of": str(as_of) if as_of else None,
            "rows": rows,
            "errors": errors or [],
        }

    # ------------------------------------------------------------------
    # entry points (ปุ่มบน config form + cron)
    # ------------------------------------------------------------------
    @staticmethod
    def _uses_external(cfg):
        """บริษัทนี้ตั้งแหล่งไหนเป็นระบบภายนอกบ้างหรือเปล่า"""
        return "external" in (
            cfg.inventory_source, cfg.ratio_source,
            cfg.invoice_source, cfg.budget_source,
        )

    @api.model
    def action_sync(self, company_ids=None, as_of=None):
        """Sync บริษัทที่ตั้งแหล่งข้อมูลภายนอกไว้ — คืน notification สรุปผล"""
        if not self.env.user.has_group("biz_smart_finance.group_bsf_manager"):
            raise UserError("ต้องเป็นสมาชิกกลุ่ม CFO Cockpit / Manager")
        as_of = as_of or fields.Date.context_today(self)
        companies = self.env["res.company"].browse(
            company_ids or self.env.user.company_ids.ids)
        Config = self.env["biz.smart.finance.config"].sudo()
        cfg_map = Config.get_for_companies(companies.ids)
        lines = []
        for company in companies:
            cfg = cfg_map.get(company.id)
            if not cfg or not self._uses_external(cfg):
                continue
            result = self.sudo().fetch_facts(company, as_of)
            detail = "; ".join(result["errors"]) if result["errors"] else ""
            lines.append("%s: %s (%d แถว) %s" % (
                company.name, result["status"], result["rows"], detail))
        if not lines:
            lines = ["ไม่มีบริษัทที่ตั้งแหล่งข้อมูลเป็นระบบภายนอก"]
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Sync ระบบภายนอก",
                "message": "\n".join(lines),
                "type": "info",
                "sticky": True,
            },
        }

    @api.model
    def cron_sync(self):
        """cron รายเดือน (ปิดไว้ default) — sync ทุกบริษัทที่ตั้ง external"""
        as_of = fields.Date.context_today(self)
        Config = self.env["biz.smart.finance.config"].sudo()
        for cfg in Config.search([]):
            if not self._uses_external(cfg):
                continue
            result = self.sudo().fetch_facts(cfg.company_id, as_of)
            _logger.info("BSF cron sync %s: %s (%d rows) %s",
                         cfg.company_id.name, result["status"],
                         result["rows"], result["errors"])
        return True
