"""Replace the Software Product uniqueness constraint with the version-aware one."""


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        'ALTER TABLE buz_it_software_product '
        'DROP CONSTRAINT IF EXISTS name_edition_company_uniq',
    )
