# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase


class TestAssetAudit(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.category = cls.env['buz.asset.category'].create({
            'name': 'AudCat', 'company_id': cls.company.id, 'useful_life_months': 12})
        cls.dept = cls.env['hr.department'].create({'name': 'AudDept'})
        cls.other_dept = cls.env['hr.department'].create({'name': 'OtherDept'})
        Emp = cls.env['hr.employee'].with_context(skip_partner_required_fields=True)
        cls.emp_a, cls.emp_b = Emp.create({'name': 'AEmp'}), Emp.create({'name': 'BEmp'})
        Loc = cls.env['buz.asset.location']
        cls.loc_a, cls.loc_b = Loc.create({'name': 'ALoc'}), Loc.create({'name': 'BLoc'})
        Users = cls.env['res.users'].with_context(no_reset_password=True, skip_partner_required_fields=True)
        base = cls.env.ref('base.group_user').id

        def user(login, group):
            return Users.create({'name': login, 'login': login,
                                 'groups_id': [Command.set([base, cls.env.ref(group).id])]})
        cls.officer = user('buz_aud_officer', 'buz_asset_management.group_asset_officer')
        cls.manager = user('buz_aud_manager', 'buz_asset_management.group_asset_manager')
        cls.viewer = user('buz_aud_viewer', 'buz_asset_management.group_asset_user')
        cls.a1 = cls._asset(cls, 'Asset 1')
        cls.a2 = cls._asset(cls, 'Asset 2')
        cls.outside = cls._asset(cls, 'Outside', department_id=cls.other_dept.id)

    def _asset(self, name, **kw):
        vals = {'name': name, 'category_id': self.category.id, 'gross_cost': 100.0, 'useful_life_months': 12,
                'employee_id': self.emp_a.id, 'department_id': self.dept.id, 'location_id': self.loc_a.id}
        vals.update(kw)
        asset = self.env['buz.asset'].create(vals)
        asset.sudo().write({'approval_state': 'approved'})
        return asset

    def _audit(self, start=True):
        audit = self.env['buz.asset.audit'].with_user(self.officer).create({
            'title': 'Q4', 'department_ids': [Command.set(self.dept.ids)]})
        if start:
            audit.with_user(self.officer).action_start()
        return audit

    def _line(self, audit, asset):
        return audit.line_ids.filtered(lambda l: l.asset_id == asset)

    def test_start_snapshots_scope_only(self):
        audit = self._audit()
        self.assertTrue(audit.name.startswith('AUD/'))
        self.assertEqual(audit.state, 'in_progress')
        assets = audit.line_ids.mapped('asset_id')
        self.assertIn(self.a1, assets)
        self.assertNotIn(self.outside, assets)
        line = self._line(audit, self.a1)
        self.assertEqual((line.expected_employee_id, line.expected_location_id), (self.emp_a, self.loc_a))
        self.assertEqual(line.result, 'not_checked')

    def test_snapshot_unchanged_after_asset_moves(self):
        audit = self._audit()
        line = self._line(audit, self.a1)
        self.a1.sudo().write({'location_id': self.loc_b.id, 'employee_id': self.emp_b.id})
        self.assertEqual(line.expected_location_id, self.loc_a)
        self.assertEqual(line.expected_employee_id, self.emp_a)

    def test_scan_results_do_not_touch_asset(self):
        audit = self._audit()
        line = self._line(audit, self.a1)
        line.write({'actual_location_id': self.loc_b.id})
        line.with_user(self.viewer).action_wrong_location()
        self.assertEqual(line.result, 'wrong_location')
        self.assertEqual(line.scanned_by_id, self.viewer)
        self.assertEqual(self.a1.location_id, self.loc_a)   # observation never overwrites the asset
        self.assertEqual(line.expected_location_id, self.loc_a)

    def test_found_copies_expected_as_actual(self):
        audit = self._audit()
        line = self._line(audit, self.a1)
        line.with_user(self.viewer).action_found()
        self.assertEqual((line.actual_location_id, line.actual_employee_id), (self.loc_a, self.emp_a))

    def test_wrong_location_requires_different_actual(self):
        audit = self._audit()
        line = self._line(audit, self.a1)
        with self.assertRaises(UserError):
            line.with_user(self.viewer).action_wrong_location()
        line.actual_location_id = self.loc_a
        with self.assertRaises(UserError):
            line.with_user(self.viewer).action_wrong_location()
        with self.assertRaises(UserError):
            line.with_user(self.viewer).action_wrong_custodian()

    def test_permissions(self):
        audit = self._audit(start=False)
        with self.assertRaises(AccessError):
            audit.with_user(self.viewer).action_start()
        with self.assertRaises(AccessError):
            self.env['buz.asset.audit'].with_user(self.viewer).create({'title': 'x'})
        audit.with_user(self.officer).action_start()
        line = self._line(audit, self.a1)
        with self.assertRaises(AccessError):
            line.with_user(self.viewer).write({'result': 'found'})
        with self.assertRaises(AccessError):
            line.with_user(self.viewer).write({'expected_location_id': self.loc_b.id})
        with self.assertRaises(AccessError):
            line.with_user(self.viewer).write({'resolution': 'accepted'})
        with self.assertRaises(AccessError):
            audit.with_user(self.officer).action_close()
        with self.assertRaises(AccessError):
            audit.with_user(self.officer).write({'state': 'closed'})

    def test_scope_frozen_after_start_and_empty_scope_rejected(self):
        audit = self._audit()
        with self.assertRaises(UserError):
            audit.with_user(self.officer).write({'department_ids': [Command.clear()]})
        empty = self.env['buz.asset.audit'].with_user(self.officer).create({
            'title': 'none', 'department_ids': [Command.set(self.env['hr.department'].create({'name': 'Empty'}).ids)]})
        with self.assertRaises(UserError):
            empty.with_user(self.officer).action_start()

    def test_close_needs_all_checked_and_exceptions_resolved(self):
        audit = self._audit()
        with self.assertRaises(UserError):
            audit.with_user(self.manager).action_close()  # nothing checked
        for line in audit.line_ids:
            line.with_user(self.viewer).action_found()
        bad = self._line(audit, self.a1)
        bad.with_user(self.viewer).action_not_found()
        self.assertEqual(audit.exception_count, 1)
        self.assertEqual(audit.unresolved_count, 1)
        with self.assertRaises(UserError):
            audit.with_user(self.manager).action_close()
        bad.with_user(self.officer).write({'resolution': 'investigating', 'resolution_note': 'ตามหา'})
        self.assertEqual(audit.unresolved_count, 0)
        audit.with_user(self.manager).action_close()
        self.assertEqual(audit.state, 'closed')
        with self.assertRaises(UserError):
            bad.with_user(self.viewer).action_found()  # closed campaign is read-only

    def test_completion_rate(self):
        audit = self._audit()
        total = len(audit.line_ids)
        self._line(audit, self.a1).with_user(self.viewer).action_found()
        self.assertAlmostEqual(audit.completion_rate, 100.0 / total, places=4)

    def test_create_transfer_from_wrong_location(self):
        audit = self._audit()
        line = self._line(audit, self.a1)
        line.write({'actual_location_id': self.loc_b.id})
        line.with_user(self.viewer).action_wrong_location()
        action = line.with_user(self.officer).action_create_transfer()
        self.assertEqual(action['context']['default_to_location_id'], self.loc_b.id)
        with self.assertRaises(AccessError):
            line.with_user(self.viewer).action_create_transfer()
        other = self._line(audit, self.a2)
        other.with_user(self.viewer).action_found()
        with self.assertRaises(UserError):
            other.with_user(self.officer).action_create_transfer()

    def test_scan_wizard_finds_by_code_serial_and_qr(self):
        audit = self._audit()
        self.a1.serial_number = 'SN-AUD-1'
        Wiz = self.env['buz.asset.audit.scan.wizard']
        line = self._line(audit, self.a1)
        for code in (self.a1.code, 'SN-AUD-1', self.a1._qr_payload(), self.a1.qr_token):
            action = Wiz.create({'audit_id': audit.id, 'code': code}).action_find()
            self.assertEqual(action['res_id'], line.id, code)
        with self.assertRaises(UserError):
            Wiz.create({'audit_id': audit.id, 'code': self.outside.code}).action_find()

    def test_qr_payload_has_no_accounting_data_and_needs_authorization(self):
        payload = self.a1._qr_payload()
        self.assertIn('/buz_asset/qr/' + self.a1.qr_token, payload)
        self.assertNotIn(str(self.a1.gross_cost), payload)
        Asset = self.env['buz.asset']
        # Authorized officer: asset form (or pending audit line).
        url = Asset.with_user(self.officer)._qr_target_url(self.a1.qr_token)
        self.assertIn('model=buz.asset', url)
        self.assertFalse(Asset.with_user(self.officer)._qr_target_url('does-not-exist'))
        # A user without any asset group cannot read the asset: same answer as unknown token.
        nobody = self.env['res.users'].with_context(no_reset_password=True, skip_partner_required_fields=True).create({
            'name': 'nobody', 'login': 'buz_aud_nobody',
            'groups_id': [Command.set([self.env.ref('base.group_user').id])]})
        self.assertFalse(Asset.with_user(nobody)._qr_target_url(self.a1.qr_token))

    def test_qr_scan_lands_on_pending_audit_line(self):
        audit = self._audit()
        line = self._line(audit, self.a1)
        url = self.env['buz.asset'].with_user(self.viewer)._qr_target_url(self.a1.qr_token)
        self.assertIn('model=buz.asset.audit.line', url)
        self.assertIn('id=%s' % line.id, url)
        line.with_user(self.viewer).action_found()
        url = self.env['buz.asset'].with_user(self.viewer)._qr_target_url(self.a1.qr_token)
        self.assertIn('model=buz.asset&', url + '&')

    def test_label_report_renders_qr(self):
        report = self.env.ref('buz_asset_management.action_report_asset_label')
        html = report.with_user(self.officer)._render_qweb_html(report.report_name, self.a1.ids)[0].decode()
        self.assertIn(self.a1.code, html)
        self.assertIn('/report/barcode/', html)
