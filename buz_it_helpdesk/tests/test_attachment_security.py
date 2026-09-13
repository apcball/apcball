import base64

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase


class TestHelpdeskAttachmentSecurity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_user = cls.env.ref('base.group_user')
        cls.group_requester = cls.env.ref('buz_it_helpdesk.group_it_requester')
        cls.group_support = cls.env.ref('buz_it_helpdesk.group_it_support_agent')
        cls.group_manager = cls.env.ref('buz_it_helpdesk.group_it_helpdesk_manager')
        cls.stage_draft = cls.env.ref('buz_it_helpdesk.stage_draft')
        cls.stage_new = cls.env.ref('buz_it_helpdesk.stage_new')
        cls.requester = cls._user('attachment-requester', cls.group_requester)
        cls.other_requester = cls._user('attachment-other', cls.group_requester)
        cls.support = cls._user('attachment-support', cls.group_support)
        cls.manager = cls._user('attachment-manager', cls.group_manager)
        cls.category = cls.env['buz.helpdesk.category'].create({
            'name': 'Attachment Security Category',
        })

    @classmethod
    def _user(cls, login, group):
        return cls.env['res.users'].create({
            'name': login,
            'login': login,
            'email': f'{login}@example.com',
            'groups_id': [Command.set([cls.group_user.id, group.id])],
        })

    def _ticket(self, requester):
        return self.env['buz.helpdesk.ticket'].with_user(self.manager).create({
            'subject': 'Attachment security ticket',
            'requester_id': requester.id,
            'category_id': self.category.id,
        })

    def _attachment(self, ticket):
        attachment = self.env['ir.attachment'].with_user(self.manager).create({
            'name': 'evidence.txt',
            'datas': base64.b64encode(b'attachment security test'),
            'res_model': 'buz.helpdesk.ticket',
            'res_id': ticket.id,
        })
        ticket.with_user(self.manager).write({
            'attachment_ids': [Command.link(attachment.id)],
        })
        return attachment

    def test_requester_reads_only_own_ticket_attachment(self):
        own_ticket = self._ticket(self.requester)
        other_ticket = self._ticket(self.other_requester)
        own_attachment = self._attachment(own_ticket)
        other_attachment = self._attachment(other_ticket)

        own_attachment.with_user(self.requester).check_access_rule('read')
        with self.assertRaises(AccessError):
            other_attachment.with_user(self.requester).check_access_rule('read')
        self.assertEqual(
            own_ticket.with_user(self.requester).read(['attachment_ids'])[0][
                'attachment_ids'
            ],
            [own_attachment.id],
        )
        self.assertEqual(
            other_ticket.with_user(self.requester).read(['attachment_ids'])[0][
                'attachment_ids'
            ],
            [],
        )

    def test_requester_cannot_manage_other_ticket_attachment(self):
        ticket = self._ticket(self.other_requester)
        attachment = self._attachment(ticket)

        with self.assertRaises(UserError):
            self.env['ir.attachment'].with_user(self.requester).create({
                'name': 'blocked.txt',
                'datas': base64.b64encode(b'blocked'),
                'res_model': 'buz.helpdesk.ticket',
                'res_id': ticket.id,
            })
        with self.assertRaises(AccessError):
            attachment.with_user(self.requester).unlink()
        with self.assertRaises(UserError):
            ticket.with_user(self.requester).write({
                'attachment_ids': [Command.unlink(attachment.id)],
            })

    def test_requester_can_manage_own_draft_attachment(self):
        ticket = self._ticket(self.requester)
        attachment = self._attachment(ticket)

        ticket.with_user(self.requester).write({
            'attachment_ids': [Command.unlink(attachment.id)],
        })

    def test_requester_cannot_manage_own_attachment_after_draft(self):
        ticket = self._ticket(self.requester)
        attachment = self._attachment(ticket)
        ticket.with_user(self.manager)._write_workflow_fields({
            'stage_id': self.stage_new.id,
        })

        with self.assertRaises(AccessError):
            attachment.with_user(self.requester).unlink()

    def test_support_and_manager_retain_attachment_access(self):
        ticket = self._ticket(self.requester)
        attachment = self._attachment(ticket)

        attachment.with_user(self.support).check_access_rule('read')
        attachment.with_user(self.manager).check_access_rule('read')
