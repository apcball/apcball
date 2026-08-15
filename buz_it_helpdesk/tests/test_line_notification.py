from unittest.mock import Mock, patch

import requests

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


TOKEN_PARAMETER = 'buz_it_helpdesk.line_channel_access_token'
GROUP_PREFIX = 'buz_it_helpdesk.line_group_id'
LINE_GROUP_ID = 'C' + 'a' * 32


class TestHelpdeskLineNotification(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company_two = cls.env['res.company'].create({
            'name': 'LINE Test Company Two',
        })
        cls.company_denied = cls.env['res.company'].create({
            'name': 'LINE Test Company Denied',
        })
        group_user = cls.env.ref('base.group_user')
        group_requester = cls.env.ref(
            'buz_it_helpdesk.group_it_requester'
        )
        group_support = cls.env.ref(
            'buz_it_helpdesk.group_it_support_agent'
        )
        group_manager = cls.env.ref(
            'buz_it_helpdesk.group_it_helpdesk_manager'
        )
        cls.requester = cls.env['res.users'].create({
            'name': 'LINE Test Requester',
            'login': 'line-test-requester',
            'email': 'line-requester@example.com',
            'company_id': cls.company.id,
            'company_ids': [Command.set([cls.company.id])],
            'groups_id': [Command.set([
                group_user.id,
                group_requester.id,
            ])],
        })
        cls.env['res.users'].create({
            'name': 'LINE Test Support',
            'login': 'line-test-support',
            'email': 'line-support@example.com',
            'company_id': cls.company.id,
            'company_ids': [Command.set([cls.company.id])],
            'groups_id': [Command.set([
                group_user.id,
                group_support.id,
            ])],
        })
        cls.manager = cls.env['res.users'].create({
            'name': 'LINE Test Manager',
            'login': 'line-test-manager',
            'email': 'line-manager@example.com',
            'company_id': cls.company.id,
            'company_ids': [Command.set([
                cls.company.id,
                cls.company_two.id,
            ])],
            'groups_id': [Command.set([
                group_user.id,
                group_manager.id,
            ])],
        })
        cls.parameters = cls.env['ir.config_parameter'].sudo()

    def setUp(self):
        super().setUp()
        for key in (
            TOKEN_PARAMETER,
            GROUP_PREFIX,
            self._group_key(self.company),
            self._group_key(self.company_two),
            self._group_key(self.company_denied),
        ):
            self.parameters.set_param(key, '')

    def _group_key(self, company):
        return '%s.%s' % (GROUP_PREFIX, company.id)

    def _manager_service(self):
        return self.env['buz.helpdesk.line.service'].with_user(
            self.manager
        ).with_context(
            allowed_company_ids=[self.company.id, self.company_two.id]
        )

    def _configure(self, company=None, token='test-token', group_id=None):
        company = company or self.company
        group_id = group_id or LINE_GROUP_ID
        self.parameters.set_param(TOKEN_PARAMETER, token)
        self.parameters.set_param(self._group_key(company), group_id)
        return group_id

    def _ticket(self, subject='LINE direct notification'):
        return self.env['buz.helpdesk.ticket'].with_user(
            self.requester
        ).create({
            'subject': subject,
            'description': 'private description',
        })

    def _response(self, status=200, payload=None, text=''):
        response = Mock(status_code=status, text=text)
        response.json.return_value = payload or {}
        return response

    def test_settings_require_helpdesk_manager(self):
        service = self.env['buz.helpdesk.line.service'].with_user(
            self.requester
        )
        with self.assertRaises(AccessError):
            service.get_line_settings(self.company.id)
        with self.assertRaises(AccessError):
            service.save_line_settings(
                self.company.id,
                'secret-token',
                LINE_GROUP_ID,
            )

    def test_settings_reject_company_outside_allowed_companies(self):
        with self.assertRaises(AccessError):
            self._manager_service().get_line_settings(
                self.company_denied.id
            )

    def test_get_settings_never_returns_saved_token(self):
        self._configure()
        result = self._manager_service().get_line_settings(self.company.id)
        self.assertTrue(result['token_configured'])
        self.assertNotIn('token', result)
        self.assertNotIn('test-token', str(result))
        self.assertEqual(result['group_id'], LINE_GROUP_ID)

    def test_save_uses_one_global_token_and_company_group(self):
        result = self._manager_service().save_line_settings(
            self.company.id,
            ' shared-token ',
            ' C' + 'b' * 32 + ' ',
        )
        self.assertTrue(result['token_configured'])
        self.assertEqual(
            self.parameters.get_param(TOKEN_PARAMETER),
            'shared-token',
        )
        self.assertEqual(
            self.parameters.get_param(self._group_key(self.company)),
            'C' + 'b' * 32,
        )
        self.assertFalse(
            self.parameters.get_param(self._group_key(self.company_two))
        )

    def test_blank_token_keeps_existing_token(self):
        self.parameters.set_param(TOKEN_PARAMETER, 'existing-token')
        self._manager_service().save_line_settings(
            self.company.id,
            '',
            LINE_GROUP_ID,
        )
        self.assertEqual(
            self.parameters.get_param(TOKEN_PARAMETER),
            'existing-token',
        )

    def test_group_must_match_line_group_id_format(self):
        with self.assertRaises(ValidationError):
            self._manager_service().save_line_settings(
                self.company.id,
                'token',
                'not-a-group-id',
            )

    def test_legacy_global_group_is_never_used_as_fallback(self):
        self.parameters.set_param(TOKEN_PARAMETER, 'token')
        self.parameters.set_param(GROUP_PREFIX, LINE_GROUP_ID)
        values = self.env[
            'buz.helpdesk.line.service'
        ].sudo()._connection_values(self.company_two)
        self.assertEqual(values['token'], 'token')
        self.assertFalse(values['group_id'])

    def test_save_and_test_confirms_bot_group_and_sends_message(self):
        bot = self._response(200, {
            'displayName': 'Mogen IT Bot',
            'basicId': '@mogenit',
        })
        group = self._response(200, {
            'groupId': LINE_GROUP_ID,
            'groupName': 'Mogen IT Support',
        })
        push = self._response(200)
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request',
            side_effect=[bot, group, push],
        ) as request:
            result = self._manager_service().save_and_test_line_settings(
                self.company.id,
                'new-token',
                LINE_GROUP_ID,
            )
        self.assertEqual(request.call_count, 3)
        self.assertEqual(result['bot_name'], 'Mogen IT Bot')
        self.assertEqual(result['bot_basic_id'], '@mogenit')
        self.assertEqual(result['group_name'], 'Mogen IT Support')
        self.assertEqual(result['group_id'], LINE_GROUP_ID)
        self.assertEqual(
            self.parameters.get_param(TOKEN_PARAMETER),
            'new-token',
        )
        self.assertEqual(
            self.parameters.get_param(self._group_key(self.company)),
            LINE_GROUP_ID,
        )
        push_call = request.call_args_list[2]
        self.assertEqual(push_call.args[:2], (
            'POST',
            'https://api.line.me/v2/bot/message/push',
        ))
        self.assertEqual(push_call.kwargs['json']['to'], LINE_GROUP_ID)
        self.assertIn('[TEST] IT Helpdesk', push_call.kwargs['json'][
            'messages'
        ][0]['text'])

    def test_invalid_token_does_not_save_settings(self):
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request',
            return_value=self._response(401),
        ):
            with self.assertRaises(UserError):
                self._manager_service().save_and_test_line_settings(
                    self.company.id,
                    'invalid-token',
                    LINE_GROUP_ID,
                )
        self.assertFalse(self.parameters.get_param(TOKEN_PARAMETER))
        self.assertFalse(
            self.parameters.get_param(self._group_key(self.company))
        )

    def test_bot_must_be_member_of_selected_group(self):
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request',
            side_effect=[
                self._response(200, {'displayName': 'Bot'}),
                self._response(404),
            ],
        ):
            with self.assertRaises(UserError):
                self._manager_service().save_and_test_line_settings(
                    self.company.id,
                    'token',
                    LINE_GROUP_ID,
                )
        self.assertFalse(self.parameters.get_param(TOKEN_PARAMETER))

    def test_line_timeout_during_settings_test_does_not_save(self):
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request',
            side_effect=requests.exceptions.Timeout('LINE timeout'),
        ):
            with self.assertRaises(UserError):
                self._manager_service().save_and_test_line_settings(
                    self.company.id,
                    'token',
                    LINE_GROUP_ID,
                )
        self.assertFalse(self.parameters.get_param(TOKEN_PARAMETER))

    def test_rate_limit_during_test_push_does_not_save(self):
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request',
            side_effect=[
                self._response(200, {'displayName': 'Bot'}),
                self._response(200, {
                    'groupId': LINE_GROUP_ID,
                    'groupName': 'IT',
                }),
                self._response(429),
            ],
        ):
            with self.assertRaises(UserError):
                self._manager_service().save_and_test_line_settings(
                    self.company.id,
                    'token',
                    LINE_GROUP_ID,
                )
        self.assertFalse(self.parameters.get_param(TOKEN_PARAMETER))

    def test_unconfigured_company_does_not_call_external_api(self):
        ticket = self._ticket('No LINE configuration')
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request'
        ) as request:
            ticket.action_create_ticket()
        request.assert_not_called()
        self.assertEqual(
            ticket.stage_id,
            self.env.ref('buz_it_helpdesk.stage_new'),
        )

    def test_new_ticket_sends_line_message_to_company_group(self):
        group_id = self._configure()
        ticket = self._ticket()
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request',
            return_value=self._response(200),
        ) as request:
            ticket.action_create_ticket()
        request.assert_called_once()
        call = request.call_args
        self.assertEqual(call.args[0], 'POST')
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
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request',
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
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request',
            return_value=self._response(401),
        ):
            self.assertTrue(ticket.action_create_ticket())
        self.assertEqual(
            ticket.stage_id,
            self.env.ref('buz_it_helpdesk.stage_new'),
        )
