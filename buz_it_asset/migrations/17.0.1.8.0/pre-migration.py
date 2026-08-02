"""Preserve the old selection values before changing the field type."""


def migrate(cr, version):
    if not version:
        return

    # Remove stale ir.model.fields.selection metadata before the Selection
    # field is replaced by a Many2one. Odoo 17 otherwise tries to process the
    # old selection records with the new field's ondelete value.
    cr.execute(
        """
        DELETE FROM ir_model_data
        WHERE model = 'ir.model.fields.selection'
          AND res_id IN (
              SELECT selection.id
              FROM ir_model_fields_selection selection
              JOIN ir_model_fields field ON field.id = selection.field_id
              JOIN ir_model model ON model.id = field.model_id
              WHERE model.model = 'buz.it.software.product'
                AND field.name = 'software_type'
          )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_fields_selection
        WHERE field_id IN (
            SELECT field.id
            FROM ir_model_fields field
            JOIN ir_model model ON model.id = field.model_id
            WHERE model.model = 'buz.it.software.product'
              AND field.name = 'software_type'
        )
        """
    )
    cr.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'buz_it_software_product'
                  AND column_name = 'software_type'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'buz_it_software_product'
                  AND column_name = 'software_type_legacy'
            ) THEN
                ALTER TABLE buz_it_software_product
                RENAME COLUMN software_type TO software_type_legacy;
            END IF;
        END $$;
        """
    )
