import base64

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase


class TestTicketItAttachments(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_user = cls.env.ref('base.group_user')
        cls.group_requester = cls.env.ref('buz_it_helpdesk.group_it_requester')
        cls.group_support = cls.env.ref('buz_it_helpdesk.group_it_support_agent')
        cls.group_manager = cls.env.ref('buz_it_helpdesk.group_it_helpdesk_manager')
        cls.support = cls._user('it-attachment-support', cls.group_support)
        cls.manager = cls._user('it-attachment-manager', cls.group_manager)
        cls.requester = cls._user('it-attachment-requester', cls.group_requester)
        cls.team = cls.env['buz.helpdesk.team'].with_user(cls.manager).create({
            'name': 'IT Attachment Team',
            'user_ids': [Command.link(cls.support.id)],
        })
        cls.category = cls.env['buz.helpdesk.category'].create({
            'name': 'IT Attachment Category',
        })

    @classmethod
    def _user(cls, login, group):
        return cls.env['res.users'].create({
            'name': login,
            'login': login,
            'email': f'{login}@example.com',
            'groups_id': [Command.set([cls.group_user.id, group.id])],
        })

    def _ticket(self):
        ticket = self.env['buz.helpdesk.ticket'].with_user(self.manager).create({
            'subject': 'IT attachment ticket',
            'requester_id': self.requester.id,
            'category_id': self.category.id,
            'team_id': self.team.id,
        })
        ticket.with_user(self.manager)._write_workflow_fields({
            'stage_id': self.env.ref('buz_it_helpdesk.stage_new').id,
            'assigned_user_id': self.support.id,
        })
        return ticket

    def _it_attachment(self, ticket):
        attachment = self.env['ir.attachment'].with_user(self.manager).create({
            'name': 'it-evidence.txt',
            'datas': base64.b64encode(b'IT attachment test'),
            'res_model': 'buz.helpdesk.ticket',
            'res_id': ticket.id,
        })
        ticket.with_user(self.manager).write({
            'it_attachment_ids': [Command.link(attachment.id)],
        })
        return attachment

    def test_it_attachment_relation_is_separate_and_readable(self):
        ticket = self._ticket()
        attachment = self._it_attachment(ticket)

        self.assertEqual(ticket.attachment_ids, self.env['ir.attachment'])
        self.assertEqual(ticket.it_attachment_ids, attachment)
        attachment.with_user(self.support).check_access_rule('read')
        attachment.with_user(self.manager).check_access_rule('read')
        self.assertEqual(
            ticket.with_user(self.manager).read(['it_attachment_ids'])[0][
                'it_attachment_ids'
            ],
            [attachment.id],
        )

    def test_it_attachment_support_can_upload_and_delete(self):
        ticket = self._ticket()
        attachment = self.env['ir.attachment'].with_user(self.support).create({
            'name': 'uploaded-by-it.txt',
            'datas': base64.b64encode(b'uploaded by IT'),
            'res_model': 'buz.helpdesk.ticket',
            'res_id': ticket.id,
        })
        ticket.with_user(self.support).write({
            'it_attachment_ids': [Command.link(attachment.id)],
        })
        self.assertIn(attachment, ticket.it_attachment_ids)
        attachment.with_user(self.support).unlink()

    def test_requester_cannot_manage_it_attachment(self):
        ticket = self._ticket()
        attachment = self._it_attachment(ticket)

        with self.assertRaises(UserError):
            ticket.with_user(self.requester).write({
                'it_attachment_ids': [Command.unlink(attachment.id)],
            })
        with self.assertRaises(AccessError):
            attachment.with_user(self.requester).unlink()
