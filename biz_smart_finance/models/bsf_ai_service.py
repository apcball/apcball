# -*- coding: utf-8 -*-
"""AI service ของ CFO Cockpit (OpenRouter, key แยกของโมดูลเอง).

กติกาสำคัญ:

* ทุก entry point รับ ``filters`` แล้วรัน engine ฝั่ง server เอง — ห้ามเชื่อ
  ตัวเลขที่ client ส่งมา (client ส่งได้แค่ tab + filters)
* บีบ payload ก่อนส่ง LLM ด้วย ``_compact`` (ตารางละไม่เกิน ``MAX_ROWS`` แถว,
  ตัด geometry ของกราฟ) — token คือเงิน
* โครงสร้างคำตอบบังคับด้วย json_schema strict (ทุก schema ต้อง required ครบ
  และ additionalProperties: False ไม่งั้น OpenRouter ปฏิเสธ)
* ไม่ sudo ตัว service — engine gate+sudo ของมันเอง; config param อ่านด้วย
  ``.sudo()`` เฉพาะจุด
"""
import json
import logging

import requests

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-opus-5"

MAX_ROWS = 8
MAX_SUGGESTED_RISKS = 6
MAX_SUGGESTED_FORECAST_LINES = 10
# เดือนที่ย้อนดูตอนให้ AI ร่างรายการประจำ — สั้นกว่านี้ฤดูกาลไม่โผล่
FORECAST_HISTORY_MONTHS = 24

SYSTEM_PERSONA = (
    "คุณคือที่ปรึกษา CFO อาวุโสของกลุ่มบริษัท มีหน้าที่วิเคราะห์ข้อมูลการเงิน"
    "จาก CFO Cockpit แล้วให้ข้อสรุปและคำแนะนำระดับผู้บริหาร\n"
    "กติกา:\n"
    "1. ตอบเป็นภาษาไทยเสมอ กระชับ ตรงประเด็น ระดับรายงานบอร์ด\n"
    "2. ตัวเลขเงินในข้อมูลเป็นบาท (THB ดิบ) — เวลานำเสนอให้แปลงเป็นล้านบาท "
    "ทศนิยมไม่เกิน 2 ตำแหน่ง เช่น 1234567.0 -> 1.23 ล้านบาท\n"
    "3. ใช้เฉพาะตัวเลขที่อยู่ในข้อมูลเท่านั้น ห้ามแต่งตัวเลขเอง "
    "ถ้าข้อมูลส่วนไหนว่างให้ข้ามหรือบอกว่ายังไม่มีข้อมูล\n"
    "4. คำแนะนำต้องปฏิบัติได้จริงและอ้างอิงตัวเลขที่เห็น"
)

