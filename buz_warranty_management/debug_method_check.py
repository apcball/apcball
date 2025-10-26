#!/usr/bin/env python3
"""
Debug script to check if action_view_warranty_cards method exists on product models
"""
import logging

_logger = logging.getLogger(__name__)

def check_method_existence(env):
    """
    Check if the action_view_warranty_cards method exists on different models
    """
    _logger.info("=== DEBUG: Checking method existence ===")
    
    # Check if method exists on product.template
    try:
        template_model = env['product.template']
        has_method_template = hasattr(template_model, 'action_view_warranty_cards')
        _logger.info(f"product.template has action_view_warranty_cards: {has_method_template}")
        
        if has_method_template:
            _logger.info(f"Method type: {type(getattr(template_model, 'action_view_warranty_cards', None))}")
        
    except Exception as e:
        _logger.error(f"Error checking product.template: {e}")
    
    # Check if method exists on product.product
    try:
        product_model = env['product.product']
        has_method_product = hasattr(product_model, 'action_view_warranty_cards')
        _logger.info(f"product.product has action_view_warranty_cards: {has_method_product}")
        
        if has_method_product:
            _logger.info(f"Method type: {type(getattr(product_model, 'action_view_warranty_cards', None))}")
        
    except Exception as e:
        _logger.error(f"Error checking product.product: {e}")
    
    # Check inheritance chain
    try:
        product_record = env['product.product'].search([], limit=1)
        if product_record:
            _logger.info(f"Product record ID: {product_record.id}")
            _logger.info(f"Product template ID: {product_record.product_tmpl_id.id}")
            
            # Check if we can call the method through the template
            template_method = getattr(product_record.product_tmpl_id, 'action_view_warranty_cards', None)
            _logger.info(f"Template has method: {template_method is not None}")
            
    except Exception as e:
        _logger.error(f"Error checking inheritance: {e}")
    
    _logger.info("=== END DEBUG ===")

if __name__ == "__main__":
    # This would be called from Odoo shell
    pass