from odoo.exceptions import UserError


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        SELECT DISTINCT repair_outcome_legacy
          FROM buz_helpdesk_ticket
         WHERE repair_outcome_legacy IS NOT NULL
           AND repair_outcome_legacy NOT IN (
               'repaired', 'parts_replaced', 'asset_replaced', 'retired', 'no_repair'
           )
        """
    )
    unknown = [row[0] for row in cr.fetchall()]
    if unknown:
        raise UserError(
            'Cannot migrate unknown repair outcomes: %s.' % ', '.join(sorted(unknown))
        )

    cr.execute(
        """
        UPDATE buz_helpdesk_ticket ticket
           SET repair_outcome_id = outcome.id
          FROM buz_it_asset_repair_outcome outcome
         WHERE outcome.code = ticket.repair_outcome_legacy
           AND ticket.repair_outcome_id IS NULL
        """
    )
    cr.execute(
        'SELECT COUNT(*) FROM buz_helpdesk_ticket '
        'WHERE repair_outcome_legacy IS NOT NULL AND repair_outcome_id IS NULL'
    )
    missing = cr.fetchone()[0]
    if missing:
        raise UserError(
            'Could not map %s existing repair outcome(s).' % missing
        )
