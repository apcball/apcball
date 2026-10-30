# -*- coding: utf-8 -*-
from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestAssetRegistration(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.category = cls.env['buz.asset.category'].create({
            'name': 'Equipment',
            'company_id': cls.company.id,
            'useful_life_months': 60,
        })
        # skip_partner_required_fields: honored by buz_partner_required_fields when installed, ignored otherwise.
        Users = cls.env['res.users'].with_context(
            no_reset_password=True, skip_partner_required_fields=True)
        cls.officer = Users.create({
            'name': 'Asset Officer', 'login': 'buz_asset_officer',
            'groups_id': [Command.set([
                cls.env.ref('base.group_user').id,
                cls.env.ref('buz_asset_management.group_asset_officer').id])],
        })
        cls.manager = Users.create({
            'name': 'Asset Manager', 'login': 'buz_asset_manager',
            'groups_id': [Command.set([
                cls.env.ref('base.group_user').id,
                cls.env.ref('buz_asset_management.group_asset_manager').id])],
        })

    def _other_company(self, name):
        # MOG_DEV has orphaned NOT NULL columns on res_company (e.g. po_lead)
        # that make company creation fail; skip rather than hide it as a pass.
        try:
            with mute_logger('odoo.sql_db'), self.cr.savepoint():
                return self.env['res.company'].with_context(
                    skip_partner_required_fields=True).create({'name': name})
        except IntegrityError:
            self.skipTest("Cannot create a second company on this database.")

    def _asset(self, **kw):
        vals = {
            'name': 'Laptop', 'category_id': self.category.id,
            'gross_cost': 1000.0, 'residual_value': 100.0, 'useful_life_months': 36,
        }
        vals.update(kw)
        return self.env['buz.asset'].create(vals)

    def test_code_generated_and_unique(self):
        a, b = self._asset(), self._asset()
        self.assertTrue(a.code and a.code != '/')
        self.assertNotEqual(a.code, b.code)

    def test_depreciable_base(self):
        self.assertEqual(self._asset().depreciable_base, 900.0)

    def test_residual_above_gross_rejected(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self._asset(gross_cost=100.0, residual_value=200.0)

    def test_useful_life_required_when_depreciable(self):
        with self.assertRaises(ValidationError):
            self._asset(useful_life_months=0)

    def test_parent_cycle_rejected(self):
        parent = self._asset()
        child = self._asset(parent_asset_id=parent.id)
        with self.assertRaises(ValidationError):
            parent.parent_asset_id = child

    def test_cross_company_employee_rejected(self):
        other = self._other_company('Other Co')
        employee = self.env['hr.employee'].with_context(skip_partner_required_fields=True).create({'name': 'Emp', 'company_id': other.id})
        with self.assertRaises(UserError):
            self._asset(employee_id=employee.id)

    def test_cross_company_category_account_rejected(self):
        other = self._other_company('Other Co 2')
        account = self.env['account.account'].with_company(other).create({
            'name': 'Foreign', 'code': 'ZZ9999', 'company_id': other.id,
            'account_type': 'asset_fixed',
        })
        with self.assertRaises(UserError):
            self.category.asset_account_id = account

    def test_direct_state_write_blocked(self):
        asset = self._asset().with_user(self.officer)
        with self.assertRaises(AccessError):
            asset.write({'approval_state': 'approved'})

    def test_code_write_blocked(self):
        asset = self._asset().with_user(self.officer)
        with self.assertRaises(AccessError):
            asset.write({'code': 'HACK'})

    def test_workflow_permissions(self):
        asset = self._asset(in_service_date='2026-01-01')
        asset.with_user(self.officer).action_submit()
        self.assertEqual(asset.approval_state, 'submitted')
        with self.assertRaises(AccessError):
            asset.with_user(self.officer).action_approve()
        asset.with_user(self.manager).action_approve()
        self.assertEqual(asset.approval_state, 'approved')
        asset.with_user(self.officer).action_put_in_service()
        self.assertEqual(asset.operational_state, 'in_service')

    def test_invalid_transition_rejected(self):
        asset = self._asset()
        with self.assertRaises(UserError):
            asset.with_user(self.manager).action_approve()

    def test_non_draft_cannot_be_deleted(self):
        asset = self._asset()
        asset.with_user(self.officer).action_submit()
        with self.assertRaises(UserError):
            asset.with_user(self.manager).unlink()


class TestAssetLocation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouses = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=2)
        if not cls.warehouses:
            cls.warehouses = cls.env['stock.warehouse'].create({
                'name': 'BUZ Test WH', 'code': 'BZT1', 'company_id': cls.env.company.id})

    def test_warehouse_and_parent_selectable_from_system(self):
        wh = self.warehouses[0]
        location = self.env['buz.asset.location'].create({
            'name': 'Rack 1', 'warehouse_id': wh.id, 'parent_id': wh.lot_stock_id.id})
        self.assertIn(wh.lot_stock_id.complete_name, location.complete_name)
        self.assertTrue(location.complete_name.endswith('Rack 1'))

    def test_parent_from_other_warehouse_rejected(self):
        if len(self.warehouses) < 2:
            self.skipTest("Needs two warehouses.")
        wh, other = self.warehouses[0], self.warehouses[1]
        with self.assertRaises(ValidationError):
            self.env['buz.asset.location'].create({
                'name': 'Rack 2', 'warehouse_id': wh.id, 'parent_id': other.lot_stock_id.id})

    def test_location_without_warehouse_or_parent(self):
        location = self.env['buz.asset.location'].create({'name': 'Office'})
        self.assertEqual(location.complete_name, 'Office')
