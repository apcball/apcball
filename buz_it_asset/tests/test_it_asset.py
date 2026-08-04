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
        cls.helpdesk_category = cls.env['buz.helpdesk.category'].create({'name': 'Hardware Support'})
        cls.helpdesk_type = cls.env['buz.helpdesk.category.type'].create({'name': 'Laptop', 'category_id': cls.helpdesk_category.id})
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
        cls.software_type = cls.env['buz.it.software.type'].create({
            'name': 'Office',
        })
        cls.outcome_parts_replaced = cls.env[
            'buz.it.asset.repair.outcome'
        ].create({
            'name': 'Parts Replaced',
            'code': 'parts_replaced',
            'behavior': 'parts_replaced',
        })
        cls.outcome_asset_replaced = cls.env[
            'buz.it.asset.repair.outcome'
        ].create({
            'name': 'Asset Replaced',
            'code': 'asset_replaced',
            'behavior': 'asset_replaced',
        })
        cls.outcome_retired = cls.env[
            'buz.it.asset.repair.outcome'
        ].create({
            'name': 'Retired',
            'code': 'retired',
            'behavior': 'retired',
        })

    def test_install_starts_without_asset_presets(self):
        for xmlid in (
            'category_end_user_devices',
            'category_network_infrastructure',
            'type_laptop',
            'software_type_office',
            'repair_outcome_parts_replaced',
        ):
            self.assertFalse(
                self.env.ref(
                    f'buz_it_asset.{xmlid}', raise_if_not_found=False,
                ),
                xmlid,
            )
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

    def test_software_product_type_version_and_edition(self):
        custom_type = self.env['buz.it.software.type'].create({
            'name': 'Developer Tools',
        })
        product = self.env['buz.it.software.product'].create({
            'name': 'Office',
            'software_type': custom_type.id,
            'version': '2026',
            'edition': 'Business',
            'company_id': self.company.id,
        })
        other_version = self.env['buz.it.software.product'].create({
            'name': 'Office',
            'software_type': self.software_type.id,
            'version': '2027',
            'edition': 'Business',
            'company_id': self.company.id,
        })
        self.assertEqual(product.software_type, custom_type)
        self.assertEqual(product.version, '2026')
        self.assertNotEqual(product, other_version)

    def test_software_license_currency_and_contract_dates(self):
        product = self.env['buz.it.software.product'].create({
            'name': 'Accounting', 'software_type': self.software_type.id, 'company_id': self.company.id,
        })
        license_record = self.env['buz.it.software.license'].create({
            'name': 'Accounting 2026', 'product_id': product.id,
            'start_date': date(2026, 8, 1),
            'expiration_date': date(2027, 7, 31),
            'company_id': self.company.id,
        })
        self.assertEqual(license_record.currency_id, self.company.currency_id)
        with self.assertRaises(ValidationError):
            license_record.write({
                'start_date': date(2027, 8, 1),
                'expiration_date': date(2027, 7, 31),
            })

    def test_free_license_has_unlimited_installations(self):
        product = self.env['buz.it.software.product'].create({
            'name': 'Free Utility', 'software_type': self.software_type.id, 'company_id': self.company.id,
        })
        license_record = self.env['buz.it.software.license'].create({
            'name': 'Free Utility', 'product_id': product.id,
            'license_type': 'free', 'seat_count': 1,
            'company_id': self.company.id,
        })
        second_employee = self.env['hr.employee'].create({
            'name': 'Second User', 'company_id': self.company.id,
        })
        self.env['buz.it.software.installation'].create({
            'license_id': license_record.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        self.env['buz.it.software.installation'].create({
            'license_id': license_record.id,
            'employee_id': second_employee.id,
            'company_id': self.company.id,
        })
        self.assertEqual(license_record.active_installation_count, 2)

    def test_asset_assignment_requires_holder_department_and_location(self):
        department_asset = self.env['buz.it.asset'].create({
            'name': 'Shared Printer',
            'type_id': self.asset_type.id,
            'serial_number': 'SN-DEPARTMENT-001',
            'location_id': self.location.id,
            'assigned_employee_id': self.employee.id,
            'responsible_department_id': self.department.id,
        })
        department_asset.action_assign()
        self.assertEqual(department_asset.state, 'assigned')
        self.assertEqual(
            department_asset.assignment_ids.department_id,
            self.department,
        )
        self.assertEqual(department_asset.assignment_ids.employee_id, self.employee)
        department_asset.action_return()
        self.assertFalse(department_asset.responsible_department_id)

        with self.assertRaises(ValidationError):
            self.env['buz.it.asset'].create({
                'name': 'Invalid Shared Asset',
                'type_id': self.asset_type.id,
                'serial_number': 'SN-OWNER-INVALID-001',
                'assigned_employee_id': self.employee.id,
                'responsible_department_id': self.department.id,
                'state': 'assigned',
            })

    def _create_repair_user(self, suffix, group_xmlid):
        return self.env['res.users'].create({
            'name': f'Repair User {suffix}',
            'login': f'repair_user_{suffix}',
            'email': f'repair-{suffix}@example.com',
            'company_id': self.company.id,
            'company_ids': [fields.Command.set([self.company.id])],
            'groups_id': [fields.Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref(group_xmlid).id,
            ])],
        })

    def _create_repair_asset(self, suffix, employee=None, state='available'):
        values = {
            'name': f'Repair Asset {suffix}',
            'type_id': self.asset_type.id,
            'serial_number': f'SN-REPAIR-{suffix}',
            'state': state,
        }
        if state == 'assigned':
            values.update({
                'location_id': self.location.id,
                'assigned_employee_id': employee.id,
                'responsible_department_id': self.department.id,
            })
        return self.env['buz.it.asset'].create(values)

    def _create_in_progress_repair_ticket(self, support, asset=None):
        ticket = self.env['buz.helpdesk.ticket'].with_user(support).create({
            'subject': 'Ticket generated repair history',
            'asset_id': asset.id if asset else False,
            'category_id': self.helpdesk_category.id,
            'category_type_id': self.helpdesk_type.id,
            'description': 'Does not power on',
        })
        ticket.with_context(buz_helpdesk_transition=True).write({
            'stage_id': self.env.ref('buz_it_helpdesk.stage_in_progress').id,
            'assigned_user_id': support.id,
            'create_ticket_date': date(2026, 8, 3),
        })
        return ticket.with_user(support)

    def test_maintenance_history_is_ticket_only(self):
        asset = self._create_repair_asset('MANUAL')
        with self.assertRaises(UserError):
            self.env['buz.it.asset.maintenance'].create({
                'asset_id': asset.id,
                'symptom': 'Manual history must be rejected',
            })

    def test_ticket_without_asset_closes_without_history(self):
        support = self._create_repair_user(
            'no_asset', 'buz_it_helpdesk.group_it_support_agent',
        )
        ticket = self._create_in_progress_repair_ticket(support)
        before = self.env['buz.it.asset.maintenance'].search_count([])
        ticket.action_close_ticket()
        self.assertTrue(ticket.is_closed_stage)
        self.assertEqual(
            self.env['buz.it.asset.maintenance'].search_count([]),
            before,
        )

    def test_ticket_closure_snapshots_readonly_maintenance_history(self):
        support = self._create_repair_user(
            'history', 'buz_it_helpdesk.group_it_support_agent',
        )
        employee = self.env['hr.employee'].create({
            'name': 'Repair Support Employee',
            'company_id': self.company.id,
            'user_id': support.id,
        })
        asset = self._create_repair_asset(
            'HISTORY', employee=employee, state='assigned',
        )
        ticket = self._create_in_progress_repair_ticket(support, asset)
        ticket.write({
            'diagnosis': 'Power supply failure',
            'repair_result': 'Replaced power supply and tested.',
            'repair_outcome_id': self.outcome_parts_replaced.id,
            'repair_instructions': 'Monitor the power supply for seven days.',
            'repair_part_ids': [fields.Command.create({
                'name': 'Power supply',
                'quantity': 1,
                'old_serial': 'PSU-OLD',
                'new_serial': 'PSU-NEW',
                'unit_price': 2500,
                'notes': 'Warranty 1 year',
            })],
        })
        original_assignment = (
            asset.assigned_employee_id,
            asset.responsible_department_id,
            asset.location_id,
        )
        ticket.action_close_ticket()

        self.assertEqual(asset.state, 'assigned')
        self.assertEqual(
            (
                asset.assigned_employee_id,
                asset.responsible_department_id,
                asset.location_id,
            ),
            original_assignment,
        )
        history = asset.maintenance_ids.filtered(
            lambda line: line.ticket_id == ticket
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history.repair_outcome_id, 'parts_replaced')
        self.assertEqual(history.diagnosis, 'Power supply failure')
        self.assertEqual(
            history.repair_result,
            'Replaced power supply and tested.',
        )
        self.assertEqual(history.performed_by_id, support)
        self.assertEqual(len(history.repair_part_ids), 1)
        self.assertEqual(history.repair_part_ids.new_serial, 'PSU-NEW')
        self.assertEqual(
            self.env['buz.it.asset.maintenance']._create_from_ticket(ticket),
            history,
        )
        self.assertEqual(
            self.env['buz.it.asset.maintenance'].search_count([
                ('ticket_id', '=', ticket.id),
            ]),
            1,
        )
        with self.assertRaises(UserError):
            history.write({'notes': 'Cannot edit history'})
        with self.assertRaises(UserError):
            history.repair_part_ids.write({'quantity': 2})

    def test_close_validates_result_outcome_parts_and_replacement(self):
        support = self._create_repair_user(
            'validation', 'buz_it_helpdesk.group_it_support_agent',
        )
        employee = self.env['hr.employee'].create({
            'name': 'Repair Validation Employee',
            'company_id': self.company.id,
            'user_id': support.id,
        })
        asset = self._create_repair_asset(
            'VALIDATION', employee=employee, state='assigned',
        )
        replacement = self._create_repair_asset('REPLACEMENT')
        ticket = self._create_in_progress_repair_ticket(support, asset)

        with self.assertRaises(UserError):
            ticket.action_close_ticket()
        ticket.write({'repair_result': 'Checked and tested.'})
        with self.assertRaises(UserError):
            ticket.action_close_ticket()
        ticket.write({'repair_outcome_id': self.outcome_parts_replaced.id})
        with self.assertRaises(UserError):
            ticket.action_close_ticket()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env['buz.helpdesk.ticket.repair.part'].with_user(
                support
            ).create({
                'ticket_id': ticket.id,
                'name': 'Invalid part',
                'quantity': 0,
            })
        ticket.write({
            'repair_outcome_id': self.outcome_asset_replaced.id,
            'repair_part_ids': [fields.Command.clear()],
        })
        with self.assertRaises(UserError):
            ticket.action_close_ticket()
        with self.assertRaises(ValidationError):
            ticket.write({'replacement_asset_id': asset.id})
        ticket.write({'replacement_asset_id': replacement.id})

        other_company = self.env['res.company'].create({
            'name': 'Repair Other Company',
        })
        support.write({
            'company_ids': [fields.Command.link(other_company.id)],
        })
        other_asset = self.env['buz.it.asset'].with_company(
            other_company
        ).create({
            'name': 'Other Company Replacement',
            'type_id': self.asset_type.id,
            'serial_number': 'SN-REPAIR-OTHER-COMPANY',
            'company_id': other_company.id,
        })
        with self.assertRaises(ValidationError):
            ticket.write({'replacement_asset_id': other_asset.id})

    def test_asset_replacement_does_not_transfer_assignment(self):
        support = self._create_repair_user(
            'replacement', 'buz_it_helpdesk.group_it_support_agent',
        )
        employee = self.env['hr.employee'].create({
            'name': 'Original Asset Employee',
            'company_id': self.company.id,
            'user_id': support.id,
        })
        replacement_employee = self.env['hr.employee'].create({
            'name': 'Replacement Asset Employee',
            'company_id': self.company.id,
        })
        asset = self._create_repair_asset(
            'ORIGINAL', employee=employee, state='assigned',
        )
        replacement = self._create_repair_asset(
            'NEW-ASSET', employee=replacement_employee, state='assigned',
        )
        old_assignment = (
            asset.assigned_employee_id,
            asset.responsible_department_id,
            asset.location_id,
        )
        new_assignment = (
            replacement.assigned_employee_id,
            replacement.responsible_department_id,
            replacement.location_id,
        )
        ticket = self._create_in_progress_repair_ticket(support, asset)
        ticket.write({
            'repair_result': 'Replaced the registered device.',
            'repair_outcome_id': self.outcome_asset_replaced.id,
            'replacement_asset_id': replacement.id,
        })
        ticket.action_close_ticket()

        self.assertEqual(
            (
                asset.assigned_employee_id,
                asset.responsible_department_id,
                asset.location_id,
            ),
            old_assignment,
        )
        self.assertEqual(
            (
                replacement.assigned_employee_id,
                replacement.responsible_department_id,
                replacement.location_id,
            ),
            new_assignment,
        )
        self.assertEqual(
            asset.maintenance_ids.replacement_asset_id,
            replacement,
        )

    def test_retirement_requires_manager_approval(self):
        support = self._create_repair_user(
            'retire_agent', 'buz_it_helpdesk.group_it_support_agent',
        )
        manager = self._create_repair_user(
            'retire_manager', 'buz_it_helpdesk.group_it_helpdesk_manager',
        )
        employee = self.env['hr.employee'].create({
            'name': 'Retirement Asset Employee',
            'company_id': self.company.id,
            'user_id': support.id,
        })
        asset = self._create_repair_asset(
            'RETIRE', employee=employee, state='assigned',
        )
        ticket = self._create_in_progress_repair_ticket(support, asset)
        ticket.write({
            'repair_result': 'Repair is not economically viable.',
            'repair_outcome_id': self.outcome_retired.id,
            'retire_reason': 'uneconomical',
        })
        with self.assertRaises(UserError):
            ticket.action_close_ticket()
        with self.assertRaises(UserError):
            ticket.write({'retire_proposed': True})
        ticket.action_propose_retirement()
        with self.assertRaises(UserError):
            ticket.action_close_ticket()

        ticket.with_user(manager).action_approve_retirement()
        ticket.with_user(manager).action_close_ticket()
        self.assertEqual(asset.state, 'retired')
        self.assertEqual(
            asset.maintenance_ids.repair_outcome_id,
            'retired',
        )
        with self.assertRaises(UserError):
            ticket.with_user(manager).write({
                'repair_result': 'Closed history must remain unchanged.',
            })

    def test_requester_cannot_edit_internal_repair_data(self):
        requester = self._create_repair_user(
            'requester', 'buz_it_helpdesk.group_it_requester',
        )
        employee = self.env['hr.employee'].create({
            'name': 'Repair Requester Employee',
            'company_id': self.company.id,
            'user_id': requester.id,
        })
        asset = self._create_repair_asset(
            'REQUESTER', employee=employee, state='assigned',
        )
        ticket = self.env['buz.helpdesk.ticket'].with_user(requester).create({
            'subject': 'Requester security ticket',
            'asset_id': asset.id,
            'category_id': self.helpdesk_category.id,
            'category_type_id': self.helpdesk_type.id,
            'description': 'Screen is blank',
        })
        with self.assertRaises(UserError):
            self.env['buz.helpdesk.ticket'].with_user(requester).create({
                'subject': 'Unauthorized repair details',
                'asset_id': asset.id,
                'category_id': self.helpdesk_category.id,
                'category_type_id': self.helpdesk_type.id,
                'description': 'Requester supplied internal fields',
                'diagnosis': 'Requester must not set this.',
            })
        with self.assertRaises(UserError):
            ticket.write({'diagnosis': 'Requester must not set this.'})
        with self.assertRaises(UserError):
            self.env['buz.helpdesk.ticket.repair.part'].with_user(
                requester
            ).create({
                'ticket_id': ticket.id,
                'name': 'Unauthorized part',
                'quantity': 1,
            })
        ticket_fields = self.env['buz.helpdesk.ticket'].with_user(
            requester
        ).fields_get()
        self.assertNotIn('diagnosis', ticket_fields)
        self.assertNotIn('external_cost', ticket_fields)
        self.assertIn('repair_outcome_id', ticket_fields)
        self.assertIn('repair_result', ticket_fields)
        maintenance_fields = self.env['buz.it.asset.maintenance'].with_user(
            requester
        ).fields_get()
        self.assertNotIn('cost', maintenance_fields)
        self.assertNotIn('diagnosis', maintenance_fields)
        self.assertIn('repair_outcome_id', maintenance_fields)

    def test_legacy_repair_data_is_preserved_without_outcome_inference(self):
        support = self._create_repair_user(
            'legacy', 'buz_it_helpdesk.group_it_support_agent',
        )
        employee = self.env['hr.employee'].create({
            'name': 'Legacy Repair Employee',
            'company_id': self.company.id,
            'user_id': support.id,
        })
        asset = self._create_repair_asset(
            'LEGACY', employee=employee, state='assigned',
        )
        ticket = self._create_in_progress_repair_ticket(support, asset)
        ticket.write({
            'repair_route': 'external_it',
            'repair_substate': 'sent_external',
            'external_reference': 'LEGACY-REF-001',
        })
        self.assertFalse(ticket.repair_outcome_id)
        self.assertTrue(ticket.has_legacy_repair_data)
        self.assertEqual(ticket.repair_route, 'external_it')
        self.assertEqual(ticket.repair_substate, 'sent_external')
        self.assertEqual(asset.state, 'assigned')
        with self.assertRaises(UserError):
            ticket.action_close_ticket()
    def test_completed_maintenance_requires_valid_date(self):
        asset = self.env['buz.it.asset'].create({
            'name': 'Maintenance Date Asset',
            'type_id': self.asset_type.id,
            'serial_number': 'SN-REPAIR-DATE-001',
        })
        with self.assertRaises(UserError):
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
            'responsible_department_id': self.department.id,
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
        type_a = self.env['buz.it.asset.type'].create({
            'name': 'Laptop', 'asset_prefix': 'ITTA', 'category_id': category_a.id,
        })
        type_b = self.env['buz.it.asset.type'].create({
            'name': 'Laptop', 'asset_prefix': 'ITTBX', 'category_id': category_b.id,
        })

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

        self.assertEqual(first.asset_tag, 'ITTA/2026/08/0001')
        self.assertEqual(second.asset_tag, 'ITTA/2026/08/0002')
        self.assertEqual(next_month.asset_tag, 'ITTA/2026/09/0003')
        self.assertEqual(other_company.asset_tag, 'ITTBX/2026/08/0001')
        self.assertEqual(next_year.asset_tag, 'ITTA/2027/01/0001')
        sequences = self.env['ir.sequence'].search([
            ('code', 'in', (f'buz.it.asset.type.{type_a.id}', f'buz.it.asset.type.{type_b.id}')),
            ('company_id', 'in', (company_a.id, company_b.id)),
        ])
        self.assertEqual(len(sequences), 4)
        self.assertTrue(all(sequences.mapped('use_date_range')))

    def test_asset_tag_date_range_race_is_retryable(self):
        sequence = self.company._ensure_it_asset_sequence(self.asset_type)
        with self.assertRaises(SerializationFailure):
            with self.env.cr.savepoint():
                with patch.object(
                    type(sequence),
                    '_next',
                    side_effect=UniqueViolation(),
                ):
                    self.company._next_it_asset_tag(self.asset_type, date(2026, 8, 1))

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
            'software_type': self.software_type.id,
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
            'software_type': self.software_type.id,
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
        license_model = self.env['buz.it.software.license']

        requester_fields = license_model.with_user(requester).fields_get(
            ['license_key', 'cost', 'purchase_document_file'],
        )
        support_fields = license_model.with_user(support).fields_get(
            ['license_key', 'cost', 'purchase_document_file'],
        )
        self.assertNotIn('license_key', requester_fields)
        self.assertNotIn('cost', requester_fields)
        self.assertNotIn('purchase_document_file', requester_fields)
        self.assertIn('license_key', support_fields)
        self.assertIn('cost', support_fields)
        self.assertIn('purchase_document_file', support_fields)

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
        self.assertFalse(
            maintenance_model.with_user(support).check_access_rights(
                'create', raise_exception=False,
            ),
        )
        self.assertFalse(
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
            'name': 'Office', 'software_type': self.software_type.id,
            'company_id': self.company.id,
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
            'name': 'VPN Client', 'software_type': self.software_type.id,
            'company_id': self.company.id,
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
