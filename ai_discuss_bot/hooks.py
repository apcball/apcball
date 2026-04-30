# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID, _
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """
    Post-installation hook to create AI Bot partner and channel.
    Compatible with Odoo 17 API.
    """
    # Check if models are properly loaded
    if 'discuss.channel' not in env:
        _logger.error("discuss.channel model not found in env.")
        return

    if 'res.partner' not in env:
        _logger.error("res.partner model not found in env.")
        return

    # Check if models are ready
    try:
        Partner = env['res.partner'].sudo()
        Channel = env['discuss.channel'].sudo()
    except Exception as e:
        _logger.error("Error accessing models: %s", e)
        return

    # Create or update AI Bot partner
    bot_partner = Partner.search([('is_ai_bot', '=', True)], limit=1)
    if not bot_partner:
        _logger.info("Creating AI Bot partner")
        bot_partner = Partner.create({
            'name': 'AI Bot',
            'is_ai_bot': True,
            'active': True,
            'email': 'ai.bot@odoo.local',
        })
    else:
        _logger.info("Updating existing AI Bot partner")
        bot_partner.write({
            'name': 'AI Bot',
            'is_ai_bot': True,
            'active': True,
            'email': 'ai.bot@odoo.local',
        })

    # Create or update AI Bot channel
    channel = Channel.search([('is_ai_bot_channel', '=', True)], limit=1)
    channel_vals = {
        'name': 'AI Bot',
        'channel_type': 'channel',
        'is_ai_bot_channel': True,
        'ai_bot_partner_id': bot_partner.id,
        'description': _('AI-powered channel for stock and document search queries'),
    }

    if not channel:
        _logger.info("Creating AI Bot channel")
        channel = Channel.create(channel_vals)
    else:
        _logger.info("Updating existing AI Bot channel")
        channel.write(channel_vals)

    # Add bot partner to channel using Odoo 17's channel_member_ids
    try:
        # In Odoo 17, we use discuss.channel.member
        if 'discuss.channel.member' in env:
            # Check if bot is already a member
            bot_member = env['discuss.channel.member'].search([
                ('channel_id', '=', channel.id),
                ('partner_id', '=', bot_partner.id)
            ], limit=1)

            if not bot_member:
                env['discuss.channel.member'].create({
                    'channel_id': channel.id,
                    'partner_id': bot_partner.id,
                })
                _logger.info("Added AI Bot partner to channel")

            # Add active internal users to the channel
            user_partners = env['res.users'].sudo().search([
                ('share', '=', False),
                ('active', '=', True),
                ('partner_id', '!=', False),
                ('partner_id', '!=', bot_partner.id),
            ]).mapped('partner_id')

            for partner in user_partners:
                existing_member = env['discuss.channel.member'].search([
                    ('channel_id', '=', channel.id),
                    ('partner_id', '=', partner.id)
                ], limit=1)

                if not existing_member:
                    env['discuss.channel.member'].create({
                        'channel_id': channel.id,
                        'partner_id': partner.id,
                    })

            _logger.info("Added %d users to AI Bot channel", len(user_partners))
        else:
            _logger.warning("discuss.channel.member model not found, skipping member management")

    except Exception as e:
        _logger.error("Error adding members to AI Bot channel: %s", e)
        raise

    _logger.info("AI Discuss Bot initialization completed successfully")
