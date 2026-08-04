
def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE ir_ui_view view
           SET active = FALSE
          FROM ir_model_data data
         WHERE data.module = 'buz_it_asset'
           AND data.name = 'view_it_asset_maintenance_readonly_extension'
           AND data.model = 'ir.ui.view'
           AND data.res_id = view.id
        """
    )
    cr.execute(
        """
        ALTER TABLE buz_helpdesk_ticket
        RENAME COLUMN repair_outcome TO repair_outcome_legacy
        """
    )
