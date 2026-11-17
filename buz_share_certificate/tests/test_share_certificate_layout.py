from odoo import Command
from odoo.exceptions import AccessError
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

    def test_layout_configuration_is_admin_only(self):
        user = self.env['res.users'].create({
            'name': 'Certificate Layout User',
            'login': 'certificate-layout-user',
            'groups_id': [Command.set([self.env.ref('base.group_user').id])],
        })

        with self.assertRaises(AccessError):
            self.env['buz.share.certificate.layout.config'].with_user(user).check_access_rights('read')
