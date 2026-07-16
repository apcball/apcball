from psycopg2.errors import UniqueViolation
from odoo.tests.common import TransactionCase


class TestWebApiIntegration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.integration_user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Website Warranty Integration',
            'login': 'website-warranty-integration@example.com',
            'email': 'website-warranty-integration@example.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.integration = cls.env['web.api.integration'].create({
            'name': 'Warranty Website',
            'user_id': cls.integration_user.id,
        })

    def test_web_api_menu_is_under_administration(self):
        menu = self.env.ref('buz_web_api.menu_web_api_integration')

        self.assertEqual(menu.parent_id, self.env.ref('base.menu_administration'))
        self.assertEqual(menu.action.res_model, 'web.api.integration')

    def test_crm_lead_has_unique_external_request_id(self):
        self.assertIn('external_request_id', self.env['crm.lead']._fields)

        lead = self.env['crm.lead'].create({
            'name': 'External CRM Lead',
            'external_request_id': 'crm-request-001',
        })
        self.assertEqual(lead.external_request_id, 'crm-request-001')

        with self.assertRaises(UniqueViolation):
            self.env['crm.lead'].create({
                'name': 'Duplicate External CRM Lead',
                'external_request_id': 'crm-request-001',
            })

    def test_warranty_card_accepts_external_request_id_domain(self):
        """The web API can deduplicate warranty cards by its external request ID."""
        self.assertTrue({
            'external_request_id',
            'source',
            'serial_number_input',
            'product_model_input',
            'registration_date',
        }.issubset(self.env['warranty.card']._fields))

        card = self.env['warranty.card'].create({
            'name': 'API Warranty Card',
            'partner_id': self.env.user.partner_id.id,
            'start_date': '2026-01-01',
            'external_request_id': '30a39e33-7fcf-43e2-b3d6-f4f7585848bf',
            'source': 'portal',
            'serial_number_input': 'SN-API-001',
            'product_model_input': 'MODEL-API-001',
        })

        found = self.env['warranty.card'].search([
            ('external_request_id', '=', '30a39e33-7fcf-43e2-b3d6-f4f7585848bf'),
        ])
        self.assertEqual(found, card)

    def test_generate_key_uses_native_odoo_key_store(self):
        action = self.integration.action_generate_api_key()
        key = action['context']['default_key']

        self.assertEqual(action['res_model'], 'web.api.key.show')
        self.assertTrue(key)
        self.assertNotIn('key', self.integration._fields)
        self.assertEqual(
            self.env['res.users.apikeys'].sudo()._check_credentials(scope='rpc', key=key),
            self.integration_user.id,
        )

        # Verify the generated key has the correct scope.
        apikey = self.env['res.users.apikeys'].sudo().search([
            ('user_id', '=', self.integration_user.id),
            ('name', '=', self.integration.key_name),
            ('scope', '=', 'rpc'),
        ])
        self.assertTrue(apikey)

    def test_revoke_key_invalidates_native_key(self):
        action = self.integration.action_generate_api_key()
        key = action['context']['default_key']

        self.integration.action_revoke_api_key()

        self.assertFalse(
            self.env['res.users.apikeys'].sudo()._check_credentials(scope='rpc', key=key)
        )
