# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase


class TestDepreciationPosting(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Account = cls.env['account.account']
        cls.expense = Account.create({
            'code': 'BUZEXP1', 'name': 'Depreciation expense', 'account_type': 'expense',
            'company_id': cls.company.id})
        cls.accum = Account.create({
            'code': 'BUZACC1', 'name': 'Accumulated depreciation', 'account_type': 'asset_non_current',
            'company_id': cls.company.id})
        cls.fixed = Account.create({
            'code': 'BUZFA1', 'name': 'Fixed assets', 'account_type': 'asset_fixed',
            'company_id': cls.company.id})
        cls.journal = cls.env['account.journal'].create({
            'name': 'Asset depreciation', 'code': 'BZAD', 'type': 'general',
            'company_id': cls.company.id})
        cls.category = cls.env['buz.asset.category'].create({
            'name': 'Equipment', 'company_id': cls.company.id, 'useful_life_months': 12,
            'asset_account_id': cls.fixed.id, 'depreciation_account_id': cls.accum.id,
            'expense_account_id': cls.expense.id, 'journal_id': cls.journal.id})
        Users = cls.env['res.users'].with_context(no_reset_password=True, skip_partner_required_fields=True)
        base = [cls.env.ref('base.group_user').id, cls.env.ref('account.group_account_manager').id]
        # The date-policy module hides its policy from users without its (read-only)
        # auditor group; grant that, never the admin/override group.
        auditor = cls.env.ref('buz_accounting_date_control.group_date_auditor', raise_if_not_found=False)
        if auditor:
            base.append(auditor.id)
        cls.acc_manager = Users.create({
            'name': 'Asset Acc Manager', 'login': 'buz_asset_accmgr',
            'groups_id': [Command.set(base + [
                cls.env.ref('buz_asset_management.group_asset_accounting_manager').id])]})
        cls.asset_manager = Users.create({
            'name': 'Asset Manager X', 'login': 'buz_asset_mgrx',
            'groups_id': [Command.set(base[:1] + [
                cls.env.ref('buz_asset_management.group_asset_manager').id])]})
        cls.accountant = Users.create({
            'name': 'Asset Accountant', 'login': 'buz_asset_acct',
            'groups_id': [Command.set(base + [cls.env.ref('buz_asset_management.group_asset_accountant').id])]})

    def _running_asset(self, **kw):
        today = fields.Date.context_today(self.env['buz.asset'])
        vals = {
            'name': 'Laptop', 'category_id': self.category.id, 'gross_cost': 1300.0,
            'residual_value': 100.0, 'useful_life_months': 12,
            'in_service_date': today - relativedelta(months=2, day=1)}
        vals.update(kw)
        asset = self.env['buz.asset'].create(vals)
        asset.sudo().write({'approval_state': 'approved', 'operational_state': 'in_service'})
        asset.with_user(self.accountant).action_capitalize()
        asset.with_user(self.accountant).action_compute_schedule()
        return asset

    def _set_lock_date(self, value):
        # Test-only: the ORM refuses to lock a period holding unposted entries
        # (DEV has some); the rollback at test end discards this.
        self.env.cr.execute(
            'UPDATE res_company SET fiscalyear_lock_date = %s WHERE id = %s', (value, self.company.id))
        self.company.invalidate_recordset(['fiscalyear_lock_date'])
        self.env.registry.clear_cache()

    def _due(self, asset):
        today = fields.Date.context_today(asset)
        return asset.depreciation_line_ids.filtered(lambda l: l.depreciation_date <= today).sorted('sequence')

    def test_post_creates_balanced_move(self):
        asset = self._running_asset()
        line = self._due(asset)[0]
        line.with_user(self.acc_manager).action_post_depreciation()
        self.assertEqual(line.state, 'posted')
        move = line.move_id
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.buz_asset_line_id, line)
        debit = move.line_ids.filtered(lambda l: l.debit)
        credit = move.line_ids.filtered(lambda l: l.credit)
        self.assertEqual(debit.account_id, self.expense)
        self.assertEqual(credit.account_id, self.accum)
        self.assertEqual(debit.debit, line.planned_amount)
        self.assertEqual(credit.credit, line.planned_amount)

    def test_repeated_post_does_not_duplicate(self):
        asset = self._running_asset()
        line = self._due(asset)[0]
        line.with_user(self.acc_manager).action_post_depreciation()
        move = line.move_id
        line.with_user(self.acc_manager).action_post_depreciation()
        self.assertEqual(line.move_id, move)
        self.assertEqual(self.env['account.move'].search_count([('buz_asset_line_id', '=', line.id)]), 1)

    def test_must_post_in_order(self):
        asset = self._running_asset()
        due = self._due(asset)
        self.assertGreaterEqual(len(due), 2)
        with self.assertRaises(UserError):
            due[1].with_user(self.acc_manager).action_post_depreciation()

    def test_future_period_rejected(self):
        asset = self._running_asset()
        today = fields.Date.context_today(asset)
        future = asset.depreciation_line_ids.filtered(lambda l: l.depreciation_date > today)[:1]
        # Earlier lines unposted trip the order check first; either way it must not post.
        with self.assertRaises(UserError):
            future.with_user(self.acc_manager).action_post_depreciation()
        self.assertFalse(future.move_id)

    def test_accountant_cannot_post_or_reverse(self):
        asset = self._running_asset()
        line = self._due(asset)[0]
        with self.assertRaises(AccessError):
            line.with_user(self.accountant).action_post_depreciation()
        line.with_user(self.acc_manager).action_post_depreciation()
        with self.assertRaises(AccessError):
            line.with_user(self.accountant).action_reverse()

    def test_not_capitalized_asset_rejected(self):
        asset = self._running_asset()
        asset.sudo().write({'accounting_state': 'not_capitalized'})
        with self.assertRaises(UserError):
            self._due(asset)[0].with_user(self.acc_manager).action_post_depreciation()

    def test_missing_category_account_rejected(self):
        asset = self._running_asset()
        self.category.expense_account_id = False
        with self.assertRaises(UserError):
            self._due(asset)[0].with_user(self.acc_manager).action_post_depreciation()

    def test_lock_date_blocks_and_marks_exception(self):
        asset = self._running_asset()
        line = self._due(asset)[0]
        self._set_lock_date(line.depreciation_date)
        line.with_user(self.acc_manager).action_post_depreciation()
        self.assertEqual(line.state, 'exception')
        self.assertFalse(line.move_id)
        self.assertTrue(line.exception_message)
        self.assertFalse(self.env['account.move'].search([('buz_asset_line_id', '=', line.id)]))
        # Unlock and retry from exception.
        self._set_lock_date(None)
        line.with_user(self.acc_manager).action_post_depreciation()
        self.assertEqual(line.state, 'posted')

    def test_reversal_keeps_original_and_links(self):
        asset = self._running_asset()
        line = self._due(asset)[0]
        line.with_user(self.acc_manager).action_post_depreciation()
        original = line.move_id
        line.with_user(self.acc_manager).action_reverse(reason='test')
        self.assertEqual(line.state, 'reversed')
        self.assertEqual(line.move_id, original)
        self.assertEqual(original.state, 'posted')
        self.assertTrue(line.reversal_move_id)
        self.assertEqual(line.reversal_move_id.reversed_entry_id, original)
        # Second reverse is a no-op.
        line.with_user(self.acc_manager).action_reverse(reason='again')
        self.assertEqual(self.env['account.move'].search_count([('reversed_entry_id', '=', original.id)]), 1)

    def test_posted_move_cannot_be_reset_or_deleted(self):
        asset = self._running_asset()
        line = self._due(asset)[0]
        line.with_user(self.acc_manager).action_post_depreciation()
        with self.assertRaises(UserError):
            line.move_id.button_draft()
        with self.assertRaises(UserError):
            line.move_id.unlink()

    def test_cron_respects_company_flag_and_is_idempotent(self):
        asset = self._running_asset()
        Line = self.env['buz.asset.depreciation.line']
        self.company.buz_asset_auto_post = False
        Line._cron_post_due_lines()
        self.assertFalse(asset.depreciation_line_ids.mapped('move_id'))
        self.company.buz_asset_auto_post = True
        Line._cron_post_due_lines()
        Line._cron_post_due_lines()
        posted = asset.depreciation_line_ids.filtered('move_id')
        self.assertEqual(len(posted), len(self._due(asset)))
        self.assertEqual(len(posted.mapped('move_id')), len(posted))

    # ------------------------------------------------------------------
    # Disposal
    # ------------------------------------------------------------------
    def _disposal_setup(self, **kw):
        Account = self.env['account.account']
        self.gainloss = Account.create({
            'code': 'BUZGL%s' % Account.search_count([]), 'name': 'Gain loss on disposal', 'account_type': 'expense',
            'company_id': self.company.id})
        self.clearing = Account.create({
            'code': 'BUZCLR%s' % Account.search_count([]), 'name': 'Disposal clearing',
            'account_type': 'income_other', 'company_id': self.company.id})
        self.category.write({'gain_loss_account_id': self.gainloss.id,
                             'disposal_clearing_account_id': self.clearing.id})
        asset = self._running_asset()
        for line in self._due(asset):
            line.with_user(self.acc_manager).action_post_depreciation()
        vals = {'asset_id': asset.id, 'reason': 'test', 'disposal_type': 'scrap'}
        vals.update(kw)
        return asset, self.env['buz.asset.disposal'].create(vals)

    def _post_disposal(self, disposal):
        disposal.with_user(self.asset_manager).action_approve()
        disposal.with_user(self.acc_manager).action_post()

    def _balance(self, account, move):
        lines = move.line_ids.filtered(lambda l: l.account_id == account)
        return sum(lines.mapped('debit')) - sum(lines.mapped('credit'))

    def test_disposal_scrap_books_loss_and_stops_depreciation(self):
        asset, disposal = self._disposal_setup()
        accumulated = sum(self._due(asset).mapped('planned_amount'))
        self._post_disposal(disposal)
        move = disposal.move_id
        self.assertEqual(disposal.state, 'posted')
        self.assertEqual(move.state, 'posted')
        self.assertEqual(sum(move.line_ids.mapped('debit')), sum(move.line_ids.mapped('credit')))
        self.assertEqual(self._balance(self.fixed, move), -1300.0)
        self.assertEqual(self._balance(self.accum, move), accumulated)
        self.assertEqual(self._balance(self.gainloss, move), 1300.0 - accumulated)
        self.assertEqual(disposal.gain_loss, accumulated - 1300.0)
        self.assertEqual(asset.operational_state, 'disposed')
        self.assertEqual(asset.accounting_state, 'disposed')
        self.assertFalse(asset.depreciation_line_ids.filtered(lambda l: l.state in ('planned', 'exception')))
        # No further depreciation posts after disposal.
        cancelled = asset.depreciation_line_ids.filtered(lambda l: l.state == 'cancelled')
        self.assertTrue(cancelled)
        with self.assertRaises(UserError):
            cancelled[:1].with_user(self.acc_manager).action_post_depreciation()

    def test_disposal_sale_proceeds_counted_once(self):
        partner = self.env['res.partner'].with_context(skip_partner_required_fields=True).create({'name': 'Buyer'})
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': partner.id,
            'invoice_date': fields.Date.context_today(self.env['buz.asset']),
            'invoice_line_ids': [Command.create({
                'name': 'Asset sale', 'quantity': 1, 'price_unit': 500.0,
                'account_id': self.env['account.account'].create({
                    'code': 'BUZCLR1', 'name': 'Disposal clearing', 'account_type': 'income_other',
                    'company_id': self.company.id}).id, 'tax_ids': [Command.clear()]})]})
        clearing = invoice.invoice_line_ids.account_id
        invoice.action_post()
        self.category.write({'disposal_clearing_account_id': clearing.id})
        self.gainloss = self.env['account.account'].create({
            'code': 'BUZGL2', 'name': 'Gain loss', 'account_type': 'expense', 'company_id': self.company.id})
        self.category.gain_loss_account_id = self.gainloss
        asset = self._running_asset()
        for line in self._due(asset):
            line.with_user(self.acc_manager).action_post_depreciation()
        disposal = self.env['buz.asset.disposal'].create({
            'asset_id': asset.id, 'reason': 'sold', 'disposal_type': 'sale', 'sale_move_id': invoice.id})
        accumulated = sum(self._due(asset).mapped('planned_amount'))
        self._post_disposal(disposal)
        move = disposal.move_id
        self.assertEqual(disposal.proceeds, 500.0)
        self.assertEqual(disposal.gain_loss, 500.0 - (1300.0 - accumulated))
        # Clearing: invoice credits 500, disposal entry debits 500 -> nets to zero.
        self.assertEqual(self._balance(clearing, move), 500.0)
        self.assertEqual(sum(move.line_ids.mapped('debit')), sum(move.line_ids.mapped('credit')))

    def test_disposal_blocked_until_depreciation_posted(self):
        asset = self._running_asset()
        self.category.gain_loss_account_id = self.env['account.account'].create({
            'code': 'BUZGL3', 'name': 'GL', 'account_type': 'expense', 'company_id': self.company.id})
        disposal = self.env['buz.asset.disposal'].create({'asset_id': asset.id, 'reason': 'x'})
        disposal.with_user(self.asset_manager).action_approve()
        with self.assertRaises(UserError):
            disposal.with_user(self.acc_manager).action_post()
        self.assertEqual(disposal.state, 'approved')
        self.assertFalse(disposal.move_id)

    def test_disposal_permissions_and_state_guard(self):
        asset, disposal = self._disposal_setup()
        with self.assertRaises(AccessError):
            disposal.with_user(self.accountant).action_approve()
        with self.assertRaises(UserError):
            disposal.with_user(self.acc_manager).action_post()  # not approved yet
        with self.assertRaises(AccessError):
            disposal.with_user(self.asset_manager).write({'state': 'posted'})
        disposal.with_user(self.asset_manager).action_approve()
        with self.assertRaises(AccessError):
            disposal.with_user(self.asset_manager).action_post()

    def test_disposal_repeated_post_and_duplicate_rejected(self):
        asset, disposal = self._disposal_setup()
        self._post_disposal(disposal)
        move = disposal.move_id
        disposal.with_user(self.acc_manager).action_post()
        self.assertEqual(disposal.move_id, move)
        with self.assertRaises(Exception):
            self.env['buz.asset.disposal'].create({'asset_id': asset.id, 'reason': 'again'})

    def test_disposal_lock_date_keeps_it_approved(self):
        asset, disposal = self._disposal_setup()
        disposal.with_user(self.asset_manager).action_approve()
        self._set_lock_date(disposal.disposal_date)
        with self.assertRaises(UserError):
            disposal.with_user(self.acc_manager).action_post()
        self.assertEqual(disposal.state, 'approved')
        self.assertFalse(disposal.move_id)
        self.assertEqual(asset.accounting_state, 'capitalized')

    # ------------------------------------------------------------------
    # Dashboard / reports
    # ------------------------------------------------------------------
    def test_book_value_uses_posted_lines_only(self):
        asset = self._running_asset()
        self.assertEqual(asset.accumulated_depreciation, 0.0)
        self.assertEqual(asset.book_value, 1300.0)
        line = self._due(asset)[0]
        line.with_user(self.acc_manager).action_post_depreciation()
        self.assertEqual(asset.accumulated_depreciation, line.planned_amount)
        self.assertEqual(asset.book_value, 1300.0 - line.planned_amount)
        line.with_user(self.acc_manager).action_reverse(reason='t')
        self.assertEqual(asset.accumulated_depreciation, 0.0)
        self.assertEqual(asset.book_value, 1300.0)

    def test_disposed_asset_has_zero_book_value(self):
        asset, disposal = self._disposal_setup()
        self._post_disposal(disposal)
        self.assertEqual(asset.book_value, 0.0)

    def test_dashboard_reflects_data_and_drilldowns_match(self):
        Dash = self.env['buz.asset.dashboard']
        before = Dash.create({})
        # KPI fields are computed on first read, so read the "before" values now.
        before_vals = before.read(['asset_count', 'total_cost', 'due_depreciation_count', 'book_value'])[0]
        asset = self._running_asset()
        due_count = len(self._due(asset))
        after = Dash.create({})
        self.assertEqual(after.asset_count, before_vals['asset_count'] + 1)
        self.assertAlmostEqual(after.total_cost, before_vals['total_cost'] + 1300.0, places=2)
        self.assertEqual(after.due_depreciation_count, before_vals['due_depreciation_count'] + due_count)
        self.assertAlmostEqual(after.book_value, before_vals['book_value'] + 1300.0, places=2)
        # Drill-down domains return the same counts as the tiles.
        self.assertEqual(
            self.env['buz.asset.depreciation.line'].search_count(after.action_open_due_lines()['domain']),
            after.due_depreciation_count)
        self.assertEqual(self.env['buz.asset'].search_count(after.action_open_assets()['domain']), after.asset_count)

    def test_dashboard_readable_by_asset_user_only_own_scope(self):
        user = self.env['res.users'].with_context(no_reset_password=True, skip_partner_required_fields=True).create({
            'name': 'Dash User', 'login': 'buz_dash_user',
            'groups_id': [Command.set([self.env.ref('base.group_user').id,
                                       self.env.ref('buz_asset_management.group_asset_user').id])]})
        dash = self.env['buz.asset.dashboard'].with_user(user).create({})
        self.assertGreaterEqual(dash.asset_count, 0)
        action = dash.action_open_assets()
        self.assertEqual(action['res_model'], 'buz.asset')

    def test_menu_structure(self):
        ref = self.env.ref
        for xmlid in ('menu_buz_asset_dashboard', 'menu_buz_asset', 'menu_buz_asset_category_main',
                      'menu_buz_asset_depreciation', 'menu_buz_asset_disposal', 'menu_buz_asset_reports',
                      'menu_buz_asset_configuration', 'menu_buz_report_register', 'menu_buz_report_book_value',
                      'menu_buz_report_depreciation', 'menu_buz_report_by_department',
                      'menu_buz_report_by_location', 'menu_buz_report_disposal'):
            self.assertTrue(ref('buz_asset_management.' + xmlid).exists(), xmlid)
        for action in ('action_buz_report_register', 'action_buz_report_book_value',
                       'action_buz_report_by_department', 'action_buz_report_by_location',
                       'action_buz_report_depreciation', 'action_buz_report_disposal'):
            self.assertTrue(ref('buz_asset_management.' + action).exists(), action)

    def test_depreciation_posts_while_under_maintenance(self):
        asset = self._running_asset()
        asset.sudo().write({'operational_state': 'under_maintenance'})
        line = self._due(asset)[0]
        line.with_user(self.acc_manager).action_post_depreciation()
        self.assertEqual(line.state, 'posted')

    # ------------------------------------------------------------------
    # Phase 3: reconciliation / roll-forward / ageing / forecast
    # ------------------------------------------------------------------
    def _cost_entry(self, amount=1300.0):
        """Opening-style entry that puts the asset cost into the GL (assets are register-only)."""
        offset = self.env['account.account'].create({
            'code': 'BUZOFF%s' % self.env['account.account'].search_count([]), 'name': 'Offset',
            'account_type': 'asset_current', 'company_id': self.company.id})
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.journal.id,
            'date': fields.Date.context_today(self.env['buz.asset']),
            'line_ids': [Command.create({'account_id': self.fixed.id, 'debit': amount, 'name': 'cost'}),
                         Command.create({'account_id': offset.id, 'credit': amount, 'name': 'offset'})]})
        move.action_post()
        return move

    def _recon(self, user=None, date=None):
        Wiz = self.env['buz.asset.reconcile.wizard'].with_user(user or self.accountant)
        wiz = Wiz.create({'date_to': date or fields.Date.context_today(self.env['buz.asset'])})
        wiz.action_compute()
        return wiz

    def _row(self, wiz, kind, account):
        return wiz.line_ids.filtered(lambda l: l.kind == kind and l.account_id == account)

    def test_reconciliation_matches_gl(self):
        baseline = self._recon().nbv_variance   # DEV also holds the owner's real asset
        asset = self._running_asset()
        self._cost_entry()
        due = self._due(asset)
        for line in due[:-1]:
            line.with_user(self.acc_manager).action_post_depreciation()
        wiz = self._recon()
        cost, accum = self._row(wiz, 'cost', self.fixed), self._row(wiz, 'accumulated', self.accum)
        self.assertEqual((cost.gl_balance, cost.subledger_balance, cost.variance), (1300.0, 1300.0, 0.0))
        self.assertTrue(cost.matched)
        posted = sum(due[:-1].mapped('planned_amount'))
        self.assertEqual((accum.gl_balance, accum.subledger_balance), (posted, posted))
        self.assertTrue(accum.matched)
        # The one due-but-unposted period is shown as plan, not as an accounting amount.
        self.assertEqual(accum.unposted_due, due[-1].planned_amount)
        self.assertAlmostEqual(wiz.nbv_variance, baseline, places=2)   # this asset adds no variance

    def test_reconciliation_shows_variance_and_drilldown(self):
        baseline = self._recon().nbv_variance
        asset = self._running_asset()  # no cost entry in the GL
        wiz = self._recon()
        cost = self._row(wiz, 'cost', self.fixed)
        self.assertEqual((cost.gl_balance, cost.subledger_balance, cost.variance), (0.0, 1300.0, -1300.0))
        self.assertFalse(cost.matched)
        self.assertAlmostEqual(wiz.nbv_variance, baseline - 1300.0, places=2)
        self.assertEqual(cost.action_open_assets()['domain'], [('id', 'in', asset.ids)])
        self._cost_entry()
        wiz2 = self._recon()
        gl_action = self._row(wiz2, 'cost', self.fixed).action_open_gl()
        self.assertEqual(self.env['account.move.line'].search_count(gl_action['domain']), 1)

    def test_reconciliation_after_disposal_and_reversal(self):
        asset, disposal = self._disposal_setup()
        self._cost_entry()
        due = self._due(asset)
        due[0].with_user(self.acc_manager).action_reverse(reason='t')   # reversal nets to zero on both sides
        wiz = self._recon()
        accum = self._row(wiz, 'accumulated', self.accum)
        self.assertEqual(accum.gl_balance, accum.subledger_balance)
        self.assertEqual(accum.subledger_balance, sum(due.mapped('planned_amount')) - due[0].planned_amount)
        # Reversal makes period 1 unavailable to the disposal; use a clean asset for the disposal leg.
        asset2, disposal2 = self._disposal_setup()
        self._cost_entry()
        self._post_disposal(disposal2)
        wiz2 = self._recon()
        cost2 = self._row(wiz2, 'cost', self.fixed)
        self.assertNotIn(asset2, cost2.asset_ids)
        # GL: two cost entries (+2600) less the disposal credit (-1300) = the one asset still on the books.
        self.assertEqual((cost2.gl_balance, cost2.subledger_balance), (1300.0, 1300.0))

    def test_unmapped_category_listed_not_counted(self):
        bare = self.env['buz.asset.category'].create({
            'name': 'Bare', 'company_id': self.company.id, 'useful_life_months': 12})
        asset = self.env['buz.asset'].create({
            'name': 'NoAcct', 'category_id': bare.id, 'gross_cost': 500.0, 'useful_life_months': 12,
            'in_service_date': fields.Date.context_today(self.env['buz.asset'])})
        asset.sudo().write({'approval_state': 'approved', 'operational_state': 'in_service',
                            'accounting_state': 'capitalized'})
        wiz = self._recon()
        self.assertIn(asset, wiz.unmapped_asset_ids)

    def test_reports_permissions(self):
        viewer = self.env['res.users'].with_context(no_reset_password=True, skip_partner_required_fields=True).create({
            'name': 'rep viewer', 'login': 'buz_rep_viewer',
            'groups_id': [Command.set([self.env.ref('base.group_user').id,
                                       self.env.ref('buz_asset_management.group_asset_user').id])]})
        for model in ('buz.asset.reconcile.wizard', 'buz.asset.rollforward.wizard'):
            with self.assertRaises(AccessError):
                self.env[model].with_user(viewer).create({})
        ageing = self.env['buz.asset.ageing.wizard'].with_user(viewer).create({})
        ageing.action_compute()
        self.assertTrue(ageing.line_ids)

    def test_rollforward_identities(self):
        today = fields.Date.context_today(self.env['buz.asset'])
        asset = self._running_asset()
        for line in self._due(asset):
            line.with_user(self.acc_manager).action_post_depreciation()
        posted = sum(self._due(asset).mapped('planned_amount'))
        wiz = self.env['buz.asset.rollforward.wizard'].with_user(self.accountant).create({
            'date_from': today - relativedelta(years=1), 'date_to': today})
        wiz.action_compute()
        line = wiz.line_ids.filtered(lambda l: l.category_id == self.category)
        self.assertEqual((line.opening_cost, line.additions, line.disposals_cost, line.closing_cost),
                         (0.0, 1300.0, 0.0, 1300.0))
        self.assertEqual((line.opening_accum, line.depreciation, line.closing_accum), (0.0, posted, posted))
        self.assertEqual((line.cost_check, line.accum_check), (0.0, 0.0))
        self.assertEqual(line.net_book_value, 1300.0 - posted)
        # Later period: everything is opening balance, only new depreciation moves.
        later = self.env['buz.asset.rollforward.wizard'].with_user(self.accountant).create({
            'date_from': today + relativedelta(days=1), 'date_to': today + relativedelta(days=40)})
        later.action_compute()
        line2 = later.line_ids.filtered(lambda l: l.category_id == self.category)
        self.assertEqual((line2.opening_cost, line2.additions), (1300.0, 0.0))
        self.assertEqual(line2.opening_accum, posted)
        self.assertEqual((line2.cost_check, line2.accum_check), (0.0, 0.0))

    def test_rollforward_with_disposal(self):
        today = fields.Date.context_today(self.env['buz.asset'])
        asset, disposal = self._disposal_setup()
        accumulated = sum(self._due(asset).mapped('planned_amount'))
        self._post_disposal(disposal)
        wiz = self.env['buz.asset.rollforward.wizard'].with_user(self.accountant).create({
            'date_from': today - relativedelta(years=1), 'date_to': today})
        wiz.action_compute()
        line = wiz.line_ids.filtered(lambda l: l.category_id == self.category)
        self.assertEqual((line.additions, line.disposals_cost, line.closing_cost), (1300.0, 1300.0, 0.0))
        self.assertEqual((line.depreciation, line.disposals_accum, line.closing_accum),
                         (accumulated, accumulated, 0.0))
        self.assertEqual((line.cost_check, line.accum_check), (0.0, 0.0))

    def test_ageing_buckets_and_drilldown(self):
        asset = self._running_asset()
        ageing = self.env['buz.asset.ageing.wizard'].with_user(self.accountant).create({})
        ageing.action_compute()
        young = ageing.line_ids.filtered(lambda l: l.sequence == 0)
        self.assertIn(asset, young.asset_ids)
        self.assertEqual(young.action_open_assets()['domain'], [('id', 'in', young.asset_ids.ids)])
        self.assertEqual(sum(ageing.line_ids.mapped('asset_count')),
                         len(ageing.line_ids.mapped('asset_ids')))
        old = self._running_asset(in_service_date=fields.Date.context_today(asset) - relativedelta(years=4))
        ageing.action_compute()
        mid = ageing.line_ids.filtered(lambda l: l.sequence == 2)
        self.assertIn(old, mid.asset_ids)

    def test_forecast_action_has_only_unposted_periods(self):
        asset = self._running_asset()
        due = self._due(asset)
        due[0].with_user(self.acc_manager).action_post_depreciation()
        action = self.env.ref('buz_asset_management.action_buz_report_forecast')
        lines = self.env['buz.asset.depreciation.line'].search(eval(action.domain) + [('asset_id', '=', asset.id)])
        self.assertNotIn(due[0], lines)
        self.assertEqual(len(lines), len(asset.depreciation_line_ids) - 1)
