from odoo import fields, models, tools


class BuzBillPaymentRef(models.Model):
    _name = "buz.bill.payment.ref"
    _description = "Bill / Invoice vs Payment Document Reference"
    _auto = False
    _order = "payment_date desc, id desc"

    partial_id = fields.Many2one("account.partial.reconcile", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    direction = fields.Selection(
        [("pay", "Payment (Vendor)"), ("receive", "Receipt (Customer)")],
        readonly=True,
    )
    move_id = fields.Many2one("account.move", string="Bill / Invoice", readonly=True)
    move_type = fields.Selection(
        [
            ("in_invoice", "Vendor Bill"),
            ("in_refund", "Vendor Credit Note"),
            ("out_invoice", "Customer Invoice"),
            ("out_refund", "Customer Credit Note"),
        ],
        readonly=True,
    )
    partner_id = fields.Many2one("res.partner", readonly=True)
    invoice_date = fields.Date(readonly=True)
    invoice_date_due = fields.Date(readonly=True)
    bill_ref = fields.Char(string="Vendor Ref", readonly=True)
    amount_total = fields.Monetary(currency_field="currency_id", readonly=True)
    payment_move_id = fields.Many2one(
        "account.move", string="Payment Document", readonly=True
    )
    payment_name = fields.Char(string="Payment Doc No.", readonly=True)
    payment_ref = fields.Char(string="Payment Memo / Cheque", readonly=True)
    payment_id = fields.Many2one("account.payment", readonly=True)
    journal_id = fields.Many2one("account.journal", readonly=True)
    payment_date = fields.Date(readonly=True)
    amount_paid = fields.Monetary(
        string="Amount Settled", currency_field="currency_id", readonly=True
    )
    currency_id = fields.Many2one("res.currency", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW buz_bill_payment_ref AS (
            SELECT
                pr.id AS id,
                pr.id AS partial_id,
                inv.company_id,
                CASE WHEN inv.move_type IN ('in_invoice','in_refund')
                     THEN 'pay' ELSE 'receive' END AS direction,
                inv.id AS move_id,
                inv.move_type,
                inv.partner_id,
                inv.invoice_date,
                inv.invoice_date_due,
                inv.ref AS bill_ref,
                inv.amount_total,
                pm.id AS payment_move_id,
                pm.name AS payment_name,
                COALESCE(ap.payment_reference, pm.ref) AS payment_ref,
                ap.id AS payment_id,
                pm.journal_id,
                pm.date AS payment_date,
                pr.amount AS amount_paid,
                inv.currency_id
            FROM account_partial_reconcile pr
            JOIN account_move_line dl ON dl.id = pr.debit_move_id
            JOIN account_move_line cl ON cl.id = pr.credit_move_id
            JOIN account_move dm ON dm.id = dl.move_id
            JOIN account_move cm ON cm.id = cl.move_id
            JOIN account_move inv ON inv.id = CASE
                WHEN dm.move_type IN ('in_invoice','in_refund','out_invoice','out_refund')
                THEN dm.id ELSE cm.id END
            JOIN account_move pm ON pm.id = CASE
                WHEN inv.id = dm.id THEN cm.id ELSE dm.id END
            LEFT JOIN account_payment ap ON ap.move_id = pm.id
            WHERE pm.id <> inv.id
            )
            """
        )
