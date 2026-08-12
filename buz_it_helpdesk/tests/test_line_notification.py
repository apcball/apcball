from unittest.mock import Mock, patch
import base64
import hashlib
import hmac
import json

from odoo import Command
from odoo.tests.common import HttpCase, TransactionCase


class TestHelpdeskLineNotification(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_user = cls.env.ref('base.group_user')
        cls.group_requester = cls.env.ref('buz_it_helpdesk.group_it_requester')
        cls.group_support = cls.env.ref('buz_it_helpdesk.group_it_support_agent')
        cls.requester = cls.env['res.users'].create({
            'name': 'LINE Test Requester', 'login': 'line-test-requester', 'email': 'line-requester@example.com',
            'groups_id': [Command.set([cls.group_user.id, cls.group_requester.id])],
        })
        cls.support = cls.env['res.users'].create({
            'name': 'LINE Test Support', 'login': 'line-test-support', 'email': 'line-support@example.com',
            'groups_id': [Command.set([cls.group_user.id, cls.group_support.id])],
        })
        cls.company = cls.env.company
        cls.config = cls.env['buz.helpdesk.line.config'].sudo().get_singleton()
        cls.config.write({'active': True, 'channel_access_token': 'token', 'channel_secret': 'secret'})
        cls.line_group = cls.env['buz.helpdesk.line.group'].sudo().create({
            'name': 'LINE Test Group', 'line_group_id': 'C' + 'a' * 32,
        })

    def _ticket(self, subject='LINE queue test'):
        self.company.write({'helpdesk_line_enabled': True, 'helpdesk_line_group_id': self.line_group.id})
        return self.env['buz.helpdesk.ticket'].with_user(self.requester).create({
            'subject': subject, 'description': 'private description',
        })

    def test_unconfigured_company_does_not_create_queue(self):
        self.company.write({'helpdesk_line_enabled': False, 'helpdesk_line_group_id': False})
        ticket = self.env['buz.helpdesk.ticket'].with_user(self.requester).create({'subject': 'No LINE'})
        ticket.action_create_ticket()
        self.assertFalse(self.env['buz.helpdesk.line.queue'].sudo().search([('ticket_id', '=', ticket.id)]))

    def test_new_ticket_creates_one_snapshot_queue(self):
        ticket = self._ticket()
        ticket.action_create_ticket()
        queue = self.env['buz.helpdesk.line.queue'].sudo().search([('ticket_id', '=', ticket.id)])
        self.assertEqual(len(queue), 1)
        self.assertIn(ticket.subject, queue.message)
        self.assertNotIn('private description', queue.message)
        self.assertEqual(queue.target_id, self.line_group.line_group_id)

    def test_queue_marks_sent_on_200_and_409(self):
        ticket = self._ticket('Send test')
        ticket.action_create_ticket()
        queue = self.env['buz.helpdesk.line.queue'].sudo().search([('ticket_id', '=', ticket.id)])
        response = Mock(status_code=200)
        with patch('odoo.addons.buz_it_helpdesk.services.line_service.requests.post', return_value=response):
            self.assertTrue(queue._process_one())
        self.assertEqual(queue.state, 'sent')

        ticket2 = self._ticket('Retry key test')
        ticket2.action_create_ticket()
        queue2 = self.env['buz.helpdesk.line.queue'].sudo().search([('ticket_id', '=', ticket2.id)])
        with patch('odoo.addons.buz_it_helpdesk.services.line_service.requests.post', return_value=Mock(status_code=409)):
            self.assertTrue(queue2._process_one())
        self.assertEqual(queue2.state, 'sent')

    def test_signature_and_webhook_group_registration_are_deterministic(self):
        body = b'{"events":[]}'
        digest = hmac.new(b'secret', body, hashlib.sha256).digest()
        signature = base64.b64encode(digest).decode()
        self.assertTrue(self.config.verify_signature(body, signature))
        self.assertFalse(self.config.verify_signature(body, 'invalid'))
        groups = self.env['buz.helpdesk.line.group'].sudo()
        groups.register_webhook_group('R' + 'b' * 32, 'Room')
        groups.register_webhook_group('R' + 'b' * 32, 'Room renamed')
        room = groups.search([('line_group_id', '=', 'R' + 'b' * 32)])
        self.assertEqual(len(room), 1)
        self.assertEqual(room.event_count, 2)
        self.assertEqual(room.name, 'Room renamed')

    def test_webhook_url_is_editable(self):
        custom_url = 'https://helpdesk.example.com/buz_it_helpdesk/line/webhook'
        self.config.write({'webhook_url': custom_url})
        self.assertEqual(self.config.webhook_url, custom_url)


class TestHelpdeskLineWebhook(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env['buz.helpdesk.line.config'].sudo().get_singleton()
        cls.config.write({
            'active': True,
            'channel_access_token': 'token',
            'channel_secret': 'secret',
        })

    def _post_webhook(self, body, signature):
        return self.url_open(
            '/buz_it_helpdesk/line/webhook',
            data=body,
            headers={
                'Content-Type': 'application/json',
                'X-Line-Signature': signature,
            },
        )

    def test_webhook_rejects_bad_signature_with_http_200(self):
        response = self._post_webhook(b'{"events":[]}', 'invalid')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_webhook_accepts_valid_signature_with_http_200(self):
        body = b'{"events":[]}'
        digest = hmac.new(b'secret', body, hashlib.sha256).digest()
        signature = base64.b64encode(digest).decode()
        response = self._post_webhook(body, signature)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})
