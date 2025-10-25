# -*- coding: utf-8 -*-

from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to handle compatibility with stock_valuation_layer_usage module
        
        When buz_valuation_regenerate creates new SVLs, we need to ensure that
        stock_valuation_layer_usage doesn't fail due to missing 'taken_data' in context.
        """
        # Check if we're in a regeneration context
        regeneration_context = self.env.context.get('valuation_regeneration', False)
        
        if regeneration_context:
            # During regeneration, we skip the stock_valuation_layer_usage processing
            # by providing an empty taken_data to prevent errors
            new_context = dict(self.env.context)
            if 'taken_data' not in new_context:
                new_context['taken_data'] = [{}]
            
            # Also skip auto-processing of taken_data during regeneration
            # since we're recreating layers from scratch
            new_context['skip_usage_tracking'] = True
            
            return super(StockValuationLayer, self.with_context(new_context)).create(vals_list)
        
        # Normal flow - let stock_valuation_layer_usage handle it
        return super(StockValuationLayer, self).create(vals_list)

    def unlink(self):
        """Override unlink to handle cleanup of usage records when regenerating
        
        When SVLs are deleted during regeneration, we also need to clean up
        the associated usage records to maintain data integrity.
        """
        # Check if we're in a regeneration context
        regeneration_context = self.env.context.get('valuation_regeneration', False)
        
        if regeneration_context:
            # Delete associated usage records if stock_valuation_layer_usage is installed
            if 'stock.valuation.layer.usage' in self.env:
                usage_records = self.env['stock.valuation.layer.usage'].search([
                    '|',
                    ('stock_valuation_layer_id', 'in', self.ids),
                    ('dest_stock_valuation_layer_id', 'in', self.ids),
                ])
                
                if usage_records:
                    _logger.info(
                        f"Cleaning up {len(usage_records)} stock valuation layer usage records "
                        f"during regeneration"
                    )
                    # Use sudo to bypass access rights during cleanup
                    usage_records.sudo().unlink()
        
        return super(StockValuationLayer, self).unlink()
