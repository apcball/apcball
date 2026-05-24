# -*- coding: utf-8 -*-
"""Migrate bot_client_id → bot_api_token on res_company + update config params."""

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Copy old bot_client_id values to new bot_api_token field
    cr.execute("""
        ALTER TABLE res_company ADD COLUMN IF NOT EXISTS bot_api_token VARCHAR;
    """)
    cr.execute("""
        UPDATE res_company
        SET bot_api_token = bot_client_id
        WHERE bot_client_id IS NOT NULL AND bot_api_token IS NULL;
    """)
    _logger.info("Migrated bot_client_id → bot_api_token on res_company")

    # Update config parameters for new gateway
    cr.execute("""
        UPDATE ir_config_parameter
        SET value = 'https://gateway.api.bot.or.th'
        WHERE key = 'hostname_TH_BOT';
    """)
    cr.execute("""
        UPDATE ir_config_parameter
        SET value = '/Stat-ExchangeRate/v2/DAILY_AVG_EXG_RATE/'
        WHERE key = 'route_TH_BOT_exchange_daily';
    """)
    _logger.info("Updated BOT API hostname and route config parameters")
