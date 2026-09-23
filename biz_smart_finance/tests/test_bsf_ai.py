# -*- coding: utf-8 -*-
"""เทสฟีเจอร์ AI — ห้ามยิง network: patch requests.post / _post_chat เสมอ
DB ที่รันมีข้อมูลจริง (shared dev DB) จึง assert แบบ delta เท่านั้น"""
import json
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase

from odoo.addons.biz_smart_finance.models.bsf_ai_service import (
    BsfAiService, LONG_LIST_KEYS, MAX_ROWS,
)

CANNED_BRIEF = {
    "summary": "สรุปทดสอบ",
    "insights": ["ประเด็นที่หนึ่ง", "ประเด็นที่สอง"],
    "actions": [
        {"name": "เร่งเก็บเงินลูกหนี้", "priority": 1, "reason": "AR สูง"},
        {"name": "เลื่อนจ่าย supplier", "priority": 2, "reason": "รักษาเงินสด"},
    ],
}

CANNED_ANSWER = {"answer": "คำตอบทดสอบ", "suggestions": ["ถามต่อเรื่อง DSO"]}

CANNED_REPORT = {"title": "รายงานทดสอบ", "content": "# หัวข้อ\n- ประเด็น"}


class FakeResponse:
    status_code = 200

    def __init__(self, parsed):
        self._parsed = parsed

    def json(self):
        return {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps(self._parsed)},
            }],
        }


