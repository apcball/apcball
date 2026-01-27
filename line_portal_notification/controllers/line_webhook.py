# -*- coding: utf-8 -*-
"""
LINE Webhook Controller
=======================

Public HTTP endpoint for receiving LINE Webhook events.
Automatically captures LINE User IDs when users interact with the Official Account.

Webhook URL: /line/webhook
"""

import hashlib
import hmac
import base64
import json
import logging

from odoo import http, fields, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class LineWebhookController(http.Controller):
    """Controller for LINE Webhook events."""

    def _verify_signature(self, body, signature):
        """
        Verify the X-Line-Signature header to ensure request is from LINE.
        
        Args:
            body: Raw request body (bytes)
            signature: X-Line-Signature header value
            
        Returns:
            bool: True if signature is valid
        """
        ICP = request.env['ir.config_parameter'].sudo()
        channel_secret = ICP.get_param('line_portal_notification.channel_secret', '')
        
        if not channel_secret:
            _logger.warning("LINE Channel Secret not configured, skipping signature verification")
            return True  # Skip verification if secret not configured
        
        # Calculate expected signature
        hash_obj = hmac.new(
            channel_secret.encode('utf-8'),
            body,
            hashlib.sha256
        )
        expected_signature = base64.b64encode(hash_obj.digest()).decode('utf-8')
        
        return hmac.compare_digest(signature, expected_signature)

    def _get_user_profile(self, line_user_id):
        """
        Get LINE user profile using the Profile API.
        
        Args:
            line_user_id: LINE User ID
            
        Returns:
            dict: User profile or None
        """
        try:
            import requests
            
            ICP = request.env['ir.config_parameter'].sudo()
            access_token = ICP.get_param('line_portal_notification.channel_access_token', '')
            
            if not access_token:
                return None
            
            response = requests.get(
                f"https://api.line.me/v2/bot/profile/{line_user_id}",
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                _logger.debug("Could not get LINE profile: %s", response.status_code)
                return None
                
        except Exception as e:
            _logger.debug("Error getting LINE profile: %s", str(e))
            return None

    @http.route(
        '/line/webhook',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def line_webhook(self, **kwargs):
        """
        LINE Webhook endpoint.
        
        Receives webhook events from LINE and processes them:
        - Extracts LINE User ID from events
        - Creates/updates line.user records
        - Returns success response
        
        Returns:
            dict: {"status": "ok"}
        """
        try:
            # Get raw body and signature for verification
            raw_body = request.httprequest.get_data()
            signature = request.httprequest.headers.get('X-Line-Signature', '')
            
            # Verify signature (optional but recommended)
            if signature and not self._verify_signature(raw_body, signature):
                _logger.warning("LINE webhook signature verification failed")
                return {'status': 'error', 'message': 'Invalid signature'}
            
            # Parse JSON body
            try:
                data = json.loads(raw_body.decode('utf-8')) if raw_body else {}
            except json.JSONDecodeError:
                # If already parsed by Odoo's json type
                data = request.jsonrequest or {}
            
            events = data.get('events', [])
            
            if not events:
                _logger.debug("LINE webhook received with no events")
                return {'status': 'ok'}
            
            # Process each event
            LineUser = request.env['line.user'].sudo()
            
            for event in events:
                event_type = event.get('type')
                source = event.get('source', {})
                source_type = source.get('type')
                
                _logger.info(
                    "LINE webhook event: type=%s, source_type=%s",
                    event_type, source_type
                )
                
                # Extract user ID based on source type
                line_user_id = None
                
                if source_type == 'user':
                    line_user_id = source.get('userId')
                elif source_type == 'group':
                    # For group events, we can get the user who triggered it
                    line_user_id = source.get('userId')  # May be None for some events
                elif source_type == 'room':
                    line_user_id = source.get('userId')  # May be None for some events
                
                if line_user_id:
                    # Validate format (starts with U and is 33 chars)
                    if line_user_id.startswith('U') and len(line_user_id) == 33:
                        # Try to get display name from profile
                        display_name = None
                        
                        # Only fetch profile for follow events or first-time users
                        if event_type in ['follow', 'message']:
                            profile = self._get_user_profile(line_user_id)
                            if profile:
                                display_name = profile.get('displayName')
                        
                        # Find or create LINE user record
                        LineUser.find_or_create_from_webhook(
                            line_user_id,
                            display_name=display_name
                        )
                    else:
                        _logger.warning(
                            "Invalid LINE User ID format received: %s",
                            line_user_id[:10] + '...' if line_user_id else 'None'
                        )
                
                # Handle specific event types if needed
                if event_type == 'follow':
                    _logger.info("User followed the LINE account: %s", 
                                line_user_id[:10] + '...' if line_user_id else 'Unknown')
                elif event_type == 'unfollow':
                    _logger.info("User unfollowed the LINE account: %s",
                                line_user_id[:10] + '...' if line_user_id else 'Unknown')
                    # Optionally mark user as inactive
                    if line_user_id:
                        existing = LineUser.search([('line_user_id', '=', line_user_id)], limit=1)
                        if existing:
                            existing.write({'active': False})
            
            return {'status': 'ok'}
            
        except Exception as e:
            _logger.exception("Error processing LINE webhook: %s", str(e))
            # Always return 200 OK to LINE to prevent retries
            return {'status': 'ok'}

    @http.route(
        '/line/webhook/verify',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
    )
    def line_webhook_verify(self, **kwargs):
        """
        Simple endpoint to verify webhook URL is accessible.
        """
        return request.make_response(
            json.dumps({'status': 'ok', 'message': 'LINE Webhook endpoint is active'}),
            headers=[('Content-Type', 'application/json')]
        )
