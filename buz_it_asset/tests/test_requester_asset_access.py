from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestRequesterAssetAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.requester_group = cls.env.ref('buz_it_helpdesk.group_it_requester')
        cls.support_group = cls.env.ref('buz_it_helpdesk.group_it_support_agent')
        cls.requester = cls.env['res.users'].create({
            'name': 'Requester Asset Access Test',
            'login': 'requester_asset_access_test',
            'company_id': cls.company.id,
            'company_ids': [Command.link(cls.company.id)],
            'groups_id': [Command.set([
                cls.env.ref('base.group_user').id,
                cls.requester_group.id,
            ])],
        })
        cls.other_user = cls.env['res.users'].create({
            'name': 'Other Asset Access Test',
            'login': 'other_asset_access_test',
            'company_id': cls.company.id,
            'company_ids': [Command.link(cls.company.id)],
            'groups_id': [Command.set([
                cls.env.ref('base.group_user').id,
                cls.requester_group.id,
            ])],
        })
        cls.support = cls.env['res.users'].create({
            'name': 'Support Asset Access Test',
            'login': 'support_asset_access_test',
            'company_id': cls.company.id,
            'company_ids': [Command.link(cls.company.id)],
            'groups_id': [Command.set([
                cls.env.ref('base.group_user').id,
                cls.support_group.id,
            ])],
        })
        cls.requester_employee = cls.env['hr.employee'].create({
            'name': 'Requester Asset Employee',
            'user_id': cls.requester.id,
            'company_id': cls.company.id,
        })
        cls.other_employee = cls.env['hr.employee'].create({
            'name': 'Other Asset Employee',
            'user_id': cls.other_user.id,
            'company_id': cls.company.id,
        })
        cls.asset_type = cls.env.ref('buz_it_asset.type_desktop_pc')
        cls.category = cls.env['buz.helpdesk.category'].create({
            'name': 'Requester Asset Test Category',
        })
        cls.category_type = cls.env['buz.helpdesk.category.type'].create({
            'name': cls.asset_type.name,
            'category_id': cls.category.id,
        })

    def _create_asset(self, name, employee):
        return self.env['buz.it.asset'].create({
            'name': name,
            'asset_tag': 'TEST-' + name.replace(' ', '-'),
            'type_id': self.asset_type.id,
            'company_id': self.company.id,
            'assigned_employee_id': employee.id,
        })

    def _new_ticket(self, user):
        return self.env['buz.helpdesk.ticket'].with_user(user).new({
            'requester_id': user.id,
            'company_id': self.company.id,
            'category_id': self.category.id,
            'category_type_id': self.category_type.id,
        })

    def test_requester_asset_domain_contains_only_own_asset(self):
        own_asset = self._create_asset('Requester Own Asset', self.requester_employee)
        other_asset = self._create_asset('Other User Asset', self.other_employee)

        ticket = self._new_ticket(self.requester)
        ticket._compute_requester_asset_ids()

        self.assertIn(own_asset.id, ticket.requester_asset_ids.ids)
        self.assertNotIn(other_asset.id, ticket.requester_asset_ids.ids)

    def test_requester_cannot_select_other_users_asset(self):
        other_asset = self._create_asset('Other User Asset Validation', self.other_employee)
        ticket = self._new_ticket(self.requester)

        with self.assertRaises(ValidationError):
            ticket._check_asset_selection(other_asset)

    def test_requester_can_create_ticket_without_asset(self):
        ticket = self.env['buz.helpdesk.ticket'].with_user(self.requester).create({
            'subject': 'Requester without assigned asset',
            'category_id': self.category.id,
            'category_type_id': self.category_type.id,
        })

        self.assertFalse(ticket.asset_id)

    def test_replacement_asset_field_is_hidden_from_requester(self):
        requester_fields = self.env['buz.helpdesk.ticket'].with_user(self.requester).fields_get([
            'replacement_asset_id',
        ])
        support_fields = self.env['buz.helpdesk.ticket'].with_user(self.support).fields_get([
            'replacement_asset_id',
        ])

        self.assertNotIn('replacement_asset_id', requester_fields)
        self.assertIn('replacement_asset_id', support_fields)

    def test_requester_cannot_read_replacement_asset_field(self):
        ticket = self.env['buz.helpdesk.ticket'].with_user(self.support).create({
            'subject': 'Replacement field access check',
            'category_id': self.category.id,
            'category_type_id': self.category_type.id,
        })

        with self.assertRaises(AccessError):
            ticket.with_user(self.requester).read(['replacement_asset_id'])