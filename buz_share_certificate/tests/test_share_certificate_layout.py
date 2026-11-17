from pathlib import Path
from runpy import run_path

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestShareCertificateLayout(TransactionCase):
    def test_default_positions_are_used(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        action = self.env.ref('buz_share_certificate.action_share_certificate_layout_config')

        self.assertEqual(len(config.position_ids), 28)
        self.assertEqual(config.get_position_style('stub_company'), 'left:22.0mm;top:24.0mm;')
        self.assertEqual(action.res_model, config._name)
        self.assertEqual(action.res_id, config.id)

    def test_report_uses_saved_positions(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        config.position_ids.filtered(lambda item: item.code == 'stub_company').write({'x_mm': 42.5})
        certificate = self.env['buz.share.certificate.print.wizard'].create({
            'company_name': 'Coordinate Test Company',
        })
        report = self.env.ref('buz_share_certificate.action_report_share_certificate')

        html, _content_type = report._render_qweb_html(report.report_name, certificate.ids)
        html = html.decode() if isinstance(html, bytes) else html

        self.assertIn('left:42.5mm;top:24.0mm;', html)
        self.assertIn('Coordinate Test Company', html)

    def test_reset_restores_only_selected_position(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        position = config.position_ids.filtered(lambda item: item.code == 'stub_company')
        other_position = config.position_ids.filtered(lambda item: item.code == 'stub_registration')
        position.write({'x_mm': 42.5, 'y_mm': 52.5})
        other_position.write({'x_mm': 99.0, 'y_mm': 98.0})

        position.action_reset_position()

        self.assertEqual((position.x_mm, position.y_mm), (22.0, 24.0))
        self.assertEqual((other_position.x_mm, other_position.y_mm), (99.0, 98.0))

    def test_preview_uses_current_certificate(self):
        certificate = self.env['buz.share.certificate.print.wizard'].create({
            'company_name': 'Preview Company',
        })
        action = certificate.action_open_layout_config()
        self.assertEqual(action['context']['preview_certificate_id'], certificate.id)

        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        preview = config.with_context(action['context']).action_preview_layout()
        self.assertEqual(preview['report_name'], 'buz_share_certificate.report_share_certificate')
        with self.assertRaises(UserError):
            config.action_preview_layout()

    def test_migration_populates_reset_defaults_without_moving_values(self):
        position = self.env.ref('buz_share_certificate.position_stub_company')
        position.write({'x_mm': 42.5, 'x_default_mm': 0, 'y_default_mm': 0})
        migration = Path(__file__).resolve().parents[1] / 'migrations' / '17.0.1.1.0' / 'post-migration.py'

        run_path(str(migration))['migrate'](self.env.cr, '17.0.1.0.0')

        self.assertEqual((position.x_mm, position.y_mm), (42.5, 24.0))
        self.assertEqual((position.x_default_mm, position.y_default_mm), (22.0, 24.0))

    def test_layout_configuration_is_admin_only(self):
        user = self.env['res.users'].create({
            'name': 'Certificate Layout User',
            'login': 'certificate-layout-user',
            'groups_id': [Command.set([self.env.ref('base.group_user').id])],
        })

        with self.assertRaises(AccessError):
            self.env['buz.share.certificate.layout.config'].with_user(user).check_access_rights('read')
