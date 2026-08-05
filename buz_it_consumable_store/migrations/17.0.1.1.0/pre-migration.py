def migrate(cr, version):
    cr.execute("""
        DELETE FROM ir_act_window
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'buz_it_consumable_store'
              AND name = 'action_consumable_store'
              AND model = 'ir.actions.act_window'
        )
    """)
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'buz_it_consumable_store'
          AND name = 'action_consumable_store'
          AND model = 'ir.actions.act_window'
    """)
