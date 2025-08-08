"""
Post-installation hook for l10n_th_account_tax module
"""
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

def post_init_hook(cr, registry):
    """
    Post-installation hook to set up WHT tax system
    """
    _logger.info("Running post-installation hook for l10n_th_account_tax...")
    
    with api.Environment.manage():
        env = api.Environment(cr, SUPERUSER_ID, {})
        
        try:
            # 1. Ensure WHT tax tags exist
            _ensure_wht_tax_tags(env)
            
            # 2. Ensure WHT accounts exist
            _ensure_wht_accounts(env)
            
            # 3. Set up default WHT tax for product categories
            _setup_default_product_wht(env)
            
            # 4. Configure payment methods for WHT
            _configure_payment_methods(env)
            
            _logger.info("Post-installation hook completed successfully!")
            
        except Exception as e:
            _logger.error(f"Error in post-installation hook: {e}")
            raise

def _ensure_wht_tax_tags(env):
    """Ensure WHT tax tags are created"""
    _logger.info("Ensuring WHT tax tags exist...")
    
    wht_tags = [
        ('wht_tag_service', 'WHT Service 3%', '#FF6B6B', 'TH'),
        ('wht_tag_professional', 'WHT Professional 5%', '#4ECDC4', 'TH'),
        ('wht_tag_rental', 'WHT Rental 5%', '#45B7D1', 'TH'),
        ('wht_tag_transport', 'WHT Transport 1%', '#96CEB4', 'TH'),
    ]
    
    for xml_id, name, color, country_code in wht_tags:
        existing = env.ref(f'l10n_th_account_tax.{xml_id}', raise_if_not_found=False)
        if not existing:
            # Create tag if not exists
            country = env['res.country'].search([('code', '=', country_code)], limit=1)
            tag = env['account.account.tag'].create({
                'name': name,
                'color': color,
                'applicability': 'taxes',
                'country_id': country.id if country else False,
            })
            # Create external ID
            env['ir.model.data'].create({
                'name': xml_id,
                'module': 'l10n_th_account_tax',
                'model': 'account.account.tag',
                'res_id': tag.id,
            })
            _logger.info(f"Created WHT tax tag: {name}")

def _ensure_wht_accounts(env):
    """Ensure WHT accounts exist in chart of accounts"""
    _logger.info("Ensuring WHT accounts exist...")
    
    # Check if chart of accounts is installed
    company = env.company
    if not company:
        _logger.warning("No company found, skipping account creation")
        return
    
    # WHT accounts mapping
    wht_accounts = [
        ('wht_payable_account', '21101', 'WHT Payable', 'liability_current'),
        ('wht_expense_account', '61101', 'WHT Expense', 'expense'),
    ]
    
    for xml_id, code, name, account_type in wht_accounts:
        existing = env.ref(f'l10n_th_account_tax.{xml_id}', raise_if_not_found=False)
        if not existing:
            # Check if account with code exists
            account = env['account.account'].search([
                ('code', '=', code),
                ('company_id', '=', company.id)
            ], limit=1)
            
            if not account:
                # Create account
                account = env['account.account'].create({
                    'name': name,
                    'code': code,
                    'account_type': account_type,
                    'company_id': company.id,
                    'reconcile': account_type == 'liability_current',
                })
                _logger.info(f"Created WHT account: {code} - {name}")
            
            # Create external ID
            env['ir.model.data'].create({
                'name': xml_id,
                'module': 'l10n_th_account_tax',
                'model': 'account.account',
                'res_id': account.id,
            })

def _setup_default_product_wht(env):
    """Set up default WHT taxes for common product categories"""
    _logger.info("Setting up default WHT for product categories...")
    
    # Common service categories that should have WHT
    service_categories = env['product.category'].search([
        ('name', 'ilike', 'service'),
    ])
    
    # Get service WHT tax
    service_wht = env.ref('l10n_th_account_tax.wht_tax_service_3', raise_if_not_found=False)
    
    if service_wht and service_categories:
        for category in service_categories:
            try:
                if hasattr(category, 'default_wht_tax_purchase_id'):
                    category.write({
                        'default_wht_tax_purchase_id': service_wht.id,
                    })
                    _logger.info(f"Set default WHT for category: {category.name}")
            except Exception as e:
                _logger.warning(f"Could not set WHT for category {category.name}: {e}")

def _configure_payment_methods(env):
    """Configure payment methods for WHT processing"""
    _logger.info("Configuring payment methods for WHT...")
    
    # Ensure payment methods support WHT
    payment_methods = env['account.payment.method'].search([])
    
    for method in payment_methods:
        # Add any WHT-specific configuration here
        # For now, all payment methods support WHT
        pass
    
    _logger.info("Payment method configuration completed")
