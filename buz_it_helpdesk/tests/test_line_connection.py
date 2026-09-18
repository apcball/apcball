from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = ''

    def json(self):
        return self._payload


@tagged('post_install', '-at_install')
class TestHelpdeskLineBotInfo(TransactionCase):

    def setUp(self):
        super().setUp()
        self.service = self.env['buz.helpdesk.line.service']

    def test_first_connection_load_fetches_and_caches_bot_info(self):
        token = 'legacy-token-without-cached-oa'
        response = FakeResponse(200, {
            'displayName': 'Example Helpdesk',
            'basicId': '@example_bot',
            'pictureUrl': 'https://profile.example/image.png',
        })
        with patch(
            'requests.request',
            return_value=response,
        ) as request:
            result = self.service._public_bot_details(token)
            second_result = self.service._public_bot_details(token)

        self.assertEqual(result['display_name'], 'Example Helpdesk')
        self.assertEqual(result['basic_id'], '@example_bot')
        self.assertEqual(result['picture_url'], 'https://profile.example/image.png')
        self.assertEqual(
            result['add_friend_url'],
            'https://line.me/R/ti/p/%40example_bot',
        )
        self.assertNotIn('token', result)
        self.assertNotIn('secret', result)
        self.assertEqual(second_result, result)
        request.assert_called_once()

    def test_bot_without_picture_still_has_add_friend_url(self):
        response = FakeResponse(200, {
            'displayName': 'No Picture',
            'basicId': '@no_picture',
        })
        with patch(
            'requests.request',
            return_value=response,
        ):
            result = self.service._public_bot_details('token-without-picture')

        self.assertEqual(result['picture_url'], '')
        self.assertEqual(
            result['add_friend_url'],
            'https://line.me/R/ti/p/%40no_picture',
        )

    def _create_requester(self):
        company = self.env.company
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'LINE Connection Test Requester',
            'login': 'line.connection.test.requester',
            'company_id': company.id,
            'company_ids': [Command.set([company.id])],
            'groups_id': [Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('buz_it_helpdesk.group_it_requester').id,
            ])],
        })

    def test_connection_status_fetches_legacy_bot_info_on_first_open(self):
        requester = self._create_requester()
        token = 'legacy-settings-without-oa-cache'
        self.env['ir.config_parameter'].sudo().set_param(
            'buz_it_helpdesk.line_channel_access_token', token
        )
        response = FakeResponse(200, {
            'displayName': 'Legacy OA',
            'basicId': '@legacy_oa',
        })
        with patch('requests.request', return_value=response) as request:
            status = self.service.with_user(requester).get_line_connection_status()

        self.assertFalse(status['connected'])
        self.assertEqual(status['display_name'], 'Legacy OA')
        self.assertEqual(status['basic_id'], '@legacy_oa')
        self.assertEqual(status['picture_url'], '')
        request.assert_called_once()

    def test_webhook_connects_user_with_one_time_code(self):
        requester = self._create_requester()
        user_service = self.service.with_user(requester)
        code = user_service.create_line_connection_code()['code']
        line_user_id = 'U0123456789abcdef0123456789abcdef'
        event = {
            'source': {'type': 'user', 'userId': line_user_id},
            'message': {'type': 'text', 'text': code},
            'replyToken': 'test-reply-token',
        }
        with patch(
            'odoo.addons.buz_it_helpdesk.services.line_service.HelpdeskLineService._send_reply',
            return_value=True,
        ):
            linked = self.service.sudo().process_webhook_event(event)

        self.assertTrue(linked)
        self.assertEqual(
            self.service._parameter(self.service._user_key(requester.id)),
            line_user_id,
        )

    def test_invalid_token_is_rejected_and_not_cached(self):
        response = FakeResponse(401, {'message': 'Unauthorized'})
        with patch(
            'requests.request',
            return_value=response,
        ):
            with self.assertRaises(UserError):
                self.service._public_bot_details('invalid-token')
