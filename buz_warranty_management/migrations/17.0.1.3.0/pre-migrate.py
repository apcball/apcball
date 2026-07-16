"""Remove the obsolete warranty.claim models before the module is upgraded."""


def migrate(cr, version):
    if not version:
        return

    model_names = (
        'warranty.claim',
        'warranty.claim.line',
        'warranty.out.wizard',
        'warranty.rma.receive.wizard',
        'warranty.rma.receive.line',
        'warranty.replacement.issue.wizard',
        'warranty.replacement.issue.line',
        'warranty.invoice.wizard',
        'warranty.invoice.line',
    )
    model_sql = ','.join("'%s'" % name for name in model_names)

    cr.execute("""
        DELETE FROM ir_model_access
        WHERE model_id IN (
            SELECT id FROM ir_model
            WHERE model IN (%s)
        )
    """ % model_sql)
    cr.execute("""
        DELETE FROM ir_rule
        WHERE model_id IN (
            SELECT id FROM ir_model
            WHERE model IN (%s)
        )
    """ % model_sql)
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE model_id IN (
            SELECT id FROM ir_model
            WHERE model IN (%s)
        )
    """ % model_sql)
    cr.execute("""
        DELETE FROM ir_ui_view
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'buz_warranty_management'
              AND (name LIKE '%warranty_claim%'
                   OR name LIKE '%warranty_out_wizard%'
                   OR name LIKE '%warranty_rma_receive%'
                   OR name LIKE '%warranty_replacement_issue%'
                   OR name LIKE '%warranty_invoice%')
              AND model = 'ir.ui.view'
        )
    """)
    cr.execute("""
        DELETE FROM ir_act_window
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'buz_warranty_management'
              AND (name LIKE '%warranty_claim%'
                   OR name LIKE '%warranty_out_wizard%'
                   OR name LIKE '%warranty_rma_receive%'
                   OR name LIKE '%warranty_replacement_issue%'
                   OR name LIKE '%warranty_invoice%')
              AND model = 'ir.actions.act_window'
        )
    """)
    cr.execute("""
        DELETE FROM ir_act_report_xml
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'buz_warranty_management'
              AND name LIKE '%warranty_claim%'
              AND model = 'ir.actions.report'
        )
    """)
    cr.execute("""
        DELETE FROM ir_sequence
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'buz_warranty_management'
              AND name = 'sequence_warranty_claim'
              AND model = 'ir.sequence'
        )
    """)
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'buz_warranty_management'
          AND (name LIKE '%warranty_claim%'
               OR name LIKE '%warranty_out_wizard%'
               OR name LIKE '%warranty_rma_receive%'
               OR name LIKE '%warranty_replacement_issue%'
               OR name LIKE '%warranty_invoice%')
    """)
    cr.execute("DROP TABLE IF EXISTS warranty_claim_rma_in_rel CASCADE")
    cr.execute("DROP TABLE IF EXISTS warranty_claim_replacement_out_rel CASCADE")
    cr.execute("DROP TABLE IF EXISTS warranty_claim_invoice_rel CASCADE")
    cr.execute("DROP TABLE IF EXISTS warranty_claim_line CASCADE")
    cr.execute("DROP TABLE IF EXISTS warranty_claim CASCADE")
    cr.execute("""
        DELETE FROM ir_model
        WHERE model IN (%s)
    """ % model_sql)
