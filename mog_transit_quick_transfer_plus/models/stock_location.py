
# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class StockLocation(models.Model):
    _inherit = "stock.location"

    skip_valuation = fields.Boolean(
        string="No Valuation (Skip Accounting/SVL)",
        help="If enabled, moves to/from this location will not generate stock valuation layers or accounting entries."
    )

    @api.model
    def _should_skip_valuation(self):
        """Check if this location should skip valuation"""
        # If force_valuation is in context, never skip valuation
        if self.env.context.get('force_valuation', False):
            _logger.info("[tqt] Force valuation - location %s will not skip valuation", self.name)
            return False
        
        # Original logic
        return self.skip_valuation
