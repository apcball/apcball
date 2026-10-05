from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Undo 17.0.2.5.0 filling masked Shopee buyers with company data."""
    cr.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'shopee_config' AND column_name = 'buyer_fallback_email'
    """)
    extra_emails = ()
    if cr.fetchone():
        cr.execute(
            "SELECT DISTINCT buyer_fallback_email FROM shopee_config"
            " WHERE buyer_fallback_email IS NOT NULL"
        )
        extra_emails = tuple(row[0] for row in cr.fetchall())
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["res.partner"]._shopee_clear_company_copies(extra_emails)
