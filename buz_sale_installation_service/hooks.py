# -*- coding: utf-8 -*-

def post_init_hook(env):
    """Post-installation hook to configure default installation service product"""
    # Get or create the default installation service product
    installation_product = env.ref('buz_sale_installation_service.product_installation_service', raise_if_not_found=False)
    
    if installation_product:
        # Set this product as default for all companies that don't have one configured
        companies = env['res.company'].search([
            ('default_installation_service_product_id', '=', False)
        ])
        for company in companies:
            company.default_installation_service_product_id = installation_product.id
