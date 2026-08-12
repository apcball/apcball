import json
import logging
import requests

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class HelpdeskLineWebhook(http.Controller):
    @http.route('/buz_it_helpdesk/line/webhook', type='http', auth='public', methods=['POST'], csrf=False)
    def webhook(self, **kwargs):
        body = request.httprequest.get_data()
        signature = request.httprequest.headers.get('X-Line-Signature', '')
        config = request.env['buz.helpdesk.line.config'].sudo().get_singleton()
        if not config.active or not request.env['buz.helpdesk.line.config'].sudo().verify_signature(body, signature):
            return request.make_json_response({'status': 'ok'})
        try:
            payload = json.loads(body.decode('utf-8'))
        except (UnicodeDecodeError, ValueError):
            return request.make_json_response({'status': 'ok'})
        groups = request.env['buz.helpdesk.line.group'].sudo()
        for event in payload.get('events', []):
            source = event.get('source') or {}
            target_id = source.get('groupId') if source.get('type') == 'group' else source.get('roomId') if source.get('type') == 'room' else None
            if not target_id:
                continue
            name = None
            if source.get('type') == 'group':
                try:
                    response = requests.get(
                        'https://api.line.me/v2/bot/group/%s/summary' % target_id,
                        headers={'Authorization': 'Bearer %s' % config.channel_access_token}, timeout=10,
                    )
                    if response.status_code == 200:
                        name = response.json().get('groupName')
                except requests.exceptions.RequestException:
                    pass
            groups.register_webhook_group(target_id, name=name)
        return request.make_json_response({'status': 'ok'})

