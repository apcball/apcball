def migrate(cr, version):
    """
    Clean up mail tracking records for removed approval_state field
    """
    # Remove mail tracking records for approval_state field
    cr.execute("""
        DELETE FROM mail_tracking_value 
        WHERE field IN (
            SELECT name FROM ir_model_fields 
            WHERE model = 'purchase.order' AND name = 'approval_state'
        )
    """)
    
    # Remove the field definition from ir_model_fields
    cr.execute("""
        DELETE FROM ir_model_fields 
        WHERE model = 'purchase.order' AND name = 'approval_state'
    """)
    
    # Clean up any mail messages that reference the removed field
    cr.execute("""
        UPDATE mail_message 
        SET tracking_value_ids = NULL 
        WHERE model = 'purchase.order' 
        AND tracking_value_ids IS NOT NULL
        AND id IN (
            SELECT DISTINCT message_id 
            FROM mail_tracking_value 
            WHERE field = 'approval_state'
        )
    """)
