from datetime import datetime
import base64
import hashlib
import hmac
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
        cls.support = cls.env['res.users'].create({
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

    def _requester_service(self):
        return self.env['buz.helpdesk.line.service'].with_user(self.requester)

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

    def test_webhook_signature_accepts_only_channel_secret_signature(self):
        body = b'{"events":[]}'
        secret = 'channel-secret'
        self.parameters.set_param(
            'buz_it_helpdesk.line_channel_secret', secret
        )
        signature = base64.b64encode(
            hmac.new(secret.encode(), body, hashlib.sha256).digest()
        ).decode()
        service = self.env['buz.helpdesk.line.service'].sudo()
        self.assertTrue(service.validate_webhook_signature(body, signature))
        self.assertFalse(service.validate_webhook_signature(body, 'invalid'))

    def test_connection_code_is_one_time_and_expired_code_is_ignored(self):
        service = self._requester_service()
        result = service.create_line_connection_code()
        self.assertEqual(len(result['code']), 8)
        raw = self.parameters.get_param(
            service._code_key(self.requester.id)
        )
        self.assertNotIn(result['code'], raw)
        self.parameters.set_param(
            service._code_key(self.requester.id),
            '%s|1' % service._hash_value(result['code']),
        )
        with patch.object(service, '_send_reply') as reply:
            self.assertFalse(service.process_webhook_event({
                'replyToken': 'reply-token',
                'source': {'userId': 'U' + '1' * 32},
                'message': {'type': 'text', 'text': result['code']},
            }))
        reply.assert_called_once()
        self.assertFalse(self.parameters.get_param(
            service._user_key(self.requester.id)
        ))

    def test_group_id_command_replies_without_persisting_group_id(self):
        service = self.env['buz.helpdesk.line.service'].sudo()
        event = {
            'replyToken': 'reply-token',
            'source': {
                'type': 'group',
                'groupId': LINE_GROUP_ID,
                'userId': 'U' + '5' * 32,
            },
            'message': {'type': 'text', 'text': ' group_id '},
        }
        with patch.object(service, '_send_reply') as reply:
            self.assertTrue(service.process_webhook_event(event))
        reply.assert_called_once_with(
            'reply-token',
            'LINE Group ID:\n%s' % LINE_GROUP_ID,
        )

    def test_group_message_does_not_reply_or_enter_connection_flow(self):
        service = self.env['buz.helpdesk.line.service'].sudo()
        event = {
            'replyToken': 'reply-token',
            'source': {
                'type': 'group',
                'groupId': LINE_GROUP_ID,
                'userId': 'U' + '6' * 32,
            },
            'message': {'type': 'text', 'text': 'normal group message'},
        }
        with patch.object(service, '_send_reply') as reply:
            self.assertFalse(service.process_webhook_event(event))
        reply.assert_not_called()

    def test_connection_code_is_consumed_after_successful_mapping(self):
        service = self.env['buz.helpdesk.line.service'].sudo()
        code = 'C0DE1234'
        line_user_id = 'U' + '4' * 32
        self.parameters.set_param(
            service._code_key(self.requester.id),
            '%s|9999999999' % service._hash_value(code),
        )
        with patch.object(service, '_send_reply'):
            event = {
                'replyToken': 'reply-token',
                'source': {'userId': line_user_id},
                'message': {'type': 'text', 'text': code.lower()},
            }
            self.assertTrue(service.process_webhook_event(event))
            self.assertFalse(service.process_webhook_event(event))
        self.assertEqual(
            self.parameters.get_param(service._user_key(self.requester.id)),
            line_user_id,
        )

    def test_connection_rejects_line_mapping_already_owned_by_other_user(self):
        service = self.env['buz.helpdesk.line.service'].sudo()
        code = 'A1B2C3D4'
        line_user_id = 'U' + '2' * 32
        self.parameters.set_param(
            service._code_key(self.requester.id),
            '%s|9999999999' % service._hash_value(code),
        )
        self.parameters.set_param(service._reverse_key(line_user_id), '999')
        with self.assertRaises(ValidationError):
            service.process_webhook_event({
                'replyToken': 'reply-token',
                'source': {'userId': line_user_id},
                'message': {'type': 'text', 'text': code},
            })

    def test_requester_can_create_code_but_cannot_change_manager_settings(self):
        result = self._requester_service().create_line_connection_code()
        self.assertEqual(result['expires_in'], 600)
        with self.assertRaises(AccessError):
            self._requester_service().save_line_settings(
                self.company.id, 'token', LINE_GROUP_ID, 'channel-secret'
            )

    def test_contact_line_requires_connected_requester_and_keeps_stage_on_failure(self):
        ticket = self._ticket('Contact User')
        ticket.with_user(self.manager).with_context(
            buz_helpdesk_transition=True,
        ).write({
            'assigned_user_id': self.support.id,
            'stage_id': self.env.ref('buz_it_helpdesk.stage_in_progress').id,
        })
        with self.assertRaises(UserError):
            ticket.with_user(self.manager).action_send_line_message('Hello')
        self.assertEqual(
            ticket.stage_id, self.env.ref('buz_it_helpdesk.stage_in_progress')
        )

    def test_contact_line_sends_sanitized_message_then_pending_user(self):
        ticket = self._ticket('Contact User')
        ticket.with_user(self.manager).with_context(
            buz_helpdesk_transition=True,
        ).write({
            'assigned_user_id': self.support.id,
            'stage_id': self.env.ref('buz_it_helpdesk.stage_in_progress').id,
        })
        line_user_id = 'U' + '3' * 32
        self.parameters.set_param(
            'buz_it_helpdesk.line_user_id.%s' % self.requester.id,
            line_user_id,
        )
        self._configure()
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request',
            return_value=self._response(200),
        ) as request:
            ticket.with_user(self.manager).action_send_line_message(
                '<p>Hello <b>Requester</b></p>'
            )
        message = request.call_args.kwargs['json']['messages'][0]['text']
        self.assertIn('Hello Requester', message)
        self.assertNotIn('<b>', message)
        self.assertEqual(
            ticket.stage_id, self.env.ref('buz_it_helpdesk.stage_pending_user')
        )

    def _prepare_resolution_ticket(self):
        ticket = self._ticket('Resolution confirmation')
        ticket.with_user(self.manager).with_context(
            buz_helpdesk_transition=True,
        ).write({
            'assigned_user_id': self.support.id,
            'stage_id': self.env.ref('buz_it_helpdesk.stage_in_progress').id,
        })
        self.parameters.set_param(
            'buz_it_helpdesk.line_user_id.%s' % self.requester.id,
            'U' + '7' * 32,
        )
        self._configure()
        return ticket

    def test_mark_resolved_notifies_requester_and_requires_confirmation(self):
        ticket = self._prepare_resolution_ticket()
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request',
            return_value=self._response(200),
        ) as request:
            ticket.with_user(self.support).action_mark_resolved()

        self.assertEqual(
            ticket.stage_id, self.env.ref('buz_it_helpdesk.stage_resolved')
        )
        confirmation = self.env['mail.activity'].search([
            ('res_model', '=', ticket._name),
            ('res_id', '=', ticket.id),
            ('user_id', '=', self.requester.id),
            ('summary', '=', 'Confirm IT Resolution'),
            ('date_done', '=', False),
        ])
        self.assertTrue(confirmation)
        message = request.call_args.kwargs['json']['messages'][0]['text']
        self.assertIn('Status: Resolved', message)
        self.assertIn('/web#id=%s' % ticket.id, message)

    def test_line_failure_does_not_roll_back_resolved_workflow(self):
        ticket = self._prepare_resolution_ticket()
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request',
            side_effect=requests.exceptions.Timeout('LINE timeout'),
        ):
            self.assertTrue(
                ticket.with_user(self.support).action_mark_resolved()
            )
        self.assertEqual(
            ticket.stage_id, self.env.ref('buz_it_helpdesk.stage_resolved')
        )
        self.assertTrue(ticket._resolution_confirmation_activities())

    def test_assigned_it_cannot_close_before_requester_confirmation(self):
        ticket = self._prepare_resolution_ticket()
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request',
            return_value=self._response(200),
        ):
            ticket.with_user(self.support).action_mark_resolved()
        with self.assertRaises(UserError):
            ticket.with_user(self.support).action_close_ticket()

    def test_requester_confirmation_allows_assigned_it_to_close(self):
        ticket = self._prepare_resolution_ticket()
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request',
            return_value=self._response(200),
        ):
            ticket.with_user(self.support).action_mark_resolved()

        ticket.with_user(self.requester).action_confirm_resolution()
        self.assertFalse(ticket._resolution_confirmation_activities())
        ticket.with_user(self.support).action_close_ticket()
        self.assertEqual(
            ticket.stage_id, self.env.ref('buz_it_helpdesk.stage_closed')
        )

    def test_only_requester_can_confirm_resolution(self):
        ticket = self._prepare_resolution_ticket()
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request',
            return_value=self._response(200),
        ):
            ticket.with_user(self.support).action_mark_resolved()
        with self.assertRaises(UserError):
            ticket.with_user(self.support).action_confirm_resolution()

    def test_manager_can_close_without_requester_confirmation(self):
        ticket = self._prepare_resolution_ticket()
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.requests.request',
            return_value=self._response(200),
        ):
            ticket.with_user(self.support).action_mark_resolved()
        ticket.with_user(self.manager).action_close_ticket()
        self.assertEqual(
            ticket.stage_id, self.env.ref('buz_it_helpdesk.stage_closed')
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

    def test_save_and_test_uses_user_timezone_in_message(self):
        self.manager.tz = 'Asia/Bangkok'
        responses = [
            self._response(200, {'displayName': 'Mogen IT Bot'}),
            self._response(200, {
                'groupId': LINE_GROUP_ID,
                'groupName': 'Mogen IT Support',
            }),
            self._response(200),
        ]
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.'
            'fields.Datetime.now',
            return_value=datetime(2026, 8, 15, 14, 55, 56),
        ), patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.'
            'requests.request',
            side_effect=responses,
        ) as request:
            self._manager_service().save_and_test_line_settings(
                self.company.id,
                'new-token',
                LINE_GROUP_ID,
            )
        message = request.call_args_list[2].kwargs['json']['messages'][0][
            'text'
        ]
        self.assertIn(
            'Time: 2026-08-15 21:55:56 (Asia/Bangkok)',
            message,
        )

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
