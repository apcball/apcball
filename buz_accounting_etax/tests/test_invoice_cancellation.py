from odoo.tests.common import TransactionCase


class TestInvoiceCancellation(TransactionCase):
    def test_only_draft_transactions_follow_new_invoice_cancellation(self):
        partner = self.env['res.partner'].create({'name': 'E-Tax Test Customer'})
        journal = self.env['account.journal'].search([
            ('type', '=', 'sale'), ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].create({
                'name': 'E-Tax Test Sales', 'code': 'ETXT', 'type': 'sale',
            })

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'journal_id': journal.id,
        })
        transactions = self.env['etax.transaction']
        draft = transactions.create({'invoice_id': invoice.id, 'partner_id': partner.id})
        sent = transactions.create({
            'invoice_id': invoice.id, 'partner_id': partner.id, 'state': 'sent',
        })

        invoice.button_cancel()

        self.assertEqual(draft.state, 'cancel')
        self.assertEqual(sent.state, 'sent')

        old_draft = transactions.create({'invoice_id': invoice.id, 'partner_id': partner.id})
        invoice.write({'state': 'cancel'})
        self.assertEqual(old_draft.state, 'draft')
