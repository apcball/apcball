def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE ir_cron
           SET numbercall = -1,
               active = TRUE
         WHERE cron_name = 'Helpdesk LINE Notification Queue'
        """
    )
