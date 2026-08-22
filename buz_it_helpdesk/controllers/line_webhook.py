import json
import logging

from odoo import http
from odoo.http import request


_logger = logging.getLogger(__name__)


class HelpdeskLineWebhookController(http.Controller):

    @http.route(
        '/buz_it_helpdesk/line/webhook',
        type='http', auth='none', methods=['POST'], csrf=False,
        save_session=False,
    )
    def line_webhook(self, **kwargs):
        body = request.httprequest.get_data()
        signature = request.httprequest.headers.get('X-Line-Signature', '')
        service = request.env['buz.helpdesk.line.service'].sudo()
        if not service.validate_webhook_signature(body, signature):
            return request.make_response('Forbidden', status=403)
        try:
            payload = json.loads(body.decode('utf-8'))
            for event in payload.get('events', []):
                service.process_webhook_event(event)
        except (ValueError, TypeError):
            _logger.warning('Invalid LINE webhook JSON payload.')
        except Exception:
            _logger.exception('LINE webhook event processing failed.')
        return request.make_response('OK', status=200)
