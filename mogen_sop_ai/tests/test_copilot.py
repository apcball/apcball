from odoo.tests.common import TransactionCase


class TestCopilotConversation(TransactionCase):
    def test_conversation_can_be_cleared_by_its_owner(self):
        conversation = self.env["mogen.sop.ai.conversation"].create({
            "name": "Test conversation", "user_id": self.env.user.id, "company_id": self.env.company.id,
        })
        self.env["mogen.sop.ai.message"].create({
            "conversation_id": conversation.id, "role": "user", "content": "Which product is at risk?",
        })
        conversation.action_clear()
        self.assertFalse(conversation.exists())
