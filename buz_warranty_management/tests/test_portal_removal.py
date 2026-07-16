from odoo.tests.common import TransactionCase


class TestWarrantyPortalRemoval(TransactionCase):
    def test_warranty_card_keeps_external_registration_fields_for_api(self):
        api_fields = {
            'source',
            'serial_number_input',
            'product_model_input',
            'registration_date',
            'external_request_id',
        }
        self.assertTrue(
            api_fields.issubset(self.env['warranty.card']._fields),
            'External registration fields must remain available to the web API',
        )
