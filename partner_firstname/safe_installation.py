# Copyright 2024
# Safe installation script for partner_firstname module

def safe_install_partner_firstname(env):
    """
    Safe installation function that handles the name splitting during module installation
    """
    # Get all partners with empty firstname and lastname
    partners = env['res.partner'].search([
        ('firstname', '=', False),
        ('lastname', '=', False),
    ])
    
    # Separate partners with valid names from those with invalid/empty names
    partners_with_names = partners.filtered(lambda p: p.name and p.name.strip())
    partners_without_names = partners - partners_with_names
    
    # Update partners that have valid names
    for partner in partners_with_names:
        # Parse the name into parts
        parts = partner._get_inverse_name(partner.name, partner.is_company)
        
        # Use a direct SQL update to avoid triggering constraints during installation
        env.cr.execute(
            "UPDATE res_partner SET firstname=%s, lastname=%s WHERE id=%s",
            (parts.get('firstname'), parts.get('lastname'), partner.id)
        )
    
    # Log information about the installation
    env['ir.logging'].create({
        'name': 'partner_firstname installation',
        'type': 'server',
        'levelname': 'INFO',
        'message': f'Successfully processed {len(partners_with_names)} partners during installation. Skipped {len(partners_without_names)} partners with empty names.',
    })
    
    return len(partners_with_names)