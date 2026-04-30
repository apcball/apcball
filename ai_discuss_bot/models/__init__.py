# -*- coding: utf-8 -*-

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Load all models
from . import ai_discuss_config
from . import res_partner
from . import mail_channel
from . import mail_message
