from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestShareCertificate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = new_test_user(cls.env, login='share_certificate_owner', groups='base.group_user')
        cls.other = new_test_user(cls.env, login='share_certificate_other', groups='base.group_user')
        cls.certificates = cls.env['buz.share.certificate'].with_user(cls.owner)
        cls.wizards = cls.env['buz.share.certificate.wizard'].with_user(cls.owner)

    def test_template_and_record_lifecycle(self):
        template = self.env['buz.share.certificate.template'].with_user(self.owner).create({
            'name': 'ตัวอย่าง', 'company_name': 'ทดสอบ', 'shareholder_name': 'ผู้ถือหุ้น',
            'certificate_number': '01', 'share_count': 10,
        })
        action = template.action_use_template()
        certificate = self.certificates.browse(action['res_id'])
        self.assertEqual(certificate.state, 'draft')
        self.assertEqual(certificate.company_name, 'ทดสอบ')
        self.assertEqual(certificate.shareholder_name, 'ผู้ถือหุ้น')
        self.assertEqual(certificate.template_id, template)
        certificate.write({'shareholder_name': 'แก้ไขแล้ว'})
        self.assertEqual(template.shareholder_name, 'ผู้ถือหุ้น')

        wizard = self.wizards.create({'certificate_id': certificate.id})
        for method in (wizard.action_open_pdf, wizard.action_download_pdf):
            method()
            self.assertEqual(certificate.state, 'draft')
        wizard.action_print_pdf()
        self.assertEqual(certificate.state, 'done')
        done_form = Form(certificate)
        with self.assertRaises(AssertionError):
            done_form.shareholder_name = 'ห้ามแก้ไขผ่านฟอร์ม'
        with self.assertRaises(UserError):
            certificate.write({'shareholder_name': 'ห้ามแก้ไข'})
        with self.assertRaises(UserError):
            certificate.write({'state': 'draft', 'shareholder_name': 'ห้ามแก้ไขพร้อมกัน'})
        wizard.action_print_pdf()
        self.assertEqual(self.certificates.search_count([('id', '=', certificate.id)]), 1)
        certificate.action_reset_to_draft()
        certificate.write({'shareholder_name': 'แก้ไขหลัง reset'})
        self.assertEqual(template.shareholder_name, 'ผู้ถือหุ้น')

    def test_owner_isolation(self):
        certificate = self.certificates.create({'certificate_number': '02'})
        template = self.env['buz.share.certificate.template'].with_user(self.owner).create({'name': 'ส่วนตัว'})
        self.assertFalse(self.env['buz.share.certificate'].with_user(self.other).search([('id', '=', certificate.id)]))
        self.assertFalse(self.env['buz.share.certificate.template'].with_user(self.other).search([('id', '=', template.id)]))
        with self.assertRaises(AccessError):
            template.with_user(self.other).action_use_template()
        with self.assertRaises(AccessError):
            certificate.with_user(self.other).read(['certificate_number'])
        other_wizard = self.env['buz.share.certificate.wizard'].with_user(self.other).create({
            'certificate_id': certificate.id,
        })
        with self.assertRaises(AccessError):
            other_wizard.action_open_pdf()
        with self.assertRaises(AccessError):
            certificate.write({'user_id': self.other.id})

    def test_entry_form_computes_total_paid(self):
        form = Form(self.certificates)
        form.certificate_number = 'SC-FORM-01'
        form.share_count = 12
        form.paid_per_share = 50
        certificate = form.save()
        self.assertEqual(certificate.total_paid, 600)

        certificate.write({'share_count': 20})
        self.assertEqual(certificate.total_paid, 1000)

    def test_entry_form_exposes_print_action(self):
        arch = self.env.ref('buz_share_certificate.view_share_certificate_form').arch_db
        self.assertIn('name="action_print_options"', arch)
        for field_name in (
            'company_name', 'registration_number', 'certificate_number', 'issue_date',
            'shareholder_name', 'share_count', 'share_number_from', 'share_number_to',
            'registered_capital', 'total_shares', 'share_value', 'paid_per_share',
            'total_paid', 'previous_certificate_number', 'previous_certificate_date',
            'director_one', 'director_two', 'receipt_date',
        ):
            self.assertIn('name="%s"' % field_name, arch)

    def test_report_uses_certificate_data(self):
        certificate = self.certificates.create({
            'certificate_number': '03', 'company_name': 'บริษัทตัวอย่าง',
            'shareholder_name': 'ชื่อผู้ถือหุ้นตัวอย่าง', 'share_count': 15,
        })
        report = self.env.ref('buz_share_certificate.action_report_share_certificate')
        html = report.with_user(self.owner)._render_qweb_html(report.report_name, certificate.ids)[0].decode()
        self.assertGreaterEqual(html.count('ชื่อผู้ถือหุ้นตัวอย่าง'), 2)
        self.assertGreaterEqual(html.count('บริษัทตัวอย่าง'), 2)

    def test_preprinted_report_outputs_values_without_labels(self):
        certificate = self.certificates.create({
            'certificate_number': 'SC-TEST-01', 'company_name': 'Mogen Demo Co',
            'registration_number': '0105566000123', 'issue_date': '2024-02-03',
            'shareholder_name': 'Shareholder Example', 'share_count': 12,
            'share_number_from': '1', 'share_number_to': '12',
            'registered_capital': 100000, 'total_shares': 1000,
            'share_value': 100, 'paid_per_share': 50, 'total_paid': 600,
            'previous_certificate_number': 'OLD-01',
            'previous_certificate_date': '2023-01-02', 'receipt_date': '2024-02-04',
            'director_one': 'Director One', 'director_two': 'Director Two',
        })
        report = self.env.ref('buz_share_certificate.action_report_share_certificate')
        html = report.with_user(self.owner)._render_qweb_html(report.report_name, certificate.ids)[0].decode()

        for value in ('SC-TEST-01', 'Mogen Demo Co', 'Shareholder Example', 'Director One', 'Director Two'):
            self.assertIn(value, html)
        for label in ('ต้นขั้วใบหุ้น', 'ทะเบียนเลขที่', 'หมายเลขหุ้นตั้งแต่', 'ออกให้ไว้ ณ วันที่', 'กรรมการ'):
            self.assertNotIn(label, html)
        self.assertNotIn('share_certificate_form_preview.jpg', html)
        self.assertNotIn('class="share-reference"', html)

    def test_layout_config_defaults_access_and_reset(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        self.assertEqual(config.stub_width_mm, 91.5)
        with self.assertRaises(AccessError):
            config.with_user(self.owner).read(['stub_width_mm'])

        config.write({'stub_width_mm': 100, 'stub_company_font_size_pt': 12})
        config.action_reset_defaults()
        self.assertEqual(config.stub_width_mm, 91.5)
        self.assertEqual(config.stub_company_font_size_pt, 10)
        with self.assertRaises(ValidationError):
            config.write({'stub_company_font_size_pt': 31})

    def test_layout_page_setup_and_individual_positions(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        paperformat = self.env.ref('buz_share_certificate.paperformat_share_certificate')
        self.assertEqual((paperformat.format, paperformat.orientation), ('A4', 'Landscape'))
        self.assertEqual(config.font_family, 'Sarabun')

        config.write({
            'margin_top_mm': 5, 'margin_bottom_mm': 6,
            'margin_left_mm': 7, 'margin_right_mm': 8,
            'stub_company_x_mm': 25, 'stub_company_y_mm': 26,
            'certificate_company_x_mm': 150, 'certificate_company_y_mm': 34,
            'stub_company_font_size_pt': 12,
        })
        self.assertEqual((paperformat.format, paperformat.orientation), ('A4', 'Landscape'))
        self.assertEqual((paperformat.margin_top, paperformat.margin_bottom,
                          paperformat.margin_left, paperformat.margin_right), (0, 0, 0, 0))
        self.assertEqual((config.stub_company_x_mm, config.certificate_company_x_mm), (25, 150))
        self.assertEqual((config.stub_company_y_mm, config.certificate_company_y_mm), (26, 34))
        preview = self.env.ref('buz_share_certificate.action_report_share_certificate_preview')
        html = preview._render_qweb_html(preview.report_name, config.ids)[0].decode()
        self.assertIn('width:297mm; height:210mm;', html)
        self.assertIn('left:0mm; top:0mm; width:297mm; height:210mm;', html)
        self.assertIn('left:7.0mm; top:5.0mm; width:282.0mm; height:199.0mm;', html)
        self.assertIn('font-family:Sarabun, sans-serif;', html)
        self.assertIn('left:25.0mm; top:26.0mm', html)
        self.assertIn('left:150.0mm; top:34.0mm', html)
        self.assertIn('font-size:12.0pt;', html)
        self.assertFalse(config.margin_warning)
        config.write({'margin_left_mm': 151})
        self.assertTrue(config.margin_warning)
        config.write({'margin_left_mm': 7})
        with self.assertRaises(ValidationError):
            config.write({'margin_left_mm': 290, 'margin_right_mm': 10})

        config.action_reset_defaults()
        self.assertEqual((paperformat.format, paperformat.orientation), ('A4', 'Landscape'))
        self.assertEqual((paperformat.margin_top, paperformat.margin_bottom,
                          paperformat.margin_left, paperformat.margin_right), (0, 0, 0, 0))
        self.assertEqual((config.stub_company_x_mm, config.certificate_company_x_mm), (22, 139.5))

    def test_layout_preview_uses_text_form_guide_and_sample_values(self):
        config = self.env.ref('buz_share_certificate.share_certificate_layout_config_default')
        action = config.action_preview_layout()
        self.assertEqual(action['type'], 'ir.actions.report')
        report = self.env.ref('buz_share_certificate.action_report_share_certificate_preview')
        html = report._render_qweb_html(report.report_name, config.ids)[0].decode()

        self.assertNotIn('share_certificate_form_preview.jpg', html)
        self.assertIn('class="share-reference"', html)
        self.assertIn('share-reference-row', html)
        self.assertIn('share-reference-dots', html)
        self.assertIn('border-bottom: 1px dotted', html)
        self.assertIn('width:297mm; height:210mm;', html)
        self.assertIn('left:0.0mm; top:0.0mm; width:297.0mm; height:210.0mm;', html)
        self.assertIn('SC-0001', html)
