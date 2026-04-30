# -*- coding: utf-8 -*-
import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)

class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    is_ai_bot_channel = fields.Boolean(string='AI Bot Channel', default=False, index=True)
    ai_bot_partner_id = fields.Many2one('res.partner', string='AI Bot Partner', readonly=True, ondelete='set null')
