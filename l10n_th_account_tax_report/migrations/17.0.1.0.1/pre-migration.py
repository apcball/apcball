# Copyright 2025 Ecosoft Co., Ltd (https://ecosoft.co.th)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

def migrate(cr, version):
    """
    Migration script for l10n_th_account_tax_report module to Odoo 17
    """
    if not version:
        # This is a new installation, no migration needed
        return

    # Perform any database migrations necessary for Odoo 17 compatibility
    # Currently empty, but can be extended as needed
    pass