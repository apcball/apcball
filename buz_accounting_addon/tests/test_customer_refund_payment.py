from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestCustomerRefundPayment(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create SO -> Invoice (paid) -> Credit Note with sale_line_ids linkage per spec
        cls.sale_order = cls.env["sale.order"].create({
            "partner_id": cls.partner_a.id,
            "order_line": [
                Command.create({
                    "product_id": cls.product_a.id,
                    "product_uom_qty": 1.0,
                    "price_unit": 4990.0,
                    "tax_id": [Command.clear()],
                }),
            ],
        })
        cls.sale_order.action_confirm()
        # Create and post the source invoice
        cls.source_invoice = cls.sale_order._create_invoices()[0]
        cls.source_invoice.action_post()
        # Pay the source invoice fully so payment_state = paid & residual 0
        pay_ctx = {"active_model": "account.move", "active_ids": cls.source_invoice.ids}
        pay_wizard = cls.env["account.payment.register"].with_context(**pay_ctx).create({"cheque_amount": cls.source_invoice.amount_residual})
        pay_wizard._create_payments()
        cls.source_invoice.invalidate_recordset(["payment_state", "amount_residual"])
        # Create Credit Note linked via sale_line_ids (primary relation per spec)
        cls.credit_note = cls.env["account.move"].create({
            "move_type": "out_refund",
            "partner_id": cls.partner_a.id,
            "invoice_date": fields.Date.today(),
            "reversed_entry_id": cls.source_invoice.id,
            "invoice_origin": cls.sale_order.name,
            "invoice_line_ids": [
                Command.create({
                    "product_id": cls.product_a.id,
                    "quantity": 1.0,
                    "price_unit": 4990.0,
                    "tax_ids": [Command.clear()],
                    "sale_line_ids": [Command.set(cls.sale_order.order_line.ids)],
                }),
            ],
        })
        cls.credit_note.action_post()

        bank_journal = cls.company_data["default_journal_bank"]
        cls.refund_pv = cls.env["buz.customer.refund.pv"].create({
            "name": "TEST-RPV-0001",
            "date": fields.Date.today(),
            "partner_id": cls.partner_a.id,
            "credit_note_id": cls.credit_note.id,
            "refund_amount": 4000.0,
            "destination_journal_id": bank_journal.id,
            "payment_method_line_id": bank_journal.outbound_payment_method_line_ids[:1].id,
            "state": "posted",
        })

    def _create_refund_wizard(self):
        action = self.refund_pv.action_register_refund_payment()
        return (
            action,
            self.env["account.payment.register"]
            .with_context(**action["context"])
            .create({"cheque_amount": self.refund_pv.refund_amount}),
        )

    def test_refund_action_forces_approved_amount(self):
        action, wizard = self._create_refund_wizard()

        self.assertFalse(action["context"]["batch"])
        self.assertEqual(
            action["context"]["buz_customer_refund_pv_id"],
            self.refund_pv.id,
        )
        self.assertEqual(wizard.amount, 4000.0)

    def test_standard_credit_note_action_remains_unchanged(self):
        action = self.credit_note.action_register_payment()
        self.assertNotIn("buz_customer_refund_pv_id", action["context"])

        wizard = (
            self.env["account.payment.register"]
            .with_context(**action["context"])
            .create({"cheque_amount": self.credit_note.amount_residual})
        )
        self.assertEqual(wizard.amount, 4990.0)

    def test_refund_payment_is_partial_linked_and_reconciled(self):
        _action, wizard = self._create_refund_wizard()
        wizard.make_payments()

        payment = self.refund_pv.payment_ids.filtered(
            lambda record: record.state != "cancel"
        )
        self.assertEqual(len(payment), 1)
        self.assertEqual(payment.amount, 4000.0)
        self.assertEqual(payment.buz_customer_refund_pv_id, self.refund_pv)
        # New flow: payment created as Draft, not yet reconciled
        self.assertEqual(payment.state, 'draft')
        self.credit_note.invalidate_recordset(["amount_residual"])
        self.assertEqual(self.credit_note.amount_residual, 4990.0)
        # แก้เลข Payment ได้ตอน Draft (เลขเดียวกับ Journal Entry)
        payment.name = 'PBNK11/2026/00009'
        self.assertEqual(payment.move_id.name, 'PBNK11/2026/00009')
        self.assertEqual(payment.name, 'PBNK11/2026/00009')
        # Post แล้วจึง Reconcile
        payment.action_post()
        self.assertEqual(payment.state, 'posted')
        self.credit_note.invalidate_recordset(["amount_residual"])
        self.assertEqual(self.credit_note.amount_residual, 990.0)

    def test_refund_payment_draft_editable_and_post_locks(self):
        _action, wizard = self._create_refund_wizard()
        wizard.make_payments()
        payment = self.refund_pv.payment_ids.filtered(lambda r: r.state != 'cancel')[:1]
        # Draft แก้ได้
        payment.name = 'PBNK11/2026/00010'
        self.assertEqual(payment.name, 'PBNK11/2026/00010')
        payment.action_post()
        # Posted ล็อก
        with self.assertRaises(UserError):
            payment.name = 'PBNK11/2026/00011'

    def test_refund_payment_duplicate_number_blocked(self):
        _action, wizard = self._create_refund_wizard()
        wizard.make_payments()
        payment = self.refund_pv.payment_ids.filtered(lambda r: r.state != 'cancel')[:1]
        payment.name = 'PBNK11/2026/00012'
        # สร้าง PV ที่สองและ payment ที่สองด้วยเลขซ้ำใน Journal เดียวกัน
        # Simulate duplicate by trying to set same name on another payment in same journal
        # Create second refund PV for same CN with remaining amount
        bank_journal = self.company_data["default_journal_bank"]
        pv2 = self.env["buz.customer.refund.pv"].create({
            "name": "TEST-RPV-0002",
            "date": fields.Date.today(),
            "partner_id": self.partner_a.id,
            "credit_note_id": self.credit_note.id,
            "refund_amount": 990.0,
            "destination_journal_id": bank_journal.id,
            "payment_method_line_id": bank_journal.outbound_payment_method_line_ids[:1].id,
            "state": "posted",
        })
        action2 = pv2.action_register_refund_payment()
        wizard2 = self.env["account.payment.register"].with_context(**action2["context"]).create({"cheque_amount": 990.0})
        wizard2.make_payments()
        payment2 = pv2.payment_ids.filtered(lambda r: r.state != 'cancel')[:1]
        with self.assertRaises(UserError):
            payment2.name = 'PBNK11/2026/00012'

    def test_refund_payment_draft_not_reconciled(self):
        _action, wizard = self._create_refund_wizard()
        wizard.make_payments()
        self.credit_note.invalidate_recordset(["amount_residual", "payment_state"])
        # Draft ยังไม่ Reconcile
        self.assertEqual(self.credit_note.amount_residual, 4990.0)

    def test_server_rejects_tampered_amount(self):
        _action, wizard = self._create_refund_wizard()
        wizard.amount = 4990.0

        with self.assertRaises(UserError):
            wizard._create_payments()