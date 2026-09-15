from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestSoftwareInstallationTarget(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Software Installation Employee',
            'company_id': cls.company.id,
        })
        cls.other_employee = cls.env['hr.employee'].create({
            'name': 'Other Software Employee',
            'company_id': cls.company.id,
        })
        cls.asset_type = cls.env.ref('buz_it_asset.type_desktop_pc')
        cls.software_type = cls.env.ref('buz_it_asset.software_type_other')
        cls.product = cls.env['buz.it.software.product'].create({
            'name': 'Installation Test Product',
            'software_type': cls.software_type.id,
            'company_id': cls.company.id,
        })
        cls.license = cls.env['buz.it.software.license'].create({
            'name': 'Installation Test License',
            'product_id': cls.product.id,
            'license_type': 'free',
            'company_id': cls.company.id,
        })

    def _create_asset(self, suffix, employee):
        return self.env['buz.it.asset'].create({
            'name': 'Installation Test Asset ' + suffix,
            'asset_tag': 'ITTEST' + suffix,
            'type_id': self.asset_type.id,
            'company_id': self.company.id,
            'assigned_employee_id': employee.id,
        })

    def _new_installation(self, employee=None, asset=None):
        return self.env['buz.it.software.installation'].new({
            'license_id': self.license.id,
            'company_id': self.company.id,
            'employee_id': employee.id if employee else False,
            'asset_id': asset.id if asset else False,
        })

    def test_employee_without_asset_is_valid(self):
        installation = self._new_installation(self.other_employee)
        result = installation._onchange_employee_id()
        self.assertFalse(installation.asset_id)
        self.assertFalse(result.get('warning'))
        record = self.env['buz.it.software.installation'].create({
            'license_id': self.license.id,
            'employee_id': self.other_employee.id,
        })
        self.assertEqual(record.employee_id, self.other_employee)
        self.assertFalse(record.asset_id)

    def test_employee_with_one_asset_is_auto_selected(self):
        asset = self._create_asset('01', self.employee)
        installation = self._new_installation(self.employee)
        installation._onchange_employee_id()
        self.assertEqual(installation.asset_id, asset)
        record = self.env['buz.it.software.installation'].create({
            'license_id': self.license.id,
            'employee_id': self.employee.id,
        })
        self.assertEqual(record.asset_id, asset)

    def test_employee_with_multiple_assets_requires_asset(self):
        self._create_asset('02', self.employee)
        self._create_asset('03', self.employee)
        installation = self._new_installation(self.employee)
        result = installation._onchange_employee_id()
        self.assertFalse(installation.asset_id)
        self.assertIn('warning', result)
        with self.assertRaisesRegex(ValidationError, 'multiple assets'):
            self.env['buz.it.software.installation'].create({
                'license_id': self.license.id,
                'employee_id': self.employee.id,
            })

    def test_asset_must_belong_to_selected_employee(self):
        asset = self._create_asset('04', self.employee)
        with self.assertRaisesRegex(ValidationError, 'not currently assigned'):
            self.env['buz.it.software.installation'].create({
                'license_id': self.license.id,
                'employee_id': self.other_employee.id,
                'asset_id': asset.id,
            })

    def test_changing_employee_clears_asset_from_previous_employee(self):
        asset = self._create_asset('05', self.employee)
        installation = self._new_installation(self.employee, asset)
        installation.employee_id = self.other_employee
        installation._onchange_employee_id()
        self.assertFalse(installation.asset_id)