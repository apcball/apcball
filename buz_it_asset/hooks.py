from odoo import _
from odoo.exceptions import UserError


LEGACY_ASSET_COLUMNS = {
    'account_email',
    'asset_name',
    'asset_type',
    'brand',
    'license_key',
    'model_name',
    'password',
    'repair_symptoms',
    'status',
}

LEGACY_ASSET_TABLES = {
    'buz_it_asset_attachment_rel',
    'buz_it_asset_license_allocation',
    'buz_it_asset_log',
    'buz_it_asset_log_ir_attachment_rel',
    'buz_it_asset_notification_config',
    'buz_it_asset_notification_config_res_users_rel',
    'buz_it_asset_notification_log',
    'buz_it_asset_renewal',
    'buz_it_asset_renewal_ir_attachment_rel',
    'buz_it_asset_repair_attachment_rel',
    'buz_it_asset_software',
    'buz_it_asset_software_rel',
    'buz_it_asset_spec_category',
    'buz_it_asset_spec_line',
    'buz_it_asset_spec_rel',
}


def pre_init_hook(env):
    """Refuse a fresh install over the incompatible legacy asset schema."""
    env.cr.execute("""
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = 'buz_it_asset'
           AND column_name = ANY(%s)
    """, [list(LEGACY_ASSET_COLUMNS)])
    legacy_columns = sorted(row[0] for row in env.cr.fetchall())
    env.cr.execute("""
        SELECT table_name
          FROM information_schema.tables
         WHERE table_schema = current_schema()
           AND table_name = ANY(%s)
    """, [list(LEGACY_ASSET_TABLES)])
    legacy_tables = sorted(row[0] for row in env.cr.fetchall())
    if legacy_columns or legacy_tables:
        details = []
        if legacy_columns:
            details.append(_('columns: %s') % ', '.join(legacy_columns))
        if legacy_tables:
            details.append(_('tables: %s') % ', '.join(legacy_tables))
        raise UserError(_(
            'Legacy IT Asset schema detected (%s). Restore or clean the legacy '
            'schema before installing this module.'
        ) % '; '.join(details))


def post_init_hook(env):
    """Create an independent IT Asset sequence for every company/type."""
    types = env['buz.it.asset.type'].sudo().search([])
    for company in env['res.company'].sudo().search([]):
        for asset_type in types:
            company._ensure_it_asset_sequence(asset_type)
