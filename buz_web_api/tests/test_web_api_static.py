import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).parents[1]


class TestWebApiModuleShape(unittest.TestCase):
    def test_manifest_declares_odoo17_dependencies(self):
        source = (MODULE_ROOT / '__manifest__.py').read_text()
        self.assertIn("'buz_warranty_management'", source)
        self.assertIn("'base'", source)

    def test_integration_generates_native_key_without_secret_field(self):
        source = (MODULE_ROOT / 'models' / 'web_api_integration.py').read_text()
        self.assertIn("'res.users.apikeys'", source)
        self.assertIn("_generate(None", source)
        self.assertIn('action_generate_api_key', source)
        self.assertNotIn("key = fields.Char", source)

    def test_health_endpoint_validates_rpc_scope(self):
        source = (MODULE_ROOT / 'controllers' / 'web_api.py').read_text()
        self.assertIn("'/web_api/v1/health'", source)
        self.assertIn("scope='rpc'", source)
        self.assertIn("'X-Odoo-API-Key'", source)

    def test_one_time_key_wizard_has_a_form_view(self):
        source = (MODULE_ROOT / 'views' / 'web_api_integration_views.xml').read_text()
        self.assertIn('model">web.api.key.show<', source)
        self.assertIn('name="key"', source)


if __name__ == '__main__':
    unittest.main()
