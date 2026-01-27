# -*- coding: utf-8 -*-
"""
LINE Channel Verification
==========================
Provides a wizard to verify LINE channel configuration and test user friendships.
"""

import logging
import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LineChannelVerification(models.TransientModel):
    _name = 'line.channel.verification'
    _description = 'LINE Channel Verification Wizard'
    
    bot_display_name = fields.Char('Bot Display Name', readonly=True)
    bot_user_id = fields.Char('Bot User ID', readonly=True)
    bot_basic_id = fields.Char('Bot Basic ID', readonly=True)
    bot_chat_mode = fields.Char('Chat Mode', readonly=True)
    
    test_user_id = fields.Char('Test User ID', help='Enter a LINE User ID to test if they can receive messages')
    test_result = fields.Text('Test Result', readonly=True)
    
    token_configured = fields.Boolean('Token Configured', readonly=True, default=False)
    
    @api.model
    def default_get(self, fields_list):
        """Load current bot configuration"""
        res = super().default_get(fields_list)
        
        try:
            line_api = self.env['line.api.service']
            token = line_api._get_channel_access_token()
            
            if token:
                res['token_configured'] = True
                
                # Get bot info from LINE API
                response = requests.get(
                    'https://api.line.me/v2/bot/info',
                    headers={'Authorization': f'Bearer {token}'},
                    timeout=10
                )
                
                if response.status_code == 200:
                    bot_info = response.json()
                    res['bot_display_name'] = bot_info.get('displayName')
                    res['bot_user_id'] = bot_info.get('userId')
                    res['bot_basic_id'] = bot_info.get('basicId')
                    res['bot_chat_mode'] = bot_info.get('chatMode')
                else:
                    _logger.error("Failed to get bot info: %s", response.text)
                    
        except Exception as e:
            _logger.error("Error loading bot configuration: %s", str(e))
            res['token_configured'] = False
            
        return res
    
    def action_test_user_id(self):
        """Test if a user can receive messages"""
        self.ensure_one()
        
        if not self.test_user_id:
            raise UserError(_("Please enter a User ID to test"))
        
        user_id = self.test_user_id.strip()
        
        try:
            line_api = self.env['line.api.service']
            
            # Try sending a test message
            line_api.send_push_message(
                user_id,
                '✅ Success! You can receive messages from this LINE Official Account.'
            )
            
            self.test_result = f"✅ SUCCESS!\n\n" \
                             f"User {user_id} can receive messages from:\n" \
                             f"• Bot: {self.bot_display_name}\n" \
                             f"• Basic ID: {self.bot_basic_id}\n\n" \
                             f"A test message has been sent to this user."
                             
        except UserError as e:
            error_msg = str(e)
            
            if "Failed to send messages" in error_msg:
                self.test_result = f"❌ FRIENDSHIP ISSUE\n\n" \
                                 f"User {user_id} is NOT a friend of:\n" \
                                 f"• Bot: {self.bot_display_name}\n" \
                                 f"• Basic ID: {self.bot_basic_id}\n\n" \
                                 f"POSSIBLE CAUSES:\n" \
                                 f"1. User has not added this bot as a friend\n" \
                                 f"2. User has blocked the bot\n" \
                                 f"3. User added a DIFFERENT LINE Official Account\n\n" \
                                 f"SOLUTION:\n" \
                                 f"Ask user to add: https://line.me/R/ti/p/{self.bot_basic_id}"
            else:
                self.test_result = f"❌ ERROR\n\n{error_msg}"
                
        except Exception as e:
            self.test_result = f"❌ UNEXPECTED ERROR\n\n{str(e)}"
        
        return {'type': 'ir.actions.do_nothing'}
    
    def action_refresh_bot_info(self):
        """Refresh bot information"""
        self.ensure_one()
        
        try:
            line_api = self.env['line.api.service']
            token = line_api._get_channel_access_token()
            
            response = requests.get(
                'https://api.line.me/v2/bot/info',
                headers={'Authorization': f'Bearer {token}'},
                timeout=10
            )
            
            if response.status_code == 200:
                bot_info = response.json()
                self.write({
                    'bot_display_name': bot_info.get('displayName'),
                    'bot_user_id': bot_info.get('userId'),
                    'bot_basic_id': bot_info.get('basicId'),
                    'bot_chat_mode': bot_info.get('chatMode'),
                    'token_configured': True,
                })
            else:
                raise UserError(_("Failed to get bot info: %s") % response.text)
                
        except Exception as e:
            raise UserError(_("Error: %s") % str(e))
        
        return {'type': 'ir.actions.do_nothing'}
