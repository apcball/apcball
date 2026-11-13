from odoo.exceptions import AccessError, UserError
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

    def test_report_uses_certificate_data(self):
        certificate = self.certificates.create({
            'certificate_number': '03', 'company_name': 'บริษัทตัวอย่าง',
            'shareholder_name': 'ชื่อผู้ถือหุ้นตัวอย่าง', 'share_count': 15,
        })
        report = self.env.ref('buz_share_certificate.action_report_share_certificate')
        html = report.with_user(self.owner)._render_qweb_html(report.report_name, certificate.ids)[0].decode()
        self.assertGreaterEqual(html.count('ชื่อผู้ถือหุ้นตัวอย่าง'), 2)
        self.assertGreaterEqual(html.count('บริษัทตัวอย่าง'), 2)
