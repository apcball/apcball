def migrate(cr, version):
    if not version:
        return

    cr.execute(
        """
        SELECT res_id
          FROM ir_model_data
         WHERE module = 'buz_it_helpdesk'
           AND name = 'stage_resolved'
           AND model = 'buz.helpdesk.stage'
        """
    )
    resolved = cr.fetchone()
    if not resolved:
        return
    resolved_id = resolved[0]

    cr.execute(
        """
        UPDATE buz_helpdesk_ticket AS ticket
           SET stage_id = %s
          FROM buz_helpdesk_stage AS old_stage
         WHERE ticket.stage_id = old_stage.id
           AND lower(old_stage.name) IN ('done', 'resolved')
           AND ticket.stage_id <> %s
        """,
        (resolved_id, resolved_id),
    )
    cr.execute(
        """
        UPDATE buz_helpdesk_stage
           SET active = FALSE
         WHERE lower(name) = 'done'
           AND id <> %s
        """,
        (resolved_id,),
    )