TAB_INSTRUCTIONS = {
    "overview": (
        "วิเคราะห์ภาพรวมกลุ่ม: รายได้/EBITDA/กำไรสุทธิเทียบ YoY, เงินสดและ "
        "Net Debt/Equity เทียบเป้า, ผลงานราย BU และความเสี่ยงเด่น "
        "แล้วสรุปประเด็นที่ CFO ต้องสั่งการ"
    ),
    "cash": (
        "วิเคราะห์สภาพคล่อง: เงินสดปัจจุบันเทียบเงินสดขั้นต่ำ แนวโน้ม 13 สัปดาห์ "
        "สัปดาห์ที่เสี่ยงหลุดขั้นต่ำ โครงสร้างเงินเข้า-ออก และวิธีปิดช่องว่าง "
        "รวมถึงการกระจุกตัวของเงินสดในธนาคารใดธนาคารหนึ่งมากเกินไป "
        "ธนาคารที่คาดว่าจะหลุด buffer ในสัปดาห์ไหน วงเงินสินเชื่อที่เหลือใช้ได้ "
        "และแผนโอนระหว่างธนาคารที่ควรเร่งอนุมัติ"
    ),
    "forecast": (
        "วิเคราะห์พยากรณ์รายเดือน: เดือนที่เงินสดต่ำสุด/หลุดขั้นต่ำและสาเหตุ, "
        "สัดส่วนรายได้ที่มาจากงานขายซึ่งยังไม่เซ็นสัญญา (ยิ่งสูงยิ่งเปราะ), "
        "โครงการที่ต้นทุนคงเหลือสูงเทียบกำไร, การกระจุกตัวของดีลใหญ่ไม่กี่ดีล "
        "และคอลัมน์ 'หลังจากนี้' ที่บอกภาระเลยช่วงพยากรณ์ "
        "แล้วเสนอมาตรการที่ทำได้ภายในไตรมาสนี้"
    ),
    "sales": (
        "วิเคราะห์ funnel ขาย-เก็บเงิน: จุดที่ conversion ตกมากสุด, DSO เทียบเป้า, "
        "backlog coverage, ลูกหนี้ค้างเกิน 60 วัน และข้อเสนอเร่งเก็บเงิน"
    ),
    "margin": (
        "วิเคราะห์กำไรโครงการ: leakage รวมเทียบเพดาน, โครงการที่ margin "
        "หลุดงบมากสุด, ผลของ VO และมาตรการหยุดเลือด"
    ),
    "ap": (
        "วิเคราะห์เจ้าหนี้และแผนจ่าย: ยอดค้างเกินกำหนด, aging, ซัพพลายเออร์"
        "ที่ต้องจ่ายก่อน (priority), ภาระ PO ที่กำลังมาถึง และความขัดแย้งกับ"
        "เงินสดขั้นต่ำ"
    ),
    "risk": (
        "วิเคราะห์ความเสี่ยง: ความเสี่ยงคะแนนสูงสุด, สัญญาณเตือนล่วงหน้า"
        "ที่ต้องเฝ้า, ผลของ scenario ที่เลือก และลำดับการจัดการ"
    ),
    "statements": (
        "วิเคราะห์งบการเงิน: โครงสร้างงบแสดงฐานะการเงินเทียบปีก่อน "
        "(สภาพคล่อง หนี้สิน ทุน), กำไรขั้นต้น/EBITDA/สุทธิเทียบงวดก่อน, "
        "กระแสเงินสดสามกิจกรรม และลูกหนี้ค้างรับตามอายุหนี้ "
        "แล้วชี้ประเด็นที่ CFO ต้องสั่งการ"
    ),
    "compare": (
        "วิเคราะห์แนวโน้มหลายงวดที่เรียงเป็นคอลัมน์ (เก่า→ใหม่): ทิศทางรายได้ "
        "กำไรขั้นต้น EBITDA และกำไรสุทธิ, งวดที่แนวโน้มหักเห, อัตรากำไรที่บาง"
        "ลงหรือหนาขึ้น, การเปลี่ยนโครงสร้างฐานะการเงิน (เงินสด ลูกหนี้ สต๊อก "
        "เจ้าหนี้ หนี้มีดอกเบี้ย) แล้วชี้ว่าอะไรกำลังก่อตัวและต้องทำอะไรต่อ"
    ),
    "controlling": (
        "วิเคราะห์ต้นทุนตามศูนย์ต้นทุน: ศูนย์ที่ใช้งบเกินหรือใกล้เต็ม "
        "(ใช้จริง + ภาระผูกพันเทียบงบ), ภาระผูกพันจาก PO ที่กำลังจะกลายเป็น "
        "ค่าใช้จ่าย, โครงสร้างต้นทุนตามประเภทบัญชี และศูนย์ที่กำไรสุทธิติดลบ"
    ),
    "inventory": (
        "วิเคราะห์สินค้าคงเหลือ: มูลค่ารวมเทียบปีก่อน, หมวดที่กินเงินทุนมากสุด, "
        "Inventory Turnover / DIO เทียบธุรกิจ, ผลกระทบต่อ Cash Conversion "
        "Cycle และส่วนต่างกระทบยอด SVL↔GL ถ้ามี — เสนอทางลดสต๊อกจม"
    ),
    "ratios": (
        "วิเคราะห์อัตราส่วนการเงินทั้ง 4 กลุ่ม (สภาพคล่อง หนี้สิน ทำกำไร "
        "ประสิทธิภาพ) เทียบปีก่อน: ตัวที่แย่ลงมากสุด, ความเชื่อมโยงระหว่างกัน "
        "และบริษัทที่ตัวเลขอ่อนแอสุด — ระวังค่าที่เป็น null คือคำนวณไม่ได้ "
        "ห้ามตีความเป็นศูนย์"
    ),
    "close": (
        "วิเคราะห์สถานะปิดงวด: งวดที่ตั้งแหล่ง GL เป็นระบบภายนอกแต่ยังไม่มี "
        "Trial Balance ยืนยัน, งวดที่ TB ไม่ดุล (ผลต่างไม่เป็นศูนย์), งวดที่ยัง "
        "ไม่ปิด และความเสี่ยงจากการผสมแหล่งข้อมูล Odoo/ภายนอกในปีงบเดียวกัน"
    ),
}

BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "insights": {"type": "array", "items": {"type": "string"}},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "priority": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["name", "priority", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "insights", "actions"],
    "additionalProperties": False,
}

RISK_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["cash", "margin", "ar", "fx",
                                 "operation", "other"],
                    },
                    "impact": {"type": "integer"},
                    "likelihood": {"type": "integer"},
                    "early_warning": {"type": "string"},
                    "action": {"type": "string"},
                },
                "required": ["name", "category", "impact", "likelihood",
                             "early_warning", "action"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "risks"],
    "additionalProperties": False,
}

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "suggestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "suggestions"],
    "additionalProperties": False,
}

FORECAST_SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "recurring_lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "flow_type": {"type": "string", "enum": ["in", "out"]},
                    "category": {
                        "type": "string",
                        "enum": ["payroll", "opex", "tax",
                                 "other_out", "other_in"],
                    },
                    "amount": {"type": "number"},
                    "recurrence": {
                        "type": "string", "enum": ["monthly", "weekly"],
                    },
                    "day_of_month": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["name", "flow_type", "category", "amount",
                             "recurrence", "day_of_month", "reason"],
                "additionalProperties": False,
            },
        },
        "assumption_notes": {"type": "array", "items": {"type": "string"}},
        "probability_flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "deal_name": {"type": "string"},
                    "issue": {"type": "string"},
                },
                "required": ["deal_name", "issue"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "recurring_lines", "assumption_notes",
                 "probability_flags"],
    "additionalProperties": False,
}

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["title", "content"],
    "additionalProperties": False,
}

# กติกาบีบ payload ต่อแท็บ: (คีย์ที่เก็บ, ลิสต์ที่ต้อง truncate)
# geometry ของกราฟ (bubbles/heatmap/calendar/before_ap/planned_ap/weeks)
# ตัดทิ้ง — โมเดลอ่านตารางพอ
_COMPACT_RULES = {
    "overview": [("kpis", None), ("dimensions", MAX_ROWS),
                 ("top_risks", MAX_ROWS), ("bu_table", MAX_ROWS)],
    "sales": [("funnel", None), ("metrics", None),
              ("by_channel", MAX_ROWS), ("by_bu", MAX_ROWS)],
    "margin": [("leakage", None), ("risk_table", MAX_ROWS),
               ("vo_table", MAX_ROWS), ("scenario_hit_pp", None)],
    "ap": [("overdue_total", None), ("aging", None),
           ("top_suppliers", MAX_ROWS), ("priority", MAX_ROWS),
           ("committed_po", None), ("conflict", None)],
    "risk": [("by_project", MAX_ROWS), ("early_warning", MAX_ROWS),
             ("register_count", None), ("scenario", None),
             # สมมติฐาน/ผลลัพธ์ของ scenario เป็นก้อนเล็ก (ไม่มีซีรีส์รายเดือน)
             # แต่เป็นสิ่งเดียวที่บอกโมเดลได้ว่า downside/stress แปลว่าอะไร
             ("outcomes", None), ("sensitivity", None)],
    # เก็บซีรีส์รายเดือนทั้งเส้น (ดู LONG_LIST_KEYS) — ตัดเหลือ 8 เมื่อไหร่
    # โมเดลจะอ่านจุดต่ำสุดของเงินสดผิดทันที
    "forecast": [("horizon_months", None), ("months", None), ("cash", None),
                 ("pnl", None), ("pipeline", None), ("ctc", None)],
    # engine เตรียม ai_summary (ตัดแถวรายบัญชีแล้ว) ให้โดยเฉพาะ
    "statements": [("ai_summary", None)],
    "controlling": [("plan_name", None), ("totals", None),
                    ("rows", MAX_ROWS), ("by_account_type", MAX_ROWS),
                    ("row_count", None), ("configured", None)],
    "inventory": [("kpis", None), ("source", None),
                  ("by_category", MAX_ROWS), ("trend", MAX_ROWS),
                  ("by_company", MAX_ROWS)],
    "ratios": [("source", None), ("groups", None),
               ("by_company", MAX_ROWS), ("missing_by_company", MAX_ROWS)],
    # คอลัมน์สูงสุด 6 ช่อง จึงไม่โดนเพดาน MAX_ROWS ตัดกลางซีรีส์
    "compare": [("mode", None), ("count", None), ("columns", MAX_ROWS),
                ("pnl_rows", MAX_ROWS), ("bs_rows", MAX_ROWS),
                ("cf_rows", MAX_ROWS), ("kpi_rows", MAX_ROWS)],
    "close": [("fy_label", None), ("rows", MAX_ROWS)],
}

