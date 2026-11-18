from io import BytesIO

from PyPDF2 import PdfFileReader
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTFigure, LTImage
from reportlab.lib.units import mm
from lxml import html as lxml_html

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('-at_install', 'post_install')
class TestShareCertificateLayout(TransactionCase):
    def test_default_positions_are_used(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        action = self.env.ref('buz_share_certificate.action_share_certificate_layout_config')

        self.assertEqual(len(config.position_ids), 34)
        self.assertTrue(all(
            position.x_mm == position.x_default_mm and position.y_mm == position.y_default_mm
            for position in config.position_ids
        ))
        self.assertEqual(len(config.position_ids.filtered(lambda position: position.font_size_pt == 10)), 33)
        self.assertEqual(config.get_position_style('stub_company'), 'left:22.0mm;top:24.0mm;font-size:10.0pt;')
        self.assertEqual(config.get_position_style('certificate_company'), 'left:139.5mm;top:33.0mm;font-size:14.0pt;')
        self.assertEqual(action.res_model, config._name)
        self.assertEqual(action.res_id, config.id)

    def test_tabs_edit_independent_positions(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        stub_positions = config.stub_position_ids
        certificate_positions = config.certificate_position_ids
        self.assertEqual((len(stub_positions), len(certificate_positions)), (19, 15))
        self.assertTrue(all(position.section == 'stub' for position in stub_positions))
        self.assertTrue(all(position.section == 'certificate' for position in certificate_positions))

        stub = stub_positions.filtered(lambda position: position.code == 'stub_company')
        certificate = certificate_positions.filtered(lambda position: position.code == 'certificate_company')
        self.assertEqual((len(stub), len(certificate)), (1, 1))
        certificate_before = (certificate.x_mm, certificate.y_mm, certificate.font_size_pt)
        config.write({'stub_position_ids': [Command.update(stub.id, {
            'x_mm': 23, 'y_mm': 25, 'font_size_pt': 11,
        })]})
        self.assertEqual((stub.x_mm, stub.y_mm, stub.font_size_pt), (23, 25, 11))
        self.assertEqual(
            (certificate.x_mm, certificate.y_mm, certificate.font_size_pt), certificate_before
        )

        config.write({'certificate_position_ids': [Command.update(certificate.id, {
            'x_mm': 141, 'y_mm': 34, 'font_size_pt': 15,
        })]})
        self.assertEqual((certificate.x_mm, certificate.y_mm, certificate.font_size_pt), (141, 34, 15))
        self.assertEqual((stub.x_mm, stub.y_mm, stub.font_size_pt), (23, 25, 11))
        self.assertEqual(len(config.position_ids), 34)

    def test_document_labels_update_without_changing_layout(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        positions = {position.code: position for position in config.position_ids}
        self.assertEqual(len(positions), 34)
        self.assertEqual(positions['stub_certificate_number'].label, 'ใบหุ้นเลขที่')
        self.assertEqual(positions['stub_issue_month'].label, 'ออกเมื่อวันที่: เดือน')
        self.assertEqual(positions['stub_cancelled_year'].label, 'ลงวันที่: ปี')
        self.assertEqual(positions['certificate_registered_shares'].label, 'แบ่งเป็น')
        self.assertEqual(
            positions['certificate_shareholder'].label,
            'ใบหุ้นนี้ออกให้ไว้เพื่อแสดงว่า',
        )
        self.assertEqual(positions['certificate_issue_year'].label, 'พุทธศักราช')

        position = positions['certificate_company']
        position.write({'label': 'ชื่อบริษัท', 'x_mm': 140.25, 'font_size_pt': 16})
        self.env['buz.share.certificate.layout.position']._sync_document_labels()
        self.assertEqual(position.label, 'บริษัท')
        self.assertEqual((position.x_mm, position.font_size_pt), (140.25, 16))

    def test_dates_print_as_separate_two_digit_values(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        certificate = self.env['buz.share.certificate.print.wizard'].create({
            'issue_date': '2026-11-09',
            'cancelled_date': '2026-01-02',
            'received_date': '2026-12-31',
        })
        report = self.env.ref('buz_share_certificate.action_report_share_certificate')
        markup, _content_type = report._render_qweb_html(report.report_name, certificate.ids)
        document = lxml_html.fromstring(markup)

        expected = {
            'stub_issue_date': '09', 'stub_issue_month': '11', 'stub_issue_year': '69',
            'stub_cancelled_date': '02', 'stub_cancelled_month': '01', 'stub_cancelled_year': '69',
            'stub_received_date': '31', 'stub_received_month': '12', 'stub_received_year': '69',
            'certificate_issue_day': '09', 'certificate_issue_month': '11',
            'certificate_issue_year': '69',
        }
        for code, value in expected.items():
            spans = document.xpath('//span[@style=$style]', style=config.get_position_style(code))
            self.assertEqual([span.text_content() for span in spans], [value], code)

        empty = self.env['buz.share.certificate.print.wizard'].create({})
        empty_markup, _content_type = report._render_qweb_html(report.report_name, empty.ids)
        empty_document = lxml_html.fromstring(empty_markup)
        for code in expected:
            self.assertFalse(
                empty_document.xpath('//span[@style=$style]', style=config.get_position_style(code)),
                code,
            )

    def test_new_date_positions_reset_without_moving_day(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        day = config.position_ids.filtered(lambda item: item.code == 'stub_issue_date')
        month = config.position_ids.filtered(lambda item: item.code == 'stub_issue_month')
        year = config.position_ids.filtered(lambda item: item.code == 'stub_issue_year')

        self.assertEqual((day.x_mm, month.x_mm, year.x_mm), (62, 74, 86))
        day.x_mm = 63.5
        month.write({'x_mm': 80, 'y_mm': 45})
        month.action_reset_position()

        self.assertEqual((month.x_mm, month.y_mm), (74, 42))
        self.assertEqual(day.x_mm, 63.5)

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

        pdf, _content_type = report._render_qweb_pdf(report.report_name, certificate.ids)
        page = next(extract_pages(BytesIO(pdf)))
        images = [image for figure in page if isinstance(figure, LTFigure)
                  for image in figure if isinstance(image, LTImage)]
        self.assertTrue(any(abs(image.x0 - 42.5 * mm) < 1 for image in images))

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
        self.assertTrue(report.paperformat_id.disable_shrinking)
        self.assertEqual(
            (report.paperformat_id.margin_top, report.paperformat_id.margin_bottom,
             report.paperformat_id.margin_left, report.paperformat_id.margin_right),
            (5, 5, 8, 7),
        )
        company_position = config.position_ids.filtered(lambda item: item.code == 'stub_company')
        self.assertEqual((company_position.x_mm, company_position.y_mm), (22, 24))
        self.assertEqual(
            config.get_position_style('stub_company'),
            'left:14.0mm;top:19.0mm;font-size:10.0pt;',
        )

        certificate = self.env['buz.share.certificate.print.wizard'].create({
            'company_name': 'Margin Test',
        })
        html, _content_type = report._render_qweb_html(report.report_name, certificate.ids)
        html = html.decode() if isinstance(html, bytes) else html
        self.assertIn('width:282.0mm;height:200.0mm;', html)
        self.assertIn('left:14.0mm;top:19.0mm;font-size:10.0pt;', html)

        pdf, _content_type = report.with_context(force_report_rendering=True)._render_qweb_pdf(
            report.report_name, certificate.ids
        )
        reader = PdfFileReader(BytesIO(pdf))
        self.assertEqual(reader.getNumPages(), 1)
        page = reader.getPage(0)
        self.assertAlmostEqual(float(page.mediaBox.getWidth()), 841.89, delta=2)
        self.assertAlmostEqual(float(page.mediaBox.getHeight()), 595.28, delta=2)
        rendered_page = next(extract_pages(BytesIO(pdf)))
        images = [image for figure in rendered_page if isinstance(figure, LTFigure)
                  for image in figure if isinstance(image, LTImage)]
        self.assertTrue(any(
            abs(image.x0 - 22 * mm) < 1
            and abs(image.y1 - (rendered_page.height - 24 * mm)) < 1
            for image in images
        ))
        self.assertTrue(any(
            abs(image.x0 - 139.5 * mm) < 1
            and abs(image.y1 - (rendered_page.height - 33 * mm)) < 1
            for image in images
        ))

        second = self.env['buz.share.certificate.print.wizard'].create({'company_name': 'Second Page'})
        pdf, _content_type = report._render_qweb_pdf(report.report_name, [certificate.id, second.id])
        self.assertEqual(PdfFileReader(BytesIO(pdf)).getNumPages(), 2)

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
