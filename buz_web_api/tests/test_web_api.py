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
