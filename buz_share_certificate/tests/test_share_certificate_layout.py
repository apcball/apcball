from io import BytesIO

from PyPDF2 import PdfFileReader

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestShareCertificateLayout(TransactionCase):
    def test_default_positions_are_used(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        action = self.env.ref('buz_share_certificate.action_share_certificate_layout_config')

        self.assertEqual(len(config.position_ids), 28)
        self.assertTrue(all(
            position.x_mm == position.x_default_mm and position.y_mm == position.y_default_mm
            for position in config.position_ids
        ))
        self.assertEqual(len(config.position_ids.filtered(lambda position: position.font_size_pt == 10)), 27)
        self.assertEqual(config.get_position_style('stub_company'), 'left:22.0mm;top:24.0mm;font-size:10.0pt;')
        self.assertEqual(config.get_position_style('certificate_company'), 'left:139.5mm;top:33.0mm;font-size:14.0pt;')
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

        self.assertIn('left:42.5mm;top:24.0mm;font-size:10.0pt;', html)
        self.assertIn('Coordinate Test Company', html)

    def test_paper_margins_apply_to_preview_and_print(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        report = self.env.ref('buz_share_certificate.action_report_share_certificate')
        self.assertEqual(
            (config.margin_top, config.margin_bottom, config.margin_left, config.margin_right),
            (0, 0, 0, 0),
        )
        self.assertFalse(config.fields_get(['margin_top'])['margin_top']['readonly'])

        config.write({'margin_top': 5, 'margin_bottom': 5, 'margin_left': 8, 'margin_right': 7})
        self.assertEqual(
            report.paperformat_id,
            self.env.ref('buz_share_certificate.paperformat_share_certificate'),
        )
        self.assertEqual(
            (report.paperformat_id.margin_top, report.paperformat_id.margin_bottom,
             report.paperformat_id.margin_left, report.paperformat_id.margin_right),
            (5, 5, 8, 7),
        )

        certificate = self.env['buz.share.certificate.print.wizard'].create({
            'company_name': 'Margin Test',
        })
        html, _content_type = report._render_qweb_html(report.report_name, certificate.ids)
        html = html.decode() if isinstance(html, bytes) else html
        self.assertIn('width:282.0mm;height:200.0mm;', html)

        pdf, _content_type = report.with_context(force_report_rendering=True)._render_qweb_pdf(
            report.report_name, certificate.ids
        )
        self.assertEqual(PdfFileReader(BytesIO(pdf)).getNumPages(), 1)

    def test_invalid_paper_margins_are_rejected(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        for margins in (
            {'margin_left': -0.01},
            {'margin_left': 150, 'margin_right': 147},
            {'margin_top': 110, 'margin_bottom': 100},
        ):
            with self.assertRaises(ValidationError):
                config.write(margins)

    def test_font_size_changes_only_selected_field(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        position = config.position_ids.filtered(lambda item: item.code == 'stub_company')
        position.font_size_pt = 12

        self.assertEqual(config.get_position_style('stub_company'), 'left:22.0mm;top:24.0mm;font-size:12.0pt;')
        self.assertEqual(config.get_position_style('certificate_company'), 'left:139.5mm;top:33.0mm;font-size:14.0pt;')
        with self.assertRaises(ValidationError):
            position.font_size_pt = 0

    def test_reset_restores_only_selected_position(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        position = config.position_ids.filtered(lambda item: item.code == 'stub_company')
        other_position = config.position_ids.filtered(lambda item: item.code == 'stub_registration')
        position.write({'x_mm': 42.5, 'y_mm': 52.5, 'font_size_pt': 12})
        other_position.write({'x_mm': 99.0, 'y_mm': 98.0})

        position.action_reset_position()

        self.assertEqual((position.x_mm, position.y_mm), (22.0, 24.0))
        self.assertEqual(position.font_size_pt, 12)
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

    def test_layout_configuration_is_admin_only(self):
        user = self.env['res.users'].create({
            'name': 'Certificate Layout User',
            'login': 'certificate-layout-user',
            'groups_id': [Command.set([self.env.ref('base.group_user').id])],
        })

        with self.assertRaises(AccessError):
            self.env['buz.share.certificate.layout.config'].with_user(user).check_access_rights('read')

    def test_only_admin_can_delete_saved_certificate(self):
        users = self.env['res.users']
        internal_group = self.env.ref('base.group_user').id
        admin_group = self.env.ref('base.group_system').id
        regular = users.create({
            'name': 'Certificate Regular User',
            'login': 'certificate-regular-user',
            'groups_id': [Command.set([internal_group])],
        })
        admin = users.create({
            'name': 'Certificate Admin User',
            'login': 'certificate-admin-user',
            'groups_id': [Command.set([internal_group, admin_group])],
        })
        certificates = self.env['buz.share.certificate.print.wizard']
        selected = certificates.create({'certificate_number': 'DELETE-001'})
        other = certificates.create({'certificate_number': 'KEEP-002'})

        with self.assertRaises(AccessError):
            selected.with_user(regular).unlink()
        self.assertTrue(selected.exists())

        selected.with_user(admin).unlink()
        self.assertFalse(selected.exists())
        self.assertTrue(other.exists())
