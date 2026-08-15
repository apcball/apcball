from unittest.mock import Mock, patch

import requests

from odoo import Command
from odoo.tests.common import TransactionCase


TOKEN_PARAMETER = 'buz_it_helpdesk.line_channel_access_token'
GROUP_PARAMETER = 'buz_it_helpdesk.line_group_id'


class TestHelpdeskLineNotification(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('base.group_user')
        group_requester = cls.env.ref(
            'buz_it_helpdesk.group_it_requester'
        )
        group_support = cls.env.ref(
            'buz_it_helpdesk.group_it_support_agent'
        )
        cls.requester = cls.env['res.users'].create({
            'name': 'LINE Test Requester',
            'login': 'line-test-requester',
            'email': 'line-requester@example.com',
            'groups_id': [Command.set([
                group_user.id,
                group_requester.id,
            ])],
        })
        cls.env['res.users'].create({
            'name': 'LINE Test Support',
            'login': 'line-test-support',
            'email': 'line-support@example.com',
            'groups_id': [Command.set([
                group_user.id,
                group_support.id,
            ])],
        })
        cls.company = cls.env.company
        cls.parameters = cls.env['ir.config_parameter'].sudo()

    def setUp(self):
        super().setUp()
        for key in (
            TOKEN_PARAMETER,
            GROUP_PARAMETER,
            '%s.%s' % (TOKEN_PARAMETER, self.company.id),
            '%s.%s' % (GROUP_PARAMETER, self.company.id),
        ):
            self.parameters.set_param(key, '')

    def _configure(self, token='test-token', group_id=None):
        group_id = group_id or ('C' + 'a' * 32)
        self.parameters.set_param(TOKEN_PARAMETER, token)
        self.parameters.set_param(GROUP_PARAMETER, group_id)
        return group_id

    def _ticket(self, subject='LINE direct notification'):
        return self.env['buz.helpdesk.ticket'].with_user(
            self.requester
        ).create({
            'subject': subject,
            'description': 'private description',
        })

    def test_company_parameters_override_global_values(self):
        self._configure(token='global-token', group_id='C' + 'a' * 32)
        self.parameters.set_param(
            '%s.%s' % (TOKEN_PARAMETER, self.company.id),
            ' company-token ',
        )
        self.parameters.set_param(
            '%s.%s' % (GROUP_PARAMETER, self.company.id),
            'C' + 'b' * 32,
        )
        values = self.env[
            'buz.helpdesk.line.service'
        ].sudo().connection_values(self.company)
        self.assertEqual(values['token'], 'company-token')
        self.assertEqual(values['group_id'], 'C' + 'b' * 32)

    def test_unconfigured_line_does_not_call_external_api(self):
        ticket = self._ticket('No LINE configuration')
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.post'
        ) as post:
            ticket.action_create_ticket()
        post.assert_not_called()
        self.assertEqual(
            ticket.stage_id,
            self.env.ref('buz_it_helpdesk.stage_new'),
        )

    def test_new_ticket_sends_line_message(self):
        group_id = self._configure()
        ticket = self._ticket()
        response = Mock(status_code=200)
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.post',
            return_value=response,
        ) as post:
            ticket.action_create_ticket()
        post.assert_called_once()
        call = post.call_args
        self.assertEqual(call.kwargs['json']['to'], group_id)
        message = call.kwargs['json']['messages'][0]['text']
        self.assertIn(ticket.subject, message)
        self.assertNotIn('private description', message)
        self.assertIn(ticket.requester_id.display_name, message)
        self.assertIn(ticket.company_id.display_name, message)
        self.assertIn('/web#id=%s' % ticket.id, message)

    def test_line_timeout_does_not_roll_back_ticket_submission(self):
        self._configure()
        ticket = self._ticket('LINE timeout')
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.post',
            side_effect=requests.exceptions.Timeout('LINE timeout'),
        ):
            self.assertTrue(ticket.action_create_ticket())
        self.assertEqual(
            ticket.stage_id,
            self.env.ref('buz_it_helpdesk.stage_new'),
        )

    def test_line_http_error_does_not_roll_back_ticket_submission(self):
        self._configure()
        ticket = self._ticket('LINE HTTP error')
        response = Mock(status_code=401, text='Authentication failed')
        response.json.return_value = {'message': 'Authentication failed'}
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.post',
            return_value=response,
        ):
            self.assertTrue(ticket.action_create_ticket())
        self.assertEqual(
            ticket.stage_id,
            self.env.ref('buz_it_helpdesk.stage_new'),
        )