# ลิสต์ที่ยอมให้ยาวเกิน MAX_ROWS ได้ — ซีรีส์ 13 สัปดาห์ ถ้าตัดเหลือ 8
# โมเดลจะอ่านแนวโน้มเงินสดผิด (คีย์ → เพดานของคีย์นั้น)
# กริดพยากรณ์ยาวได้ถึง 18 เดือน + คอลัมน์ "หลังจากนี้" = 19 จุด
FORECAST_SERIES_MAX = 19
LONG_LIST_KEYS = {
    "closing_by_week": 13,
    "months": FORECAST_SERIES_MAX,
    "closing": FORECAST_SERIES_MAX,
    "net": FORECAST_SERIES_MAX,
    "revenue": FORECAST_SERIES_MAX,
    "cost": FORECAST_SERIES_MAX,
    "margin": FORECAST_SERIES_MAX,
    "pipeline_in": FORECAST_SERIES_MAX,
    "weighted_by_month": FORECAST_SERIES_MAX,
}


class BsfAiService(models.AbstractModel):
    _name = "biz.smart.finance.ai"
    _description = "Smart Finance AI Service (OpenRouter)"

    # ------------------------------------------------------------------
    # config / gates
    # ------------------------------------------------------------------
    def _get_api_key(self):
        key = self.env["ir.config_parameter"].sudo().get_param(
            "biz_smart_finance.openrouter_api_key")
        if not key:
            raise UserError(_(
                "ยังไม่ได้ตั้งค่า OpenRouter API Key\n"
                "ไปที่ การตั้งค่า (Settings) > Smart Finance "
                "เพื่อตั้งค่าก่อนใช้งานฟีเจอร์ AI"))
        return key

    def _get_model(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "biz_smart_finance.ai_model") or DEFAULT_MODEL

    @api.model
    def is_configured(self):
        return bool(self.env["ir.config_parameter"].sudo().get_param(
            "biz_smart_finance.openrouter_api_key"))

    def _check_user(self):
        if self.env.su:
            return
        if not self.env.user.has_group("biz_smart_finance.group_bsf_user"):
            raise AccessError(_("ต้องเป็นสมาชิกกลุ่ม CFO Cockpit / Viewer"))

    def _check_manager(self):
        if self.env.su:
            return
        if not self.env.user.has_group("biz_smart_finance.group_bsf_manager"):
            raise AccessError(_("ต้องเป็นสมาชิกกลุ่ม CFO Cockpit / Manager"))

    # ------------------------------------------------------------------
    # OpenRouter (shape เดียวกับ ai.pm.claude.service._post_chat)
    # ------------------------------------------------------------------
    def _post_chat(self, system, user_content, schema, schema_name,
                   max_tokens=4096, model=None):
        api_key = self._get_api_key()
        payload = {
            "model": model or self._get_model(),
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        headers = {
            "content-type": "application/json",
            "authorization": "Bearer %s" % api_key,
        }
        try:
            resp = requests.post(
                API_URL, headers=headers, json=payload, timeout=180)
        except requests.RequestException as exc:
            _logger.exception("OpenRouter API request failed")
            raise UserError(_("เรียก AI ไม่สำเร็จ: %s") % exc)

        if resp.status_code != 200:
            _logger.error(
                "OpenRouter API error %s: %s", resp.status_code, resp.text)
            try:
                message = resp.json().get("error", {}).get("message")
            except ValueError:
                message = None
            raise UserError(
                _("AI ตอบกลับผิดพลาด (%s): %s")
                % (resp.status_code, (message or resp.text)[:500]))

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise UserError(_("โมเดล AI ไม่ตอบกลับ"))
        choice = choices[0]
        if choice.get("finish_reason") == "content_filter":
            raise UserError(_("โมเดล AI ปฏิเสธคำขอนี้"))
        text = (choice.get("message") or {}).get("content")
        if not text:
            raise UserError(_("โมเดล AI ไม่ตอบกลับ"))
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            raise UserError(_("อ่านคำตอบของ AI เป็น JSON ไม่ได้"))

    # ------------------------------------------------------------------
    # payload compaction — pure function (เทสเรียกตรงได้)
    # ------------------------------------------------------------------
    def _bound_lists(self, node, key=""):
        """ตัดทุกลิสต์ให้ไม่เกิน MAX_ROWS แบบ recursive

        กติกา "ตารางละไม่เกิน MAX_ROWS แถว" ต้องบังคับที่โครงสร้าง ไม่ใช่ฝาก
        ไว้กับ _COMPACT_RULES ซึ่งคุมได้แค่คีย์ชั้นบนสุด — ลิสต์ที่ซ้อนอยู่ข้างใน
        dict (เช่น `ap.conflict.weeks` ที่ยาวได้ถึง 13 สัปดาห์เมื่อเงินสดต่ำกว่า
        ขั้นต่ำทุกสัปดาห์) เคยหลุดไปหาโมเดลทั้งก้อน และจะหลุดอีกทุกครั้งที่มีคน
        เพิ่มลิสต์ซ้อนใหม่โดยไม่ได้แก้กติกา
        """
        if isinstance(node, list):
            limit = LONG_LIST_KEYS.get(key, MAX_ROWS)
            return [self._bound_lists(item, key) for item in node[:limit]]
        if isinstance(node, dict):
            return {k: self._bound_lists(v, k) for k, v in node.items()}
        return node

    @api.model
    def _compact(self, tab, payload):
        echo = payload.get("filters") or {}
        out = {
            "filters": {
                k: echo.get(k)
                for k in ("company_label", "year", "month", "scenario", "as_of")
            },
        }
        if tab == "cash":
            cash = payload.get("cash") or {}
            forecast = cash.get("forecast") or {}
            weeks = forecast.get("weeks") or []
            closing = forecast.get("closing") or []
            banks = cash.get("banks") or {}
            facilities = cash.get("facilities") or {}
            transfers = cash.get("transfers") or {}
            out["cash"] = {
                "opening": forecast.get("opening"),
                "min_cash": forecast.get("min_cash"),
                "kpis": cash.get("kpis"),
                # ซีรีส์กราฟเดียวที่เก็บ: เงินสดปลายสัปดาห์ 13 ตัว + label
                "closing_by_week": [
                    {"week": (weeks[i].get("label") if i < len(weeks) else i),
                     "closing": value}
                    for i, value in enumerate(closing)
                ],
                "alerts": (forecast.get("alerts") or [])[:MAX_ROWS],
                "rows": (forecast.get("rows") or [])[:MAX_ROWS],
                "min_cash_alert": cash.get("min_cash_alert"),
                # สรุปรายธนาคาร — ไม่ส่ง weeks เต็ม 13 สัปดาห์ต่อธนาคาร
                # (ใหญ่เกินจำเป็นสำหรับ brief) ส่งแค่ยอดปัจจุบัน+เตือน
                "bank_shares_basis": banks.get("shares_basis"),
                "banks": [
                    {"name": row.get("name"),
                     "current_balance": row.get("current_balance"),
                     "min_balance": row.get("min_balance")}
                    for row in (banks.get("rows") or [])[:MAX_ROWS]
                ],
                "bank_alerts": (banks.get("alerts") or [])[:MAX_ROWS],
                "facilities": (facilities.get("rows") or [])[:MAX_ROWS],
                "facilities_total": facilities.get("total"),
                "transfers": [
                    row for row in (transfers.get("rows") or [])[:MAX_ROWS]
                    if row.get("state") in ("draft", "approved")
                ],
            }
            return self._bound_lists(out)
        if tab == "forecast":
            out["forecast"] = self._compact_forecast(payload)
            return self._bound_lists(out)
        section = payload.get(tab) or {}
        rules = _COMPACT_RULES.get(tab) or []
        compacted = {}
        for key, limit in rules:
            value = section.get(key)
            if isinstance(value, list) and limit:
                value = value[:limit]
            compacted[key] = value
        out[tab] = compacted
        return self._bound_lists(out)

    def _compact_forecast(self, payload):
        """กริดพยากรณ์ → ซีรีส์ล้วน (ตัด `rows` ที่ซ้ำกับซีรีส์ทิ้ง)

        `cash.rows` เป็น 19 dict × 12 คีย์ = ข้อมูลเดิมในรูปที่ยาวกว่าเดิม
        สามเท่า โมเดลอ่านซีรีส์คู่กับ labels ได้ตรงกว่าและถูกกว่ามาก
        """
        forecast = payload.get("forecast") or {}
        cash = forecast.get("cash") or {}
        pnl = forecast.get("pnl") or {}
        pipeline = forecast.get("pipeline") or {}
        ctc = forecast.get("ctc") or {}
        labels = [m.get("label") for m in (forecast.get("months") or [])]
        return {
            "horizon_months": forecast.get("horizon_months"),
            "months": labels,
            "cash": {
                "opening": cash.get("opening"),
                "min_cash": cash.get("min_cash"),
                "net": cash.get("net"),
                "closing": cash.get("closing"),
                "alerts": (cash.get("alerts") or [])[:MAX_ROWS],
                "low_month": cash.get("low_month"),
            },
            "pnl": {
                "revenue": pnl.get("revenue"),
                "cost": pnl.get("cost"),
                "margin": pnl.get("margin"),
                "total": pnl.get("total"),
                "actual_mtd": pnl.get("actual_mtd"),
            },
            "pipeline": {
                "totals": pipeline.get("totals"),
                "revenue_share_pct": pipeline.get("revenue_share_pct"),
                "weighted_by_month": pipeline.get("weighted_by_month"),
                "rows": (pipeline.get("rows") or [])[:MAX_ROWS],
            },
            "ctc": {
                "total": ctc.get("total"),
                "overdue_count": ctc.get("overdue_count"),
                "rows": (ctc.get("rows") or [])[:MAX_ROWS],
            },
        }

    def _dump(self, data):
        return json.dumps(data, ensure_ascii=False, default=str)

    # ------------------------------------------------------------------
    # 1) AI CFO Brief ต่อแท็บ
    # ------------------------------------------------------------------
    @api.model
    def generate_brief(self, tab, filters=None):
        self._check_user()
        if tab not in TAB_INSTRUCTIONS:
            raise UserError(_("ไม่รู้จักแท็บ: %s") % tab)
        Dashboard = self.env["biz.smart.finance.dashboard"]
        # Monthly Close ย้ายไปเป็น client action แยก — ใช้เครื่องยนต์บางของมัน
        # (get_dashboard_data ไม่มีสไลซ์ close อีกต่อไป)
        payload = (
            Dashboard.get_monthly_close_data(filters or {})
            if tab == "close"
            else Dashboard.get_dashboard_data(filters or {})
        )
        compact = self._compact(tab, payload)
        user_content = "%s\n\nข้อมูล (JSON):\n%s" % (
            TAB_INSTRUCTIONS[tab], self._dump(compact))
        parsed = self._post_chat(
            SYSTEM_PERSONA, user_content, BRIEF_SCHEMA, "cfo_brief")
        actions = []
        for action in parsed.get("actions") or []:
            try:
                priority = int(action.get("priority") or 3)
            except (TypeError, ValueError):
                priority = 3
            actions.append({
                "name": action.get("name") or "",
                "priority": priority,
                "reason": action.get("reason") or "",
            })
        return {
            "summary": parsed.get("summary") or "",
            "insights": [s for s in (parsed.get("insights") or []) if s],
            "actions": actions,
        }

    # ------------------------------------------------------------------
    # 2) AI เสนอความเสี่ยงเข้า Register (manager เท่านั้น — เขียนข้อมูล)
    # ------------------------------------------------------------------
    @api.model
    def suggest_risks(self, filters=None):
        self._check_manager()
        payload = self.env["biz.smart.finance.dashboard"].get_dashboard_data(
            filters or {})
        echo = payload["filters"]
        company_ids = (
            [echo["company_id"]] if echo.get("company_id")
            else self.env.user.company_ids.ids
        )
        Risk = self.env["biz.smart.finance.risk"]
        existing_risks = Risk.search([
            ("state", "!=", "closed"), ("company_id", "in", company_ids),
        ])
        existing_names = set(existing_risks.mapped("name"))

        context = {"filters": None}
        for tab in ("overview", "cash", "margin", "ap", "risk", "statements",
                    "controlling"):
            compact = self._compact(tab, payload)
            context["filters"] = compact.pop("filters")
            context.update(compact)
        context["existing_risks"] = sorted(existing_names)

        instruction = (
            "จากข้อมูลการเงินด้านล่าง เสนอความเสี่ยงทางการเงินใหม่ไม่เกิน "
            "%d รายการที่ยังไม่ซ้ำกับ existing_risks แต่ละรายการให้ระบุ "
            "category, impact และ likelihood (1-5), สัญญาณเตือนล่วงหน้า "
            "(early_warning) ที่วัดได้จริง และแผนรับมือ (action) สั้น ๆ "
            "อ้างอิงตัวเลขที่เห็นเท่านั้น\n\nข้อมูล (JSON):\n%s"
        ) % (MAX_SUGGESTED_RISKS, self._dump(context))
        parsed = self._post_chat(
            SYSTEM_PERSONA, instruction, RISK_SCHEMA, "risk_suggestions")

        created, skipped = [], 0
        company_id = echo.get("company_id") or self.env.company.id

        def clamp(value):
            try:
                return max(1, min(5, int(value or 3)))
            except (TypeError, ValueError):
                return 3

        for item in (parsed.get("risks") or [])[:MAX_SUGGESTED_RISKS]:
            raw = (item.get("name") or "").strip()
            if not raw:
                skipped += 1
                continue
            name = "[AI] %s" % raw
            if name in existing_names or raw in existing_names:
                skipped += 1
                continue
            category = item.get("category")
            if category not in dict(Risk._fields["category"].selection):
                category = "other"
            risk = Risk.create({
                "name": name,
                "company_id": company_id,
                "category": category,
                "impact": clamp(item.get("impact")),
                "likelihood": clamp(item.get("likelihood")),
                "early_warning": item.get("early_warning") or "",
                "action": item.get("action") or "",
                "state": "open",
            })
            existing_names.add(name)
            created.append({
                "id": risk.id, "name": risk.name,
                "level": risk.level, "score": risk.score,
            })
        return {
            "summary": parsed.get("summary") or "",
            "created": len(created),
            "skipped": skipped,
            "risks": created,
        }

    # ------------------------------------------------------------------
    # 2b) AI ร่างรายการประจำเข้ากริดพยากรณ์ (manager — เขียนข้อมูล)
    # ------------------------------------------------------------------
    @api.model
    def suggest_forecast(self, filters=None):
        """อ่านค่าใช้จ่ายจริงย้อนหลังแล้วเสนอ "รายการประจำ" เป็น **ร่าง**

        เขียนเป็น state=draft เสมอ — ตัวเลขที่ AI เดาจากบัญชีย้อนหลังต้องมีคน
        การเงินอ่านเหตุผล (`ai_note`) แล้วกดยืนยันก่อน ไม่งั้นกริดพยากรณ์จะ
        ขยับเองโดยไม่มีใครรับผิดชอบตัวเลข
        """
        self._check_manager()
        Dashboard = self.env["biz.smart.finance.dashboard"]
        payload = Dashboard.get_dashboard_data(filters or {})
        echo = payload["filters"]
        company_ids = (
            [echo["company_id"]] if echo.get("company_id")
            else self.env.user.company_ids.ids
        )
        Line = self.env["biz.smart.finance.forecast.line"]
        existing = Line.search([("company_id", "in", company_ids)])
        existing_names = set(existing.mapped("name"))

        context = self._compact("forecast", payload)
        context["history_by_month"] = Dashboard.sudo().monthly_actual_history(
            company_ids, FORECAST_HISTORY_MONTHS)
        context["existing_lines"] = [
            {
                "name": line.name,
                "flow_type": line.flow_type,
                "category": line.category,
                "amount": line.amount,
                "recurrence": line.recurrence,
                "state": line.state,
            }
            for line in existing[:50]
        ]

        instruction = (
            "จากยอดจริงย้อนหลังรายเดือน (history_by_month) และกริดพยากรณ์ "
            "ด้านล่าง ให้เสนอ 'รายการกระแสเงินสดประจำ' ไม่เกิน %d รายการ "
            "ที่ยังไม่มีใน existing_lines — เน้นค่าใช้จ่ายที่เกิดซ้ำทุกเดือน "
            "(เงินเดือน ค่าเช่า สาธารณูปโภค ภาษี) โดยประมาณจำนวนเงินจาก"
            "ค่าเฉลี่ยที่เห็นจริงเท่านั้น ห้ามแต่งตัวเลข ระบุเหตุผล (reason) "
            "ว่าอ่านมาจากตัวเลขไหน\n"
            "นอกจากนี้ให้ระบุ assumption_notes (สมมติฐานที่ผู้ใช้ควรตรวจ เช่น "
            "รอบเก็บเงินลูกค้า ฤดูกาล) และ probability_flags สำหรับดีลใน "
            "pipeline ที่ความน่าจะเป็นดูไม่สมเหตุผลเทียบขั้นการขายหรือวันเซ็น"
            "\n\nข้อมูล (JSON):\n%s"
        ) % (MAX_SUGGESTED_FORECAST_LINES, self._dump(context))
        parsed = self._post_chat(
            SYSTEM_PERSONA, instruction, FORECAST_SUGGEST_SCHEMA,
            "forecast_suggestions")

        company_id = echo.get("company_id") or self.env.company.id
        categories = dict(Line._fields["category"].selection)
        created, skipped = [], 0
        for item in (parsed.get("recurring_lines")
                     or [])[:MAX_SUGGESTED_FORECAST_LINES]:
            raw = (item.get("name") or "").strip()
            try:
                amount = float(item.get("amount") or 0.0)
            except (TypeError, ValueError):
                amount = 0.0
            if not raw or amount <= 0:
                skipped += 1
                continue
            name = "[AI] %s" % raw
            if name in existing_names or raw in existing_names:
                skipped += 1
                continue
            category = item.get("category")
            if category not in categories:
                category = "opex"
            flow_type = "in" if item.get("flow_type") == "in" else "out"
            # หมวดกับทิศทางต้องไม่ขัดกัน — engine แยกขาเงินเข้า/ออกจาก
            # flow_type ก่อนเสมอ แต่หมวดที่ขัดกันทำให้รายงานอ่านสับสน
            if flow_type == "in" and category != "other_in":
                category = "other_in"
            elif flow_type == "out" and category == "other_in":
                category = "other_out"
            recurrence = "weekly" if item.get("recurrence") == "weekly" else "monthly"
            try:
                day_of_month = max(1, min(31, int(item.get("day_of_month") or 25)))
            except (TypeError, ValueError):
                day_of_month = 25
            line = Line.create({
                "name": name,
                "company_id": company_id,
                "flow_type": flow_type,
                "category": category,
                "amount": amount,
                "recurrence": recurrence,
                "day_of_month": day_of_month,
                "state": "draft",
                "ai_note": (item.get("reason") or "")[:512],
            })
            existing_names.add(name)
            created.append({
                "id": line.id, "name": line.name,
                "amount": line.amount, "category": line.category,
            })
        return {
            "summary": parsed.get("summary") or "",
            "created": len(created),
            "skipped": skipped,
            "lines": created,
            "assumption_notes": [
                s for s in (parsed.get("assumption_notes") or []) if s],
            "probability_flags": parsed.get("probability_flags") or [],
        }

    # ------------------------------------------------------------------
    # 3) chat low-level (conversation model เป็นคนเรียก)
    # ------------------------------------------------------------------
    @api.model
    def answer(self, context_text, messages):
        """messages = [{"role": "user"|"assistant", "content": str}, ...]
        flatten เป็นบรรทัดเพราะ _post_chat รับ user message เดียว"""
        lines = []
        for message in messages[:-1]:
            lines.append("%s: %s" % (message["role"], message["content"]))
        question = messages[-1]["content"] if messages else ""
        user_content = ""
        if lines:
            user_content = "บทสนทนาก่อนหน้า:\n%s\n\n" % "\n".join(lines)
        user_content += "คำถามล่าสุด: %s" % question
        system = "%s\n\n%s" % (SYSTEM_PERSONA, context_text)
        parsed = self._post_chat(
            system, user_content, ANSWER_SCHEMA, "cfo_answer",
            max_tokens=2048)
        return {
            "answer": parsed.get("answer") or "",
            "suggestions": [s for s in (parsed.get("suggestions") or []) if s],
        }

    # ------------------------------------------------------------------
    # 4) รายงาน CFO ประจำเดือน (report model เป็นคนเรียก)
    # ------------------------------------------------------------------
    @api.model
    def generate_report(self, compact_context):
        instruction = (
            "เขียนรายงานผู้บริหาร CFO ประจำเดือนฉบับเต็ม เป็น markdown "
            "ภาษาไทย ครอบคลุม: ภาพรวมผลประกอบการ, สภาพคล่องและ cash "
            "forecast 13 สัปดาห์, funnel ขาย-เก็บเงิน, กำไรโครงการและ "
            "leakage, เจ้าหนี้/แผนจ่าย, ความเสี่ยงและ early warning, "
            "และข้อเสนอแนะต่อผู้บริหาร ปิดท้ายด้วยรายการสั่งการ (action items)"
            "\n\nข้อมูล (JSON):\n%s"
        ) % self._dump(compact_context)
        return self._post_chat(
            SYSTEM_PERSONA, instruction, REPORT_SCHEMA,
            "cfo_monthly_report", max_tokens=8192)
