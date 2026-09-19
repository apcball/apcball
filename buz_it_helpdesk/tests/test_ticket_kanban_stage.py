from odoo.tests.common import TransactionCase


class TestTicketKanbanStage(TransactionCase):
    """ตรวจสอบการตั้งค่ากลุ่มสถานะสำหรับ Kanban Ticket"""

    def test_draft_is_visible_and_folded(self):
        draft = self.env.ref('buz_it_helpdesk.stage_draft')

        self.assertTrue(draft.show_in_kanban)
        self.assertTrue(draft.fold)

    def test_ticket_actions_include_draft_records(self):
        tickets_action = self.env.ref('buz_it_helpdesk.action_helpdesk_tickets')
        my_tickets_action = self.env.ref(
            'buz_it_helpdesk.action_helpdesk_my_tickets'
        )

        self.assertNotIn('stage_draft', tickets_action.domain or '')
        self.assertNotIn('stage_draft', my_tickets_action.domain or '')

    def test_ticket_kanban_groups_by_stage(self):
        kanban_view = self.env.ref('buz_it_helpdesk.view_helpdesk_ticket_kanban')

        self.assertIn('default_group_by="stage_id"', kanban_view.arch_db)
