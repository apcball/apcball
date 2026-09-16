# -*- coding: utf-8 -*-
"""CFO Copilot — บทสนทนาเก็บใน DB (ir.rule จำกัดเห็นเฉพาะของตัวเอง)
context สร้างฝั่ง server จาก engine เสมอ — client ไม่มีทางส่งตัวเลขเอง"""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError

CHAT_HISTORY_LIMIT = 20


class BsfConversation(models.Model):
    _name = "biz.smart.finance.conversation"
    _description = "Smart Finance CFO Copilot Conversation"
    _order = "last_activity desc"

    name = fields.Char(string="ชื่อบทสนทนา", required=True,
                       default="การสนทนาใหม่")
    user_id = fields.Many2one(
        "res.users", string="ผู้ใช้", required=True, index=True,
        ondelete="cascade", default=lambda self: self.env.user,
    )
    message_ids = fields.One2many(
        "biz.smart.finance.message", "conversation_id", string="ข้อความ",
    )
    last_activity = fields.Datetime(
        string="ใช้งานล่าสุด", default=fields.Datetime.now,
    )

    def _check_user(self):
        if self.env.su:
            return
        if not self.env.user.has_group("biz_smart_finance.group_bsf_user"):
            raise AccessError(_("ต้องเป็นสมาชิกกลุ่ม CFO Cockpit / Viewer"))

    @api.model
    def create_and_send(self, question, filters=None):
        self._check_user()
        conversation = self.create({
            "name": (question or "การสนทนาใหม่")[:60],
        })
        return conversation.chat_send(question, filters)

    def chat_send(self, question, filters=None):
        self.ensure_one()
        self._check_user()
        self.env["biz.smart.finance.message"].create({
            "conversation_id": self.id, "role": "user",
            "content": question or "",
        })
        context_text = self._build_context(filters)
        history = self.message_ids.sorted("id")[-CHAT_HISTORY_LIMIT:]
        messages = [
            {"role": message.role, "content": message.content}
            for message in history
        ]
        result = self.env["biz.smart.finance.ai"].answer(
            context_text, messages)
        self.env["biz.smart.finance.message"].create({
            "conversation_id": self.id, "role": "assistant",
            "content": result["answer"],
        })
        self.last_activity = fields.Datetime.now()
        return {
            "answer": result["answer"],
            "suggestions": result["suggestions"],
            "conversation_id": self.id,
            "name": self.name,
        }

    def _build_context(self, filters):
        ai = self.env["biz.smart.finance.ai"]
        payload = self.env["biz.smart.finance.dashboard"].get_dashboard_data(
            filters or {})
        context = {"filters": None}
        for tab in ("overview", "cash", "forecast", "risk"):
            compact = ai._compact(tab, payload)
            context["filters"] = compact.pop("filters")
            context.update(compact)
        return (
            "ข้อมูลการเงินปัจจุบันจาก CFO Cockpit (JSON):\n%s\n\n"
            "ตอบจากข้อมูลข้างต้นเท่านั้น ถ้าข้อมูลไม่พอให้บอกว่าต้องดูแท็บไหน"
            "ของ CFO Cockpit หรือให้กรอกข้อมูลส่วนไหนเพิ่ม"
        ) % ai._dump(context)

    def get_messages(self):
        self.ensure_one()
        self._check_user()
        return [
            {"id": message.id, "role": message.role,
             "content": message.content}
            for message in self.message_ids.sorted("id")
        ]

    @api.model
    def list_conversations(self):
        self._check_user()
        # ir.rule จำกัด user_id อยู่แล้ว — โดเมนซ้ำไว้เป็น defence in depth
        conversations = self.search(
            [("user_id", "=", self.env.uid)], limit=30)
        return [
            {"id": conv.id, "name": conv.name,
             "last_activity": fields.Datetime.to_string(conv.last_activity)}
            for conv in conversations
        ]


class BsfMessage(models.Model):
    _name = "biz.smart.finance.message"
    _description = "Smart Finance CFO Copilot Message"
    _order = "id"

    conversation_id = fields.Many2one(
        "biz.smart.finance.conversation", string="บทสนทนา", required=True,
        ondelete="cascade", index=True,
    )
    role = fields.Selection(
        [("user", "ผู้ใช้"), ("assistant", "AI")],
        string="ฝ่าย", required=True,
    )
    content = fields.Text(string="ข้อความ", required=True)
