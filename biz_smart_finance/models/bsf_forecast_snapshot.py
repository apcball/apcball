# -*- coding: utf-8 -*-
import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class BsfForecastSnapshot(models.Model):
    """ภาพนิ่งของกริดพยากรณ์ ณ ต้นเดือน — ไว้ย้อนดูว่า "ตอนนั้นเราคาดว่าอย่างไร"

    เก็บทั้งกริดเป็น JSON ก้อนเดียวโดยตั้งใจ (ไม่แตกเป็นตาราง งวด×ตัวชี้วัด)
    เพราะโครงของกริดยังเปลี่ยนได้ และสิ่งที่ต้องการคือเทียบภาพรวมย้อนหลัง
    ไม่ใช่คิวรีเจาะรายบรรทัด — KPI 3 ตัวที่ใช้บ่อยแยกเป็นคอลัมน์ให้ list view
    เรียงและสรุปได้โดยไม่ต้อง parse JSON
    """

    _name = "biz.smart.finance.forecast.snapshot"
    _description = "Smart Finance Forecast Snapshot"
    _order = "snapshot_date desc, company_id"
    _rec_name = "display_name"

    company_id = fields.Many2one(
        "res.company", string="บริษัท", required=True, index=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id", store=True, readonly=True,
    )
    snapshot_date = fields.Date(
        string="ณ วันที่", required=True, index=True,
        default=fields.Date.context_today,
    )
    horizon_months = fields.Integer(string="ช่วงพยากรณ์ (เดือน)")
    include_sales_to_cash = fields.Boolean(string="รวม Sales to Cash")
    payload_json = fields.Text(string="ข้อมูลกริด (JSON)", required=True)
    kpi_revenue_12m = fields.Monetary(
        string="รายได้คาดตลอดช่วง", currency_field="currency_id",
    )
    kpi_net_cash_low = fields.Monetary(
        string="เงินสดคงเหลือต่ำสุด", currency_field="currency_id",
    )
    kpi_pipeline_weighted = fields.Monetary(
        string="งานขายถ่วงน้ำหนัก", currency_field="currency_id",
    )
    display_name = fields.Char(compute="_compute_display_name_field", store=True)

    _sql_constraints = [
        ("bsf_snapshot_uniq", "unique(company_id, snapshot_date)",
         "มีภาพนิ่งของบริษัทนี้ ณ วันนี้อยู่แล้ว"),
    ]

    @api.depends("company_id", "snapshot_date")
    def _compute_display_name_field(self):
        for rec in self:
            rec.display_name = "%s · %s" % (
                rec.snapshot_date or "", rec.company_id.name or "")

    def action_open_payload(self):
        """เปิดดู JSON เต็มในฟอร์ม (ไม่มีจอเฉพาะ — ฟอร์มโชว์ text อยู่แล้ว)"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
        }

    @api.model
    def cron_snapshot(self):
        """เก็บภาพนิ่งของทุกบริษัทที่ตั้งค่า Smart Finance ไว้แล้ว

        รันซ้ำวันเดิมได้ (ข้ามบริษัทที่มีภาพนิ่งของวันนี้แล้ว) — cron ที่พลาด
        รอบแล้วถูก trigger ซ้ำจึงไม่สร้างข้อมูลซ้อน
        """
        today = fields.Date.context_today(self)
        engine = self.env["biz.smart.finance.dashboard"]
        configs = self.env["biz.smart.finance.config"].sudo().search([])
        # เช็ค "มีภาพนิ่งของวันนี้แล้วหรือยัง" ครั้งเดียวก่อนเข้าลูป แทน
        # search_count ต่อบริษัท
        done_today = {
            company.id
            for company, in self._read_group(
                [("snapshot_date", "=", today)], groupby=["company_id"])
        }
        created = self.browse()
        for cfg in configs:
            company = cfg.company_id
            if company.id in done_today:
                continue
            # ใช้เครื่องยนต์สไลซ์บาง — cron อ่านแค่ payload["forecast"]
            # การสร้างครบ 13 แท็บต่อบริษัทคือของทิ้งล้วน ๆ
            # (จงใจไม่ commit ต่อบริษัท: `TransactionCase` ของ Odoo ไม่ได้เข้า
            # test mode — มีแต่ HttpCase — commit จริงจะปิด savepoint ที่กรอบ
            # เทสใช้แยก transaction แล้วเทสถัดไปพังยกชุด ส่วนความเสี่ยงที่กัน
            # ได้จริงถูกกันด้วย try/except ต่อบริษัทตรงนี้อยู่แล้ว)
            try:
                payload = engine.sudo().with_company(company).get_forecast_data(
                    {"company_id": company.id})
            except Exception:  # pragma: no cover - กัน cron ตายทั้งรอบ
                _logger.exception(
                    "Smart Finance: เก็บภาพนิ่ง forecast ของ %s ไม่สำเร็จ",
                    company.display_name)
                continue
            forecast = payload.get("forecast") or {}
            if not forecast:
                continue
            created |= self.create(self._values_from_forecast(
                company, today, forecast, payload.get("filters") or {}))
        return len(created)

    @api.model
    def _values_from_forecast(self, company, day, forecast, filters=None):
        cash = forecast.get("cash") or {}
        pnl = forecast.get("pnl") or {}
        closing = cash.get("closing") or []
        pipeline = forecast.get("pipeline") or {}
        return {
            "company_id": company.id,
            "snapshot_date": day,
            "horizon_months": forecast.get("horizon_months") or 0,
            "include_sales_to_cash": bool((filters or {}).get("include_sales_to_cash")),
            "payload_json": json.dumps(forecast, ensure_ascii=False),
            "kpi_revenue_12m": sum(pnl.get("revenue") or []),
            "kpi_net_cash_low": min(closing) if closing else 0.0,
            "kpi_pipeline_weighted": (
                pipeline.get("totals") or {}).get("weighted") or 0.0,
        }
