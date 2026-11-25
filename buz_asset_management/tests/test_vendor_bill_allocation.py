# -*- coding: utf-8 -*-
from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestVendorBillAllocation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.category = cls.env['buz.asset.category'].create({
            'name': 'Equipment', 'company_id': cls.company.id, 'useful_life_months': 36})
        cls.partner = cls.env['res.partner'].with_context(skip_partner_required_fields=True).create(
            {'name': 'Vendor X'})
        cls.account = cls.env['account.account'].create({
            'code': 'BUZFA9', 'name': 'Fixed assets', 'account_type': 'asset_fixed', 'company_id': cls.company.id})
        Users = cls.env['res.users'].with_context(no_reset_password=True, skip_partner_required_fields=True)
        base = [cls.env.ref('base.group_user').id, cls.env.ref('account.group_account_invoice').id]
        cls.officer = Users.create({
            'name': 'Bill Officer', 'login': 'buz_bill_officer',
            'groups_id': [Command.set(base + [cls.env.ref('buz_asset_management.group_asset_officer').id])]})
        cls.plain = Users.create({
            'name': 'Bill Plain', 'login': 'buz_bill_plain', 'groups_id': [Command.set(base)]})

    def _bill(self, move_type='in_invoice', post=True, amounts=(1000.0, 500.0)):
        bill = self.env['account.move'].create({
            'move_type': move_type, 'partner_id': self.partner.id,
            'invoice_date': fields.Date.context_today(self.env['buz.asset']),
            'invoice_line_ids': [Command.create({
                'name': 'Item %s' % i, 'quantity': 1, 'price_unit': price,
                'account_id': self.account.id, 'tax_ids': [Command.clear()]})
                for i, price in enumerate(amounts)]})
        if post:
            bill.action_post()
        return bill

    def _wizard(self, bill, user=None):
        wiz = self.env['buz.asset.register.wizard'].with_user(user or self.officer).with_context(
            default_move_id=bill.id).create({'move_id': bill.id})
        return wiz

    def _fill(self, wiz, *rows):
        """rows: (wizard_line_index, amount) ; sets the category on every line."""
        wiz.line_ids.write({'category_id': self.category.id})
        return wiz

    def test_default_lines_are_eligible_bill_lines(self):
        bill = self._bill()
        wiz = self._wizard(bill)
        self.assertEqual(sorted(wiz.line_ids.mapped('amount')), [500.0, 1000.0])

    def test_create_assets_one_per_line(self):
        bill = self._bill()
        wiz = self._fill(self._wizard(bill))
        wiz.action_create_assets()
        assets = self.env['buz.asset'].search([('source_move_id', '=', bill.id)])
        self.assertEqual(sorted(assets.mapped('gross_cost')), [500.0, 1000.0])
        self.assertEqual(set(assets.mapped('source_type')), {'vendor_bill'})
        self.assertEqual(set(assets.mapped('vendor_id')), {self.partner})
        self.assertEqual(set(assets.mapped('approval_state')), {'draft'})
        # Register-only: no accounting entry created by registration.
        self.assertFalse(self.env['account.move'].search([('ref', 'in', assets.mapped('code'))]))
        self.assertFalse(assets.depreciation_line_ids)

    def test_split_allocation_of_one_line(self):
        bill = self._bill(amounts=(1000.0,))
        wiz = self._fill(self._wizard(bill))
        line = wiz.line_ids
        line.amount = 600.0
        line.copy({'amount': 400.0, 'wizard_id': wiz.id})
        wiz.action_create_assets()
        assets = self.env['buz.asset'].search([('source_move_id', '=', bill.id)])
        self.assertEqual(sorted(assets.mapped('gross_cost')), [400.0, 600.0])

    def test_overrun_in_wizard_rejected(self):
        bill = self._bill(amounts=(1000.0,))
        wiz = self._fill(self._wizard(bill))
        wiz.line_ids.amount = 1000.01
        with self.assertRaises(UserError):
            wiz.action_create_assets()
        self.assertFalse(self.env['buz.asset'].search([('source_move_id', '=', bill.id)]))

    def test_second_registration_cannot_exceed_remaining(self):
        bill = self._bill(amounts=(1000.0,))
        wiz = self._fill(self._wizard(bill))
        wiz.line_ids.amount = 700.0
        wiz.action_create_assets()
        wiz2 = self._wizard(bill)
        self.assertEqual(wiz2.line_ids.amount, 300.0)  # only the remainder is offered
        wiz2 = self._fill(wiz2)
        wiz2.line_ids.amount = 300.01
        with self.assertRaises(UserError):
            wiz2.action_create_assets()

    def test_model_constraint_blocks_overrun_and_duplicate(self):
        bill = self._bill(amounts=(1000.0,))
        line = bill.invoice_line_ids
        asset_a = self.env['buz.asset'].create({'name': 'A', 'category_id': self.category.id,
                                                'gross_cost': 800.0, 'useful_life_months': 12})
        asset_b = self.env['buz.asset'].create({'name': 'B', 'category_id': self.category.id,
                                                'gross_cost': 800.0, 'useful_life_months': 12})
        Acq = self.env['buz.asset.acquisition']
        Acq.create({'asset_id': asset_a.id, 'move_line_id': line.id, 'amount': 800.0})
        with self.assertRaises(ValidationError):
            Acq.create({'asset_id': asset_b.id, 'move_line_id': line.id, 'amount': 300.0})

    def test_draft_bill_and_refund_rejected(self):
        draft = self._bill(post=False)
        with self.assertRaises(UserError):
            draft.action_buz_register_assets()
        refund = self._bill(move_type='in_refund')
        with self.assertRaises(UserError):
            refund.action_buz_register_assets()
        asset = self.env['buz.asset'].create({'name': 'R', 'category_id': self.category.id,
                                              'gross_cost': 10.0, 'useful_life_months': 12})
        with self.assertRaises(ValidationError):
            self.env['buz.asset.acquisition'].create({
                'asset_id': asset.id, 'move_line_id': refund.invoice_line_ids[0].id, 'amount': 10.0})

    def test_tax_and_payable_lines_not_offered(self):
        bill = self._bill()
        wiz = self._wizard(bill)
        offered = wiz.line_ids.mapped('move_line_id')
        self.assertTrue(all(l.display_type == 'product' for l in offered))
        payable = bill.line_ids.filtered(lambda l: l.display_type == 'payment_term')
        self.assertFalse(offered & payable)

    def test_user_without_officer_group_rejected(self):
        bill = self._bill()
        wiz = self._fill(self._wizard(bill, user=self.officer))
        with self.assertRaises(AccessError):
            wiz.with_user(self.plain).action_create_assets()

    def test_bill_cannot_be_reset_or_cancelled_after_registration(self):
        bill = self._bill()
        self._fill(self._wizard(bill)).action_create_assets()
        with self.assertRaises(UserError):
            bill.button_draft()
        with self.assertRaises(UserError):
            bill.button_cancel()

    def test_deleting_draft_asset_frees_allocation(self):
        bill = self._bill(amounts=(1000.0,))
        self._fill(self._wizard(bill)).action_create_assets()
        asset = self.env['buz.asset'].search([('source_move_id', '=', bill.id)])
        asset.unlink()
        self.assertEqual(self._wizard(bill).line_ids.amount, 1000.0)

    # ------------------------------------------------------------------
    # Non-recoverable VAT
    # ------------------------------------------------------------------
    def _vat_tax(self, closing=False, flagged=True, account=True):
        acct = self.env['account.account'].create({
            'code': 'BUZNRV%s' % self.env['account.tax'].search_count([]), 'name': 'Non-recoverable VAT',
            'account_type': 'expense', 'company_id': self.company.id})
        reps = [Command.create({'repartition_type': 'base', 'factor_percent': 100.0})]
        tax_rep = {'repartition_type': 'tax', 'factor_percent': 100.0, 'use_in_tax_closing': closing}
        if account:
            tax_rep['account_id'] = acct.id
        reps.append(Command.create(tax_rep))
        refund = [Command.create({'repartition_type': 'base', 'factor_percent': 100.0}),
                  Command.create(dict(tax_rep))]
        return self.env['account.tax'].create({
            'name': 'NR VAT 7%% %s' % acct.code, 'amount': 7.0, 'amount_type': 'percent',
            'type_tax_use': 'purchase', 'buz_vat_non_recoverable': flagged,
            'invoice_repartition_line_ids': reps, 'refund_repartition_line_ids': refund})

    def _bill_with_tax(self, tax, price=1000.0):
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.partner.id,
            'invoice_date': fields.Date.context_today(self.env['buz.asset']),
            'invoice_line_ids': [Command.create({
                'name': 'Taxed item', 'quantity': 1, 'price_unit': price,
                'account_id': self.account.id, 'tax_ids': [Command.set(tax.ids)]})]})
        bill.action_post()
        return bill

    def test_non_recoverable_vat_added_to_cost(self):
        bill = self._bill_with_tax(self._vat_tax())
        wiz = self._wizard(bill)
        self.assertEqual(wiz.line_ids.amount, 1070.0)
        self._fill(wiz).action_create_assets()
        asset = self.env['buz.asset'].search([('source_move_id', '=', bill.id)])
        self.assertEqual(asset.gross_cost, 1070.0)

    def test_non_recoverable_vat_overrun_rejected(self):
        bill = self._bill_with_tax(self._vat_tax())
        wiz = self._fill(self._wizard(bill))
        wiz.line_ids.amount = 1070.01
        with self.assertRaises(UserError):
            wiz.action_create_assets()

    def test_recoverable_vat_not_in_cost(self):
        bill = self._bill_with_tax(self._vat_tax(flagged=False))
        self.assertEqual(self._wizard(bill).line_ids.amount, 1000.0)

    def test_flag_rejected_when_tax_line_is_in_tax_closing_or_has_no_account(self):
        with self.assertRaises(ValidationError):
            self._vat_tax(closing=True)
        with self.assertRaises(ValidationError):
            self._vat_tax(account=False)
