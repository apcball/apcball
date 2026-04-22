# -*- coding: utf-8 -*-
# File: models/res_config_settings.py
# Purpose: Extend Inventory configuration settings to include the
#          "Low Stock Threshold" parameter for the Stock Enhanced Checker.

from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    """
    Extend res.config.settings to add the Low Stock Threshold setting.
    This value is stored as an ir.config_parameter and controls the
    orange warning color in the Stock Enhanced Checker dashboard.
    """
    _inherit = 'res.config.settings'

    low_stock_threshold = fields.Integer(
        string='Low Stock Threshold',
        default=5,
        config_parameter='stock_enhanced_checker.low_stock_threshold',
        help='Products with available qty below this value are shown in orange '
             'in the Stock Enhanced Checker dashboard.',
    )
