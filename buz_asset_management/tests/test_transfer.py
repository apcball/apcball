# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestAssetTransfer(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.category = cls.env['buz.asset.category'].create({
            'name': 'Equip', 'company_id': cls.company.id, 'useful_life_months': 12})
        Dept, Loc = cls.env['hr.department'], cls.env['buz.asset.location']
        Emp = cls.env['hr.employee'].with_context(skip_partner_required_fields=True)
        cls.dept_a, cls.dept_b = Dept.create({'name': 'Dept A'}), Dept.create({'name': 'Dept B'})
        cls.emp_a, cls.emp_b = Emp.create({'name': 'Emp A'}), Emp.create({'name': 'Emp B'})
        cls.loc_a, cls.loc_b = Loc.create({'name': 'Loc A'}), Loc.create({'name': 'Loc B'})
        Users = cls.env['res.users'].with_context(no_reset_password=True, skip_partner_required_fields=True)
        base = cls.env.ref('base.group_user').id

        def user(login, group):
            return Users.create({'name': login, 'login': login,
                                 'groups_id': [Command.set([base, cls.env.ref(group).id])]})
        cls.officer = user('buz_trf_officer', 'buz_asset_management.group_asset_officer')
        cls.manager = user('buz_trf_manager', 'buz_asset_management.group_asset_manager')
        cls.viewer = user('buz_trf_viewer', 'buz_asset_management.group_asset_user')

    def _asset(self, approved=True, **kw):
        vals = {'name': 'Laptop', 'category_id': self.category.id, 'gross_cost': 1200.0,
                'useful_life_months': 12, 'employee_id': self.emp_a.id,
                'department_id': self.dept_a.id, 'location_id': self.loc_a.id}
        vals.update(kw)
        asset = self.env['buz.asset'].create(vals)
        if approved:
            asset.sudo().write({'approval_state': 'approved'})
        return asset

    def _transfer(self, asset, **kw):
        vals = {'asset_id': asset.id, 'reason': 'test', 'to_employee_id': self.emp_b.id,
                'to_department_id': self.dept_b.id, 'to_location_id': self.loc_b.id}
        vals.update(kw)
        return self.env['buz.asset.transfer'].with_user(self.officer).create(vals)

    def _run(self, transfer):
        transfer.with_user(self.officer).action_submit()
        transfer.with_user(self.manager).action_approve()
        transfer.with_user(self.officer).action_done()

    def test_full_flow_updates_asset_and_keeps_history(self):
        asset = self._asset()
        transfer = self._transfer(asset)
        self.assertTrue(transfer.name.startswith('TRF/'))
        self.assertEqual(transfer.from_employee_id, self.emp_a)
        self._run(transfer)
        self.assertEqual(transfer.state, 'done')
        self.assertEqual((asset.employee_id, asset.department_id, asset.location_id),
                         (self.emp_b, self.dept_b, self.loc_b))
        # Snapshot of the previous custody is preserved.
        self.assertEqual((transfer.from_employee_id, transfer.from_department_id, transfer.from_location_id),
                         (self.emp_a, self.dept_a, self.loc_a))
        self.assertEqual(transfer.approver_id, self.manager)
        self.assertEqual(transfer.completer_id, self.officer)
        self.assertEqual(asset.transfer_ids, transfer)

    def test_partial_change_only_location(self):
        asset = self._asset()
        transfer = self._transfer(asset, to_employee_id=self.emp_a.id, to_department_id=self.dept_a.id)
        self._run(transfer)
        self.assertEqual(asset.employee_id, self.emp_a)
        self.assertEqual(asset.location_id, self.loc_b)

    def test_no_change_rejected(self):
        asset = self._asset()
        transfer = self._transfer(asset, to_employee_id=self.emp_a.id, to_department_id=self.dept_a.id,
                                  to_location_id=self.loc_a.id)
        with self.assertRaises(UserError):
            transfer.with_user(self.officer).action_submit()

    def test_direct_custody_edit_blocked_on_approved_asset_only(self):
        approved, draft = self._asset(), self._asset(approved=False)
        with self.assertRaises(UserError):
            approved.with_user(self.officer).write({'location_id': self.loc_b.id})
        draft.with_user(self.officer).write({'location_id': self.loc_b.id})
        self.assertEqual(draft.location_id, self.loc_b)
        # Unchanged value is not an edit.
        approved.with_user(self.officer).write({'location_id': self.loc_a.id})

    def test_permissions(self):
        asset = self._asset()
        with self.assertRaises(AccessError):
            self.env['buz.asset.transfer'].with_user(self.viewer).create({
                'asset_id': asset.id, 'reason': 'x', 'to_location_id': self.loc_b.id})
        transfer = self._transfer(asset)
        transfer.with_user(self.officer).action_submit()
        with self.assertRaises(AccessError):
            transfer.with_user(self.officer).action_approve()
        with self.assertRaises(AccessError):
            transfer.with_user(self.officer).write({'state': 'done'})
        with self.assertRaises(UserError):
            transfer.with_user(self.officer).action_done()  # not approved yet

    def test_overlapping_open_transfer_rejected(self):
        asset = self._asset()
        self._transfer(asset)
        with self.assertRaises(ValidationError):
            self._transfer(asset, to_location_id=self.loc_a.id)

    def test_stale_snapshot_blocks_completion(self):
        asset = self._asset()
        transfer = self._transfer(asset)
        transfer.with_user(self.officer).action_submit()
        transfer.with_user(self.manager).action_approve()
        asset.sudo().write({'location_id': self.loc_b.id})  # moved behind the request's back
        with self.assertRaises(UserError):
            transfer.with_user(self.officer).action_done()
        self.assertEqual(transfer.state, 'approved')

    def test_done_transfer_is_immutable(self):
        transfer = self._transfer(self._asset())
        self._run(transfer)
        with self.assertRaises(UserError):
            transfer.with_user(self.officer).write({'reason': 'edit'})
        with self.assertRaises(UserError):
            transfer.with_user(self.manager).unlink()
        with self.assertRaises(UserError):
            transfer.with_user(self.officer).action_cancel()

    def test_not_approved_or_disposed_asset_rejected(self):
        transfer = self._transfer(self._asset(approved=False))
        with self.assertRaises(UserError):
            transfer.with_user(self.officer).action_submit()
        asset = self._asset()
        asset.sudo().write({'operational_state': 'disposed'})
        transfer = self._transfer(asset)
        with self.assertRaises(UserError):
            transfer.with_user(self.officer).action_submit()

    def test_reject_then_reopen_and_cancel_frees_asset(self):
        asset = self._asset()
        transfer = self._transfer(asset)
        transfer.with_user(self.officer).action_submit()
        transfer.with_user(self.manager).action_reject()
        self.assertEqual(transfer.state, 'rejected')
        transfer.with_user(self.manager).action_reset_to_draft()
        self.assertEqual(transfer.state, 'draft')
        transfer.with_user(self.officer).action_cancel()
        self._transfer(asset)  # no longer blocked by the cancelled one

    def test_acknowledge_records_user_once(self):
        transfer = self._transfer(self._asset())
        transfer.with_user(self.officer).action_submit()
        transfer.with_user(self.manager).action_approve()
        transfer.with_user(self.viewer).action_acknowledge()
        self.assertEqual(transfer.acknowledged_by_id, self.viewer)
        transfer.with_user(self.manager).action_acknowledge()
        self.assertEqual(transfer.acknowledged_by_id, self.viewer)
