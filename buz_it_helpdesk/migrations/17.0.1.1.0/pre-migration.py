from odoo.exceptions import UserError


def migrate(cr, version):
    if not version:
        return

    cr.execute(
        'ALTER TABLE buz_helpdesk_ticket '
        'ADD COLUMN IF NOT EXISTS company_id integer'
    )
    cr.execute(
        """
        UPDATE buz_helpdesk_ticket ticket
           SET company_id = department.company_id
          FROM hr_department department
         WHERE ticket.department_id = department.id
           AND ticket.company_id IS NULL
           AND department.company_id IS NOT NULL
        """
    )
    cr.execute(
        """
        UPDATE buz_helpdesk_ticket ticket
           SET company_id = requester.company_id
          FROM res_users requester
         WHERE ticket.requester_id = requester.id
           AND ticket.company_id IS NULL
           AND requester.company_id IS NOT NULL
        """
    )
    cr.execute('SELECT id FROM res_company ORDER BY id LIMIT 1')
    fallback = cr.fetchone()
    if not fallback:
        raise UserError('Cannot migrate Helpdesk Tickets: no company exists.')
    cr.execute(
        'UPDATE buz_helpdesk_ticket SET company_id = %s '
        'WHERE company_id IS NULL',
        (fallback[0],),
    )
    cr.execute(
        'ALTER TABLE buz_helpdesk_ticket ALTER COLUMN company_id SET NOT NULL'
    )