class TestBsfAi(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Users = cls.env["res.users"]
        base_group = cls.env.ref("base.group_user").id
        cls.plain_user = Users.create({
            "name": "AI Plain", "login": "bsf_ai_plain",
            "groups_id": [(6, 0, [base_group])],
            "company_id": cls.company.id,
            "company_ids": [(6, 0, [cls.company.id])],
        })
        cls.viewer = Users.create({
            "name": "AI Viewer", "login": "bsf_ai_viewer",
            "groups_id": [(6, 0, [
                base_group,
                cls.env.ref("biz_smart_finance.group_bsf_user").id,
            ])],
            "company_id": cls.company.id,
            "company_ids": [(6, 0, [cls.company.id])],
        })
        cls.viewer2 = Users.create({
            "name": "AI Viewer 2", "login": "bsf_ai_viewer2",
            "groups_id": [(6, 0, [
                base_group,
                cls.env.ref("biz_smart_finance.group_bsf_user").id,
            ])],
            "company_id": cls.company.id,
            "company_ids": [(6, 0, [cls.company.id])],
        })
        cls.manager = Users.create({
            "name": "AI Manager", "login": "bsf_ai_manager",
            "groups_id": [(6, 0, [
                base_group,
                cls.env.ref("biz_smart_finance.group_bsf_manager").id,
            ])],
            "company_id": cls.company.id,
            "company_ids": [(6, 0, [cls.company.id])],
        })
        cls.env["ir.config_parameter"].sudo().set_param(
            "biz_smart_finance.openrouter_api_key", "test-key")
        cls.filters = {"company_id": cls.company.id}

    def _ai(self, user):
        return self.env["biz.smart.finance.ai"].with_user(user)

    # ------------------------------------------------------------------
    # gates
    # ------------------------------------------------------------------
    def test_gates(self):
        with self.assertRaises(AccessError):
            self._ai(self.plain_user).generate_brief("overview", {})
        with self.assertRaises(AccessError):
            self.env["biz.smart.finance.conversation"].with_user(
                self.plain_user).create_and_send("ถาม", {})
        with self.assertRaises(AccessError):
            self.env["biz.smart.finance.report"].with_user(
                self.plain_user).generate({})
        # viewer เขียน register ไม่ได้ — suggest_risks ต้อง manager
        with self.assertRaises(AccessError):
            self._ai(self.viewer).suggest_risks({})

    def test_missing_key(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "biz_smart_finance.openrouter_api_key", "")
        self.assertFalse(self.env["biz.smart.finance.ai"].is_configured())
        with self.assertRaises(UserError) as err:
            self._ai(self.viewer).generate_brief("overview", self.filters)
        self.assertIn("การตั้งค่า", str(err.exception))
        payload = self.env["biz.smart.finance.dashboard"].with_user(
            self.manager).get_dashboard_data(self.filters)
        self.assertFalse(payload["ai"]["configured"])
        self.assertTrue(payload["ai"]["is_manager"])
        hint_codes = {h["code"] for h in payload["empty_hints"]}
        self.assertIn("no_ai_key", hint_codes)
        no_key = [h for h in payload["empty_hints"] if h["code"] == "no_ai_key"]
        self.assertFalse(no_key[0]["model"])
        # viewer ไม่เห็น hint นี้ (เปิด Settings ไม่ได้)
        viewer_payload = self.env["biz.smart.finance.dashboard"].with_user(
            self.viewer).get_dashboard_data(self.filters)
        self.assertNotIn(
            "no_ai_key", {h["code"] for h in viewer_payload["empty_hints"]})

    # ------------------------------------------------------------------
    # compaction
    # ------------------------------------------------------------------
    def _assert_lists_bounded(self, node, path=""):
        """เพดานเดียวกับที่ `_bound_lists` บังคับจริง — ซีรีส์ที่ลงทะเบียนใน
        LONG_LIST_KEYS ยาวได้ตามที่ประกาศ (ตัดแล้วโมเดลอ่านแนวโน้มผิด)"""
        if isinstance(node, list):
            key = path.rsplit(".", 1)[-1]
            self.assertLessEqual(
                len(node), LONG_LIST_KEYS.get(key, MAX_ROWS), path)
            for item in node:
                self._assert_lists_bounded(item, path)
        elif isinstance(node, dict):
            for key, value in node.items():
                self._assert_lists_bounded(value, "%s.%s" % (path, key))

    def test_compact_all_tabs(self):
        engine = self.env["biz.smart.finance.dashboard"].with_user(self.viewer)
        payload = engine.get_dashboard_data(self.filters)
        ai = self.env["biz.smart.finance.ai"]
        for tab in ("overview", "cash", "forecast", "sales", "margin",
                    "ap", "risk"):
            compact = ai._compact(tab, payload)
            self._assert_lists_bounded(compact, tab)
            self.assertIn("company_label", compact["filters"])
            dumped = json.dumps(compact, default=str)
            for banned in ("bubbles", "heatmap", "calendar", "before_ap",
                           "planned_ap"):
                self.assertNotIn('"%s"' % banned, dumped, tab)

    # ------------------------------------------------------------------
    # brief
    # ------------------------------------------------------------------
    def test_generate_brief(self):
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["payload"] = json
            return FakeResponse(CANNED_BRIEF)

        with patch(
            "odoo.addons.biz_smart_finance.models.bsf_ai_service"
            ".requests.post", side_effect=fake_post,
        ):
            result = self._ai(self.viewer).generate_brief(
                "cash", self.filters)
        self.assertEqual(result["summary"], "สรุปทดสอบ")
        self.assertEqual(len(result["actions"]), 2)
        request = captured["payload"]
        self.assertTrue(
            request["response_format"]["json_schema"]["strict"])
        self.assertEqual(
            request["response_format"]["json_schema"]["name"], "cfo_brief")
        self.assertEqual(request["messages"][0]["role"], "system")
        self.assertIn("ล้านบาท", request["messages"][0]["content"])

    def test_generate_brief_unknown_tab(self):
        with self.assertRaises(UserError):
            self._ai(self.viewer).generate_brief("nonsense", self.filters)

    # ------------------------------------------------------------------
    # suggest_risks + dedupe
    # ------------------------------------------------------------------
    def test_suggest_risks_dedupe(self):
        Risk = self.env["biz.smart.finance.risk"]
        existing = Risk.create({
            "name": "ลูกค้ารายใหญ่จ่ายช้า", "company_id": self.company.id,
            "impact": 3, "likelihood": 3,
        })
        canned = {
            "summary": "พบความเสี่ยง",
            "risks": [
                {"name": "ลูกค้ารายใหญ่จ่ายช้า", "category": "ar",
                 "impact": 4, "likelihood": 4,
                 "early_warning": "AR > 60 วันเพิ่ม", "action": "ทวงถาม"},
                {"name": "เงินสดต่ำช่วง Q4", "category": "cash",
                 "impact": 9, "likelihood": 0,
                 "early_warning": "closing < min", "action": "เลื่อนจ่าย"},
                {"name": "ต้นทุนเหล็กขึ้น", "category": "weird_category",
                 "impact": 3, "likelihood": 2,
                 "early_warning": "ราคาเหล็ก +8%", "action": "ล็อกราคา"},
            ],
        }
        before = Risk.search_count([])
        with patch.object(BsfAiService, "_post_chat", return_value=canned):
            result = self._ai(self.manager).suggest_risks(self.filters)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(Risk.search_count([]) - before, 2)
        created = Risk.browse([r["id"] for r in result["risks"]])
        for risk in created:
            self.assertTrue(risk.name.startswith("[AI] "))
            self.assertEqual(risk.state, "open")
            self.assertTrue(1 <= risk.impact <= 5)
            self.assertTrue(1 <= risk.likelihood <= 5)
        categories = set(created.mapped("category"))
        self.assertIn("other", categories)  # fallback จาก weird_category
        # รันซ้ำ — ทุกตัวซ้ำหมด
        with patch.object(BsfAiService, "_post_chat", return_value=canned):
            result2 = self._ai(self.manager).suggest_risks(self.filters)
        self.assertEqual(result2["created"], 0)
        self.assertEqual(Risk.search_count([]) - before, 2)
        self.assertTrue(existing.exists())

    # ------------------------------------------------------------------
    # suggest_forecast
    # ------------------------------------------------------------------
    def test_suggest_forecast_creates_drafts(self):
        Line = self.env["biz.smart.finance.forecast.line"]
        canned = {
            "summary": "เห็นค่าใช้จ่ายซ้ำทุกเดือน",
            "recurring_lines": [
                {"name": "เงินเดือนพนักงาน", "flow_type": "out",
                 "category": "payroll", "amount": 850000.0,
                 "recurrence": "monthly", "day_of_month": 28,
                 "reason": "ค่าเฉลี่ย 12 เดือน"},
                # หมวดขัดกับทิศทาง → ต้องถูกแก้ให้สอดคล้อง ไม่ใช่ปฏิเสธ
                {"name": "ดอกเบี้ยรับ", "flow_type": "in",
                 "category": "opex", "amount": 12000.0,
                 "recurrence": "monthly", "day_of_month": 99,
                 "reason": "เงินฝากประจำ"},
                # ยอดไม่บวก → ข้าม
                {"name": "รายการว่าง", "flow_type": "out",
                 "category": "opex", "amount": 0.0,
                 "recurrence": "monthly", "day_of_month": 5,
                 "reason": "-"},
            ],
            "assumption_notes": ["ตรวจรอบเก็บเงินลูกค้า"],
            "probability_flags": [
                {"deal_name": "ดีล A", "issue": "ความน่าจะเป็นสูงเกินขั้นการขาย"},
            ],
        }
        with patch.object(BsfAiService, "_post_chat", return_value=canned):
            result = self._ai(self.manager).suggest_forecast(self.filters)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["skipped"], 1)
        created = Line.browse([line["id"] for line in result["lines"]])
        for line in created:
            self.assertEqual(line.state, "draft")
            self.assertTrue(line.name.startswith("[AI] "))
            self.assertTrue(line.ai_note)
            self.assertTrue(1 <= line.day_of_month <= 31)
        income = created.filtered(lambda l: l.flow_type == "in")
        self.assertEqual(income.category, "other_in")
        # รันซ้ำต้องไม่สร้างซ้ำ
        with patch.object(BsfAiService, "_post_chat", return_value=canned):
            again = self._ai(self.manager).suggest_forecast(self.filters)
        self.assertEqual(again["created"], 0)

    def test_suggest_forecast_is_manager_only(self):
        with self.assertRaises(AccessError):
            self._ai(self.viewer).suggest_forecast(self.filters)

    def test_forecast_compact_keeps_full_series(self):
        engine = self.env["biz.smart.finance.dashboard"].with_user(self.viewer)
        payload = engine.get_dashboard_data(self.filters)
        compact = self.env["biz.smart.finance.ai"]._compact("forecast", payload)
        months = payload["forecast"]["months"]
        self.assertGreater(len(months), MAX_ROWS)
        # ซีรีส์รายเดือนต้องไม่ถูกตัดเหลือ MAX_ROWS ไม่งั้นโมเดลอ่านจุดต่ำสุดผิด
        self.assertEqual(len(compact["forecast"]["months"]), len(months))
        self.assertEqual(len(compact["forecast"]["cash"]["closing"]), len(months))
        self.assertEqual(len(compact["forecast"]["pnl"]["revenue"]), len(months))
        # ตาราง (ไม่ใช่ซีรีส์) ยังต้องถูกตัดตามเพดานเดิม
        self.assertLessEqual(len(compact["forecast"]["ctc"]["rows"]), MAX_ROWS)
        self.assertNotIn('"rows": [{"index"', json.dumps(compact, default=str))

    # ------------------------------------------------------------------
    # chat
    # ------------------------------------------------------------------
    def test_chat_flow(self):
        Conversation = self.env["biz.smart.finance.conversation"]
        with patch.object(BsfAiService, "_post_chat",
                          return_value=CANNED_ANSWER):
            result = Conversation.with_user(self.viewer).create_and_send(
                "เงินสดพอไหม", self.filters)
        self.assertEqual(result["answer"], "คำตอบทดสอบ")
        conversation = Conversation.with_user(self.viewer).browse(
            result["conversation_id"])
        self.assertEqual(conversation.name, "เงินสดพอไหม")
        messages = conversation.get_messages()
        self.assertEqual([m["role"] for m in messages], ["user", "assistant"])
        # viewer2 มองไม่เห็นบทสนทนาของ viewer (ir.rule)
        other = Conversation.with_user(self.viewer2).list_conversations()
        self.assertNotIn(
            result["conversation_id"], [c["id"] for c in other])

    def test_chat_history_trimmed(self):
        Conversation = self.env["biz.smart.finance.conversation"]
        with patch.object(BsfAiService, "_post_chat",
                          return_value=CANNED_ANSWER):
            result = Conversation.with_user(self.viewer).create_and_send(
                "คำถามแรก", self.filters)
        conversation = Conversation.with_user(self.viewer).browse(
            result["conversation_id"])
        Message = self.env["biz.smart.finance.message"].with_user(self.viewer)
        for index in range(30):
            Message.create({
                "conversation_id": conversation.id,
                "role": "user", "content": "คำถาม %d" % index,
            })
        captured = {}

        def fake_answer(model_self, context_text, messages):
            captured["messages"] = messages
            return CANNED_ANSWER

        with patch.object(BsfAiService, "answer", fake_answer):
            conversation.chat_send("คำถามสุดท้าย", self.filters)
        from odoo.addons.biz_smart_finance.models.bsf_ai_chat import (
            CHAT_HISTORY_LIMIT,
        )
        self.assertLessEqual(len(captured["messages"]), CHAT_HISTORY_LIMIT)
        self.assertEqual(captured["messages"][-1]["content"], "คำถามสุดท้าย")

    # ------------------------------------------------------------------
    # report
    # ------------------------------------------------------------------
    def test_report_lifecycle(self):
        Report = self.env["biz.smart.finance.report"]
        with patch.object(BsfAiService, "_post_chat",
                          return_value=CANNED_REPORT):
            result = Report.with_user(self.viewer).generate(self.filters)
        self.assertEqual(result["state"], "done")
        record = Report.with_user(self.viewer).browse(result["id"])
        self.assertEqual(record.name, "รายงานทดสอบ")
        self.assertIn("หัวข้อ", record.content)
        # ล้มเหลว: record ต้องคงอยู่ในสถานะ error (ไม่ raise ต่อ — กัน rollback)
        with patch.object(
            BsfAiService, "_post_chat",
            side_effect=UserError("โมเดล AI ไม่ตอบกลับ"),
        ):
            failed = Report.with_user(self.viewer).generate(self.filters)
        self.assertEqual(failed["state"], "error")
        failed_record = Report.with_user(self.viewer).browse(failed["id"])
        self.assertEqual(failed_record.state, "error")
        self.assertIn("ไม่ตอบกลับ", failed_record.error_message)
