from datetime import date, timedelta
from unittest.mock import patch

from psycopg2.errors import SerializationFailure, UniqueViolation

from odoo import fields
from odoo.addons.buz_it_asset.hooks import pre_init_hook
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestITAsset(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.category = cls.env['buz.it.asset.category'].create({'name': 'End User Devices'})
        cls.asset_type = cls.env['buz.it.asset.type'].create({
            'name': 'Laptop', 'category_id': cls.category.id,
        })
        cls.location = cls.env['buz.it.asset.location'].create({
            'name': 'IT Room', 'company_id': cls.company.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Asset Holder', 'company_id': cls.company.id,
        })
        cls.department = cls.env['hr.department'].create({
            'name': 'Shared IT Equipment', 'company_id': cls.company.id,
        })

    def test_default_hardware_taxonomy(self):
        categories = self.env['buz.it.asset.category'].search([
            ('id', 'in', [
                self.env.ref('buz_it_asset.category_end_user_devices').id,
                self.env.ref('buz_it_asset.category_network_infrastructure').id,
                self.env.ref('buz_it_asset.category_servers_storage').id,
                self.env.ref('buz_it_asset.category_peripherals_accessories').id,
            ]),
        ])
        self.assertEqual(len(categories), 4)
        self.assertEqual(sum(len(category.type_ids) for category in categories), 15)
        self.assertEqual(
            self.env.ref('buz_it_asset.type_laptop').category_id,
            self.env.ref('buz_it_asset.category_end_user_devices'),
        )

    def test_default_specification_profiles(self):
        expected = {
            'type_desktop_pc': 'desktop',
            'type_laptop': 'laptop',
            'type_tablet': 'mobile',
            'type_smartphone': 'mobile',
            'type_router': 'network',
            'type_switch': 'network',
            'type_access_point': 'network',
            'type_hardware_firewall': 'network',
            'type_server': 'server',
            'type_nas_san': 'storage',
            'type_hdd_ssd': 'storage',
            'type_monitor': 'monitor',
            'type_printer_scanner': 'printer',
            'type_ups': 'ups',
            'type_keyboard_mouse': 'input',
        }
        for xmlid, profile in expected.items():
            self.assertEqual(self.env.ref(f'buz_it_asset.{xmlid}').spec_profile, profile)
        self.assertEqual(self.asset_type.spec_profile, 'generic')

    def test_serial_number_is_required_for_new_assets(self):
        with self.assertRaises(ValidationError):
            self.env['buz.it.asset'].create({
                'name': 'Missing Serial',
                'type_id': self.asset_type.id,
            })

    def test_changing_type_keeps_existing_specifications(self):
        asset = self.env['buz.it.asset'].create({
            'name': 'Profile Test',
            'type_id': self.asset_type.id,
            'serial_number': 'SN-PROFILE-001',
            'cpu': 'Intel Core i7',
        })
        other_type = self.env['buz.it.asset.type'].create({
            'name': 'Network Type', 'category_id': self.category.id,
            'spec_profile': 'network',
        })
        asset.write({'type_id': other_type.id})
        self.assertEqual(asset.cpu, 'Intel Core i7')
        self.assertEqual(asset.spec_profile, 'network')

    def test_purchase_information_uses_company_currency(self):
        asset = self.env['buz.it.asset'].create({
            'name': 'Purchased Laptop',
            'type_id': self.asset_type.id,
            'serial_number': 'SN-PURCHASE-001',
            'purchase_date': date(2026, 8, 1),
            'purchase_price': 42500,
        })
        self.assertEqual(asset.purchase_price, 42500)
        self.assertEqual(asset.currency_id, self.company.currency_id)

    def test_asset_accepts_employee_or_department_not_both(self):
        department_asset = self.env['buz.it.asset'].create({
            'name': 'Shared Printer',
            'type_id': self.asset_type.id,
            'serial_number': 'SN-DEPARTMENT-001',
            'responsible_department_id': self.department.id,
        })
        department_asset.action_assign()
        self.assertEqual(department_asset.state, 'assigned')
        self.assertEqual(
            department_asset.assignment_ids.department_id,
            self.department,
        )
        self.assertFalse(department_asset.assignment_ids.employee_id)
        department_asset.action_return()
        self.assertFalse(department_asset.responsible_department_id)

        with self.assertRaises(ValidationError):
            self.env['buz.it.asset'].create({
                'name': 'Invalid Shared Asset',
                'type_id': self.asset_type.id,
                'serial_number': 'SN-OWNER-INVALID-001',
                'assigned_employee_id': self.employee.id,
                'responsible_department_id': self.department.id,
            })

    def test_maintenance_internal_external_and_completion(self):
        asset = self.env['buz.it.asset'].create({
            'name': 'Repair Asset',
            'type_id': self.asset_type.id,
            'serial_number': 'SN-REPAIR-001',
        })
        internal = self.env['buz.it.asset.maintenance'].create({
            'asset_id': asset.id,
            'sent_date': date(2026, 8, 1),
            'symptom': 'Does not boot',
            'technician_employee_id': self.employee.id,
            'cost': 1200,
        })
        self.assertEqual(internal.currency_id, self.company.currency_id)
        self.assertIn(internal, asset.maintenance_ids)
        internal.action_done()
        self.assertEqual(internal.state, 'done')
        self.assertTrue(internal.completed_date)
        with self.assertRaises(UserError):
            internal.unlink()

        external = self.env['buz.it.asset.maintenance'].create({
            'asset_id': asset.id,
            'sent_date': date(2026, 8, 2),
            'symptom': 'Damaged display',
            'external_technician_name': 'External Technician',
        })
        external.action_start()
        self.assertEqual(external.state, 'in_progress')

        with self.assertRaises(ValidationError):
            self.env['buz.it.asset.maintenance'].create({
                'asset_id': asset.id,
                'symptom': 'Invalid technician selection',
                'technician_employee_id': self.employee.id,
                'external_technician_name': 'External Technician',
            })

    def test_completed_maintenance_requires_valid_date(self):
        asset = self.env['buz.it.asset'].create({
            'name': 'Maintenance Date Asset',
            'type_id': self.asset_type.id,
            'serial_number': 'SN-REPAIR-DATE-001',
        })
        with self.assertRaises(ValidationError):
            self.env['buz.it.asset.maintenance'].create({
                'asset_id': asset.id,
                'sent_date': date(2026, 8, 2),
                'completed_date': date(2026, 8, 1),
                'symptom': 'Invalid dates',
                'state': 'done',
            })

    def test_assign_and_return_creates_immutable_history(self):
        asset = self.env['buz.it.asset'].create({
            'name': 'ThinkPad', 'type_id': self.asset_type.id,
            'serial_number': 'SN-THINKPAD-001',
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

    def test_asset_tag_sequence_is_yearly_and_company_specific(self):
        company_a = self.env['res.company'].create({'name': 'Asset Company A'})
        company_b = self.env['res.company'].create({'name': 'Asset Company B'})
        category_a = self.env['buz.it.asset.category'].create({'name': 'Laptop A'})
        category_b = self.env['buz.it.asset.category'].create({'name': 'Laptop B'})
        type_a = self.env['buz.it.asset.type'].create({'name': 'Laptop', 'category_id': category_a.id})
        type_b = self.env['buz.it.asset.type'].create({'name': 'Laptop', 'category_id': category_b.id})

        def create_asset(company, asset_type, name, sequence_date):
            return self.env['buz.it.asset'].with_company(company).with_context(
                ir_sequence_date=sequence_date,
            ).create({
                'name': name,
                'type_id': asset_type.id,
                'serial_number': f'SN-{name}',
                'company_id': company.id,
            })

        first = create_asset(company_a, type_a, 'A-1', date(2026, 8, 1))
        second = create_asset(company_a, type_a, 'A-2', date(2026, 8, 2))
        next_month = create_asset(
            company_a, type_a, 'A-3', date(2026, 9, 1),
        )
        other_company = create_asset(
            company_b, type_b, 'B-1', date(2026, 8, 1),
        )
        next_year = create_asset(
            company_a, type_a, 'A-2027', date(2027, 1, 1),
        )

        self.assertEqual(first.asset_tag, 'ITA/2026/08/0001')
        self.assertEqual(second.asset_tag, 'ITA/2026/08/0002')
        self.assertEqual(next_month.asset_tag, 'ITA/2026/09/0003')
        self.assertEqual(other_company.asset_tag, 'ITA/2026/08/0001')
        self.assertEqual(next_year.asset_tag, 'ITA/2027/01/0001')
        sequences = self.env['ir.sequence'].search([
            ('code', '=', 'buz.it.asset'),
            ('company_id', 'in', (company_a.id, company_b.id)),
        ])
        self.assertEqual(len(sequences), 2)
        self.assertTrue(all(sequences.mapped('use_date_range')))

    def test_asset_tag_date_range_race_is_retryable(self):
        sequence = self.company._ensure_it_asset_sequence()
        with self.assertRaises(SerializationFailure):
            with self.env.cr.savepoint():
                with patch.object(
                    type(sequence),
                    '_next',
                    side_effect=UniqueViolation(),
                ):
                    self.company._next_it_asset_tag(date(2026, 8, 1))

    def test_multi_company_relations_are_rejected(self):
        other_company = self.env['res.company'].create({
            'name': 'Other Asset Company',
        })
        other_category = self.env['buz.it.asset.category'].create({'name': 'Other Category'})
        other_type = self.env['buz.it.asset.type'].create({
            'name': 'Other Type', 'category_id': other_category.id,
        })
        other_employee = self.env['hr.employee'].create({
            'name': 'Other Employee',
            'company_id': other_company.id,
        })
        other_product = self.env['buz.it.software.product'].create({
            'name': 'Other Product',
            'company_id': other_company.id,
        })
        asset = self.env['buz.it.asset'].create({
            'name': 'Company Asset',
            'type_id': self.asset_type.id,
            'serial_number': 'SN-COMPANY-001',
            'company_id': self.company.id,
        })
        product = self.env['buz.it.software.product'].create({
            'name': 'Company Product',
            'company_id': self.company.id,
        })
        license_record = self.env['buz.it.software.license'].create({
            'name': 'Company License',
            'product_id': product.id,
            'company_id': self.company.id,
        })

        invalid_creates = [
            ('buz.it.asset.assignment', {
                'asset_id': asset.id,
                'employee_id': other_employee.id,
                'company_id': self.company.id,
            }),
            ('buz.it.software.license', {
                'name': 'Invalid License',
                'product_id': other_product.id,
                'company_id': self.company.id,
            }),
            ('buz.it.software.installation', {
                'license_id': license_record.id,
                'employee_id': other_employee.id,
                'company_id': self.company.id,
            }),
        ]
        for model_name, values in invalid_creates:
            with self.assertRaises(UserError):
                with self.env.cr.savepoint():
                    self.env[model_name].create(values)

    def test_installation_create_access(self):
        requester_group = self.env.ref(
            'buz_it_helpdesk.group_it_requester',
        )
        support_group = self.env.ref(
            'buz_it_helpdesk.group_it_support_agent',
        )
        manager_group = self.env.ref(
            'buz_it_helpdesk.group_it_helpdesk_manager',
        )

        def create_user(login, group):
            return self.env['res.users'].with_context(
                no_reset_password=True,
            ).create({
                'name': login,
                'login': login,
                'company_id': self.company.id,
                'company_ids': [fields.Command.set([self.company.id])],
                'groups_id': [fields.Command.set([group.id])],
            })

        requester = create_user('asset-requester', requester_group)
        support = create_user('asset-support', support_group)
        manager = create_user('asset-manager', manager_group)
        installation_model = self.env['buz.it.software.installation']

        self.assertFalse(
            installation_model.with_user(requester).check_access_rights(
                'create', raise_exception=False,
            ),
        )
        self.assertTrue(
            installation_model.with_user(support).check_access_rights(
                'create', raise_exception=False,
            ),
        )
        self.assertTrue(
            installation_model.with_user(manager).check_access_rights(
                'create', raise_exception=False,
            ),
        )
        maintenance_model = self.env['buz.it.asset.maintenance']
        self.assertFalse(
            maintenance_model.with_user(requester).check_access_rights(
                'create', raise_exception=False,
            ),
        )
        self.assertTrue(
            maintenance_model.with_user(support).check_access_rights(
                'create', raise_exception=False,
            ),
        )
        self.assertTrue(
            maintenance_model.with_user(manager).check_access_rights(
                'create', raise_exception=False,
            ),
        )

    def test_pre_init_rejects_legacy_schema(self):
        self.env.cr.execute(
            'CREATE TABLE buz_it_asset_spec_line (id integer)',
        )
        try:
            with self.assertRaises(UserError):
                pre_init_hook(self.env)
        finally:
            self.env.cr.execute('DROP TABLE buz_it_asset_spec_line')

        self.env.cr.execute(
            'ALTER TABLE buz_it_asset ADD COLUMN asset_name varchar',
        )
        try:
            with self.assertRaises(UserError):
                pre_init_hook(self.env)
        finally:
            self.env.cr.execute(
                'ALTER TABLE buz_it_asset DROP COLUMN asset_name',
            )

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
