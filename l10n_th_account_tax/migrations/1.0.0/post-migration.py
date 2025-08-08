"""
Migration Script for WHT Tax System
Converts from custom wht_tax_id fields to standard Odoo tax system
"""
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

def migrate_wht_data(cr, version):
    """
    Migrate WHT data from old system to new system
    """
    _logger.info("Starting WHT Tax System Migration...")
    
    with api.Environment.manage():
        env = api.Environment(cr, SUPERUSER_ID, {})
        
        # 1. Migrate Account Move Lines with WHT
        _migrate_move_lines_wht(env)
        
        # 2. Migrate Products with WHT Tax
        _migrate_product_wht_tax(env)
        
        # 3. Migrate Partners with default WHT
        _migrate_partner_wht_tax(env)
        
        # 4. Update existing WHT Certificates
        _update_wht_certificates(env)
        
        # 5. Clean up old data (optional)
        # _cleanup_old_wht_data(env)
        
    _logger.info("WHT Tax System Migration completed successfully!")

def _migrate_move_lines_wht(env):
    """Migrate account move lines with WHT tax to standard tax system"""
    _logger.info("Migrating account move lines with WHT...")
    
    # Find move lines with old WHT system
    move_lines = env['account.move.line'].search([
        ('wht_tax_id', '!=', False),
        ('tax_ids', '=', False)
    ])
    
    # Mapping old WHT to new tax IDs
    wht_tax_mapping = {
        # Service WHT 3%
        'service_3': env.ref('l10n_th_account_tax.wht_tax_service_3', raise_if_not_found=False),
        # Professional WHT 5%
        'professional_5': env.ref('l10n_th_account_tax.wht_tax_professional_5', raise_if_not_found=False),
        # Rental WHT 5%
        'rental_5': env.ref('l10n_th_account_tax.wht_tax_rental_5', raise_if_not_found=False),
        # Transport WHT 1%
        'transport_1': env.ref('l10n_th_account_tax.wht_tax_transport_1', raise_if_not_found=False),
    }
    
    for line in move_lines:
        try:
            if hasattr(line, 'wht_tax_id') and line.wht_tax_id:
                # Map old WHT tax to new standard tax
                new_tax = None
                old_wht = line.wht_tax_id
                
                # Map based on old WHT tax rate and type
                if old_wht.percent == 3.0:
                    new_tax = wht_tax_mapping['service_3']
                elif old_wht.percent == 5.0:
                    if 'professional' in old_wht.name.lower():
                        new_tax = wht_tax_mapping['professional_5']
                    else:
                        new_tax = wht_tax_mapping['rental_5']
                elif old_wht.percent == 1.0:
                    new_tax = wht_tax_mapping['transport_1']
                
                if new_tax:
                    # Update line with standard tax
                    line.write({
                        'tax_ids': [(6, 0, [new_tax.id])],
                    })
                    _logger.info(f"Migrated line {line.id}: {old_wht.name} -> {new_tax.name}")
                    
        except Exception as e:
            _logger.error(f"Error migrating line {line.id}: {e}")
            continue
    
    _logger.info(f"Migrated {len(move_lines)} move lines")

def _migrate_product_wht_tax(env):
    """Migrate products with WHT tax configuration"""
    _logger.info("Migrating product WHT tax configuration...")
    
    # Find products with old WHT configuration
    products = env['product.template'].search([
        '|',
        ('property_wht_tax_id', '!=', False),
        ('default_wht_tax_id', '!=', False)
    ])
    
    wht_tax_mapping = {
        3.0: env.ref('l10n_th_account_tax.wht_tax_service_3', raise_if_not_found=False),
        5.0: env.ref('l10n_th_account_tax.wht_tax_professional_5', raise_if_not_found=False),
        1.0: env.ref('l10n_th_account_tax.wht_tax_transport_1', raise_if_not_found=False),
    }
    
    for product in products:
        try:
            # Migrate old WHT tax to new standard tax
            old_wht = None
            if hasattr(product, 'property_wht_tax_id'):
                old_wht = product.property_wht_tax_id
            elif hasattr(product, 'default_wht_tax_id'):
                old_wht = product.default_wht_tax_id
                
            if old_wht and old_wht.percent in wht_tax_mapping:
                new_tax = wht_tax_mapping[old_wht.percent]
                if new_tax:
                    product.write({
                        'wht_tax_purchase_id': new_tax.id,
                        'supplier_taxes_id': [(4, new_tax.id)],
                    })
                    _logger.info(f"Migrated product {product.name}: {old_wht.name} -> {new_tax.name}")
                    
        except Exception as e:
            _logger.error(f"Error migrating product {product.id}: {e}")
            continue
    
    _logger.info(f"Migrated {len(products)} products")

