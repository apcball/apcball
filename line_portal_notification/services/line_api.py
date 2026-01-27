# -*- coding: utf-8 -*-
"""
LINE Messaging API Service
==========================

This service handles all communication with the LINE Messaging API.
Supports push messages with proper error handling and logging.

LINE Messaging API Documentation:
https://developers.line.biz/en/reference/messaging-api/
"""

import json
import logging
import requests

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# LINE API Endpoints
LINE_API_BASE_URL = "https://api.line.me/v2/bot"
LINE_PUSH_MESSAGE_ENDPOINT = f"{LINE_API_BASE_URL}/message/push"
LINE_VALIDATE_TOKEN_ENDPOINT = "https://api.line.me/v2/oauth/verify"

# Request timeout in seconds
REQUEST_TIMEOUT = 15


class LineApiService(models.AbstractModel):
    _name = 'line.api.service'
    _description = 'LINE Messaging API Service'

    @api.model
    def _get_channel_access_token(self):
        """
        Get LINE Channel Access Token from configuration.
        
        Returns:
            str: Channel access token
            
        Raises:
            UserError: If token is not configured
        """
        ICP = self.env['ir.config_parameter'].sudo()
        token = ICP.get_param('line_portal_notification.channel_access_token', '')
        
        if not token:
            raise UserError(_(
                "LINE Channel Access Token is not configured. "
                "Please go to Settings > General Settings > LINE Notification "
                "and enter your Channel Access Token."
            ))
        
        return token

    @api.model
    def _get_channel_secret(self):
        """
        Get LINE Channel Secret from configuration.
        
        Returns:
            str: Channel secret
        """
        ICP = self.env['ir.config_parameter'].sudo()
        return ICP.get_param('line_portal_notification.channel_secret', '')

    @api.model
    def _get_headers(self):
        """
        Build HTTP headers for LINE API requests.
        
        Returns:
            dict: HTTP headers
        """
        access_token = self._get_channel_access_token()
        return {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }

    @api.model
    def send_push_message(self, line_user_id, message, retry_count=0, max_retries=3):
        """
        Send a push message to a LINE user.
        
        Args:
            line_user_id: The LINE user ID to send to
            message: The message text to send
            retry_count: Current retry attempt (internal use)
            max_retries: Maximum number of retry attempts
            
        Returns:
            bool: True if successful
            
        Raises:
            UserError: If message fails to send after all retries
        """
        if not line_user_id or not str(line_user_id).strip():
            raise UserError(_("LINE User ID is required to send a message."))
        
        line_user_id = str(line_user_id).strip()
        
        # Strict format check: starts with U (User), C (Group), or R (Room) followed by 32 hex chars.
        # Total length is 33.
        import re
        if not re.match(r'^[UCR][0-9a-fA-F]{32}$', line_user_id):
             raise UserError(_(
                 "Invalid LINE User ID format: '%s'.\n\n"
                 "It looks like you entered a LINE Display ID (e.g., 'apcball').\n"
                 "The system requires the internal LINE API User ID, which always starts with 'U' and is 33 characters long "
                 "(e.g., 'U1234567890abcdef1234567890abcdef').\n\n"
                 "Please check the LINE Developers Console or ask the user to interact with the LINE Official Account to get their User ID."
             ) % line_user_id)

        headers = self._get_headers()

        payload = {
            'to': line_user_id,
            'messages': [
                {
                    'type': 'text',
                    'text': message,
                }
            ]
        }
        
        _logger.info(
            "Sending LINE push message to user %s (attempt %d/%d). Payload: %s",
            line_user_id,
            retry_count + 1,
            max_retries,
            json.dumps(payload)
        )
        
        try:
            response = requests.post(
                LINE_PUSH_MESSAGE_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            
            # Log response for debugging
            _logger.debug("LINE API response: %s - %s", response.status_code, response.text)
            
            # Handle response
            if response.status_code == 200:
                _logger.info("LINE push message sent successfully to %s", line_user_id[:8] + '...')
                return True
                
            elif response.status_code == 400:
                # Bad request - likely invalid user ID or message format
                error_data = response.json() if response.text else {}
                error_message = error_data.get('message', 'Bad request')
                
                # Check for detailed validation errors
                details = error_data.get('details', [])
                if details:
                    error_message += "\nDetails:"
                    for detail in details:
                        detail_msg = detail.get('message', 'Unknown error')
                        if detail.get('property'):
                            detail_msg += f" (Property: '{detail.get('property')}')"
                        error_message += f"\n- {detail_msg}"
                
                # Check for common "Not a friend" error
                if "Failed to send messages" in error_message or "Invalid user ID" in error_message:
                    error_message += "\n\n⚠️ Troubleshooting Guide:\n" \
                                     "1. Is the USER ID correct? Ensure it's not a Display Name.\n" \
                                     "2. Is the user a friend of THIS specific bot?\n" \
                                     "   (User IDs are unique to each provider/channel. An ID from Bot A won't work for Bot B)\n" \
                                     "3. Has the user blocked the bot?"

                _logger.error("LINE API bad request: %s. User ID was: %r", error_message, line_user_id)
                # EXPOSE THE ID TO THE USER FOR DEBUGGING
                raise UserError(_("LINE API Error: %s\n(Debug info: User ID='%s', Length=%d)") % (error_message, line_user_id, len(line_user_id)))
                
            elif response.status_code == 401:
                # Invalid access token
                _logger.error("LINE API authentication failed - invalid access token")
                raise UserError(_(
                    "LINE API authentication failed. "
                    "Please check your Channel Access Token in Settings."
                ))
                
            elif response.status_code == 403:
                # User has blocked the bot or not friend
                _logger.warning("LINE user %s has blocked the bot or is not a friend", line_user_id[:8] + '...')
                raise UserError(_(
                    "Cannot send message: User has blocked the LINE account or is not a friend."
                ))
                
            elif response.status_code == 429:
                # Rate limited - retry with backoff
                if retry_count < max_retries:
                    import time
                    wait_time = 2 ** retry_count  # Exponential backoff
                    _logger.warning("LINE API rate limited, retrying in %d seconds...", wait_time)
                    time.sleep(wait_time)
                    return self.send_push_message(line_user_id, message, retry_count + 1, max_retries)
                else:
                    raise UserError(_("LINE API rate limit exceeded. Please try again later."))
                    
            elif response.status_code >= 500:
                # Server error - retry
                if retry_count < max_retries:
                    import time
                    wait_time = 2 ** retry_count
                    _logger.warning("LINE API server error, retrying in %d seconds...", wait_time)
                    time.sleep(wait_time)
                    return self.send_push_message(line_user_id, message, retry_count + 1, max_retries)
                else:
                    raise UserError(_("LINE API server error. Please try again later."))
                    
            else:
                # Other errors - try to parse JSON if possible
                try:
                    error_data = response.json() if response.text else {}
                    error_message = error_data.get('message', response.text)
                    # Check for details even here
                    details = error_data.get('details', [])
                    if details:
                        error_message += "\nDetails:"
                        for detail in details:
                            detail_msg = detail.get('message', 'Unknown error')
                            if detail.get('property'):
                                detail_msg += f" (Property: '{detail.get('property')}')"
                            error_message += f"\n- {detail_msg}"
                except ValueError:
                    # Not JSON
                    error_message = response.text or "Unknown Error"

                error_text = f"HTTP {response.status_code}: {error_message}"
                _logger.error("LINE API unexpected error: %s", error_text)
                raise UserError(_("LINE API Error: %s") % error_text)
                
        except requests.exceptions.Timeout:
            _logger.error("LINE API request timed out")
            if retry_count < max_retries:
                return self.send_push_message(line_user_id, message, retry_count + 1, max_retries)
            raise UserError(_("LINE API request timed out. Please try again."))
            
        except requests.exceptions.ConnectionError as e:
            _logger.error("LINE API connection error: %s", str(e))
            if retry_count < max_retries:
                import time
                time.sleep(1)
                return self.send_push_message(line_user_id, message, retry_count + 1, max_retries)
            raise UserError(_("Cannot connect to LINE API. Please check your internet connection."))
            
        except requests.exceptions.RequestException as e:
            _logger.error("LINE API request error: %s", str(e))
            raise UserError(_("LINE API Error: %s") % str(e))

    @api.model
    def send_flex_message(self, line_user_id, alt_text, flex_contents):
        """
        Send a Flex Message to a LINE user.
        Flex Messages allow for rich, customizable layouts.
        
        Args:
            line_user_id: The LINE user ID to send to
            alt_text: Alternative text for notifications
            flex_contents: Flex message JSON structure
            
        Returns:
            bool: True if successful
        """
        if not line_user_id:
            raise UserError(_("LINE User ID is required to send a message."))
        
        headers = self._get_headers()
        
        payload = {
            'to': line_user_id,
            'messages': [
                {
                    'type': 'flex',
                    'altText': alt_text,
                    'contents': flex_contents,
                }
            ]
        }
        
        try:
            response = requests.post(
                LINE_PUSH_MESSAGE_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            
            if response.status_code == 200:
                return True
            else:
                error_text = response.text or f"HTTP {response.status_code}"
                raise UserError(_("LINE API Error: %s") % error_text)
                
        except requests.exceptions.RequestException as e:
            raise UserError(_("LINE API Error: %s") % str(e))

    @api.model
    def validate_access_token(self):
        """
        Validate the configured LINE Channel Access Token.
        
        Returns:
            dict: Token info if valid
            
        Raises:
            UserError: If token is invalid
        """
        access_token = self._get_channel_access_token()
        
        try:
            response = requests.get(
                LINE_VALIDATE_TOKEN_ENDPOINT,
                params={'access_token': access_token},
                timeout=REQUEST_TIMEOUT,
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise UserError(_("LINE Channel Access Token is invalid."))
                
        except requests.exceptions.RequestException as e:
            raise UserError(_("Failed to validate token: %s") % str(e))

    @api.model
    def build_approval_flex_message(self, doc_name, amount, portal_url, company_name=None):
        """
        Build a Flex Message for approval requests.
        
        Args:
            doc_name: Document reference
            amount: Document amount
            portal_url: Portal URL for approval
            company_name: Optional company name
            
        Returns:
            dict: Flex message contents
        """
        body_contents = [
            {
                "type": "text",
                "text": "📄 Document Awaiting Approval",
                "weight": "bold",
                "size": "lg",
                "color": "#1DB446",
            },
            {
                "type": "separator",
                "margin": "md",
            },
            {
                "type": "box",
                "layout": "vertical",
                "margin": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": f"Ref: {doc_name}",
                        "size": "md",
                        "color": "#555555",
                    },
                ],
            },
        ]
        
        if amount:
            body_contents.append({
                "type": "text",
                "text": f"Amount: {amount}",
                "size": "md",
                "color": "#555555",
                "margin": "sm",
            })
        
        return {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": body_contents,
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "action": {
                            "type": "uri",
                            "label": "Review & Approve",
                            "uri": portal_url,
                        },
                        "style": "primary",
                        "color": "#1DB446",
                    },
                ],
            },
        }
