from datetime import date, timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestITAsset(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.category = cls.env['buz.it.asset.category'].create({
            'name': 'Laptop', 'company_id': cls.company.id,
        })
        cls.location = cls.env['buz.it.asset.location'].create({
            'name': 'IT Room', 'company_id': cls.company.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Asset Holder', 'company_id': cls.company.id,
        })

    def test_assign_and_return_creates_immutable_history(self):
        asset = self.env['buz.it.asset'].create({
            'name': 'ThinkPad', 'category_id': self.category.id,
            'location_id': self.location.id,
        })
        asset.assigned_employee_id = self.employee
        asset.action_assign()
        self.assertEqual(asset.state, 'assigned')
        assignment = asset.assignment_ids
        self.assertEqual(assignment.employee_id, self.employee)
        with self.assertRaises(UserError):
            other = self.env['hr.employee'].create({'name': 'Other'})
            assignment.write({'employee_id': other.id})
        asset.action_return()
        self.assertEqual(asset.state, 'available')
        self.assertFalse(asset.assigned_employee_id)
        self.assertTrue(assignment.returned_date)
        with self.assertRaises(UserError):
            asset.action_return()

    def test_license_seat_limit_and_expiry(self):
        product = self.env['buz.it.software.product'].create({
            'name': 'Office', 'company_id': self.company.id,
        })
        license_record = self.env['buz.it.software.license'].create({
            'name': 'Office 1 seat', 'product_id': product.id,
            'seat_count': 1, 'expiration_date': date.today() - timedelta(days=1),
            'company_id': self.company.id,
        })
        with self.assertRaises(UserError):
            self.env['buz.it.software.installation'].create({
                'license_id': license_record.id,
                'employee_id': self.employee.id,
                'company_id': self.company.id,
            })

    def test_installation_requires_one_target(self):
        product = self.env['buz.it.software.product'].create({
            'name': 'VPN Client', 'company_id': self.company.id,
        })
        license_record = self.env['buz.it.software.license'].create({
            'name': 'VPN', 'product_id': product.id, 'seat_count': 2,
            'company_id': self.company.id,
        })
        with self.assertRaises(ValidationError):
            self.env['buz.it.software.installation'].create({
                'license_id': license_record.id,
                'company_id': self.company.id,
            })
