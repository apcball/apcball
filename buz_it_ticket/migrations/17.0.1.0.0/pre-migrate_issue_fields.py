# -*- coding: utf-8 -*-
"""
Migration script to add default values for new Issue ticket fields
This ensures existing Issue tickets don't break when new required fields are added
"""

def migrate(cr, version):
    """Set default values for existing Issue tickets"""
    if not version:
        return
    
    # Set default values for existing Issue tickets
    cr.execute("""
        UPDATE it_ticket 
        SET 
            requester_email = COALESCE(
                employee_work_email.work_email,
                res_users.email,
                'To be updated'
            ),
            line_id = 'To be updated',
            symptoms = COALESCE(description, 'To be updated'),
            computer_name = 'To be updated'
        FROM it_ticket AS ticket
        LEFT JOIN hr_employee employee ON ticket.employee_id = employee.id
        LEFT JOIN res_users res_users ON employee.user_id = res_users.id
        LEFT JOIN hr_employee employee_work_email ON ticket.employee_id = employee_work_email.id
        WHERE ticket.category = 'issue' 
        AND (ticket.requester_email IS NULL OR ticket.requester_email = '')
    """)
    
    # Log the migration
    cr.execute("""
        INSERT INTO ir_logging (create_date, create_uid, name, level, message, path, line, func, type)
        VALUES (
            NOW()::timestamp,
            1,
            'buz_it_ticket.migration',
            'info',
            'Migrated existing Issue tickets with default values for new required fields',
            'pre-migrate_issue_fields.py',
            1,
            'migrate',
            'server'
        )
    """)