def _migrate_partner_wht_tax(env):
    """Migrate partners with default WHT tax"""
    _logger.info("Migrating partner WHT tax configuration...")
    
    partners = env['res.partner'].search([
        ('property_wht_tax_id', '!=', False)
    ])
    
    wht_tax_mapping = {
        3.0: env.ref('l10n_th_account_tax.wht_tax_service_3', raise_if_not_found=False),
        5.0: env.ref('l10n_th_account_tax.wht_tax_professional_5', raise_if_not_found=False),
        1.0: env.ref('l10n_th_account_tax.wht_tax_transport_1', raise_if_not_found=False),
    }
    
    for partner in partners:
        try:
            if hasattr(partner, 'property_wht_tax_id') and partner.property_wht_tax_id:
                old_wht = partner.property_wht_tax_id
                if old_wht.percent in wht_tax_mapping:
                    new_tax = wht_tax_mapping[old_wht.percent]
                    if new_tax:
                        # Set as default supplier tax for this partner
                        partner.write({
                            'property_supplier_taxes_id': [(4, new_tax.id)],
                        })
                        _logger.info(f"Migrated partner {partner.name}: {old_wht.name} -> {new_tax.name}")
                        
        except Exception as e:
            _logger.error(f"Error migrating partner {partner.id}: {e}")
            continue
    
    _logger.info(f"Migrated {len(partners)} partners")

def _update_wht_certificates(env):
    """Update existing WHT certificates with payment links"""
    _logger.info("Updating WHT certificates...")
    
    # Find existing certificates that might need payment links
    certificates = env['withholding.tax.cert'].search([
        ('payment_id', '=', False),
        ('state', '!=', 'cancel')
    ])
    
    for cert in certificates:
        try:
            # Try to find related payment by date and partner
            payments = env['account.payment'].search([
                ('partner_id', '=', cert.partner_id.id),
                ('date', '=', cert.date),
                ('state', '=', 'posted'),
                ('has_wht_tax', '=', True),
                ('wht_cert_ids', '=', False)
            ], limit=1)
            
            if payments:
                # Link certificate to payment
                payments[0].write({
                    'wht_cert_ids': [(4, cert.id)]
                })
                cert.write({
                    'payment_id': payments[0].id,
                    'auto_generated': False  # Mark as manually linked
                })
                _logger.info(f"Linked certificate {cert.number} to payment {payments[0].name}")
                
        except Exception as e:
            _logger.error(f"Error updating certificate {cert.id}: {e}")
            continue
    
    _logger.info(f"Updated {len(certificates)} certificates")

def _cleanup_old_wht_data(env):
    """
    Optional: Clean up old WHT data fields
    WARNING: This will permanently remove old data
    """
    _logger.warning("Starting cleanup of old WHT data - THIS CANNOT BE UNDONE!")
    
    # Remove old WHT tax records (if not referenced)
    old_wht_taxes = env['account.withholding.tax'].search([])
    
    for wht_tax in old_wht_taxes:
        # Check if still referenced
        references = env['account.move.line'].search_count([
            ('wht_tax_id', '=', wht_tax.id)
        ])
        
        if references == 0:
            wht_tax.unlink()
            _logger.info(f"Removed unused WHT tax: {wht_tax.name}")
    
    _logger.info("Old WHT data cleanup completed")

# Helper function to run migration manually
def run_manual_migration(env):
    """Run migration manually from Python code"""
    _logger.info("Running manual WHT migration...")
    migrate_wht_data(env.cr, '1.0')
    env.cr.commit()
    _logger.info("Manual migration completed!")
