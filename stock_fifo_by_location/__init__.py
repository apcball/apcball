# -*- coding: utf-8 -*-
"""
Stock FIFO by Location Module for Odoo 17

This module extends Odoo's stock valuation system to support FIFO cost accounting
on a per-location basis. It ensures that cost of goods sold (COGS) calculations
are accurate when inventory is distributed across multiple storage locations.

Usage:
    Install in Odoo 17 with stock and stock_account modules.
    
    The module automatically:
    - Populates location_id when creating stock valuation layers
    - Isolates FIFO queues per location
    - Validates location availability during deliveries
    - Provides configurable shortage handling
    
For more information, see README.md
"""

__version__ = '17.0.1.0.0'
__author__ = 'Custom Development'
__license__ = 'LGPL-3'

from . import models
from . import wizard
from .hooks import post_init_hook
