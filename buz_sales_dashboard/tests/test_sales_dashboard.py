import base64
import io
import json
import zipfile
from datetime import datetime, timedelta
from xml.etree import ElementTree

import openpyxl
from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import mute_logger
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged

from odoo.addons.buz_sales_dashboard.hooks import revoke_automatic_access

NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_xlsx(content):
    """{sheet name: [[cell value, ...], ...]} using only the standard library."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(t.text or "" for t in si.iter("{%s}t" % NS["x"]))
                       for si in root.findall("x:si", NS)]
        book = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        result = {}
        for number, sheet in enumerate(book.find("x:sheets", NS), start=1):
            root = ElementTree.fromstring(
                archive.read("xl/worksheets/sheet%d.xml" % number))
            rows = []
            for row in root.iter("{%s}row" % NS["x"]):
                values = []
                for cell in row.findall("x:c", NS):
                    value = cell.find("x:v", NS)
                    if value is None:
                        values.append(None)
                    elif cell.get("t") == "s":
                        values.append(strings[int(value.text)])
                    else:
                        values.append(float(value.text))
                rows.append(values)
            result[sheet.get("name")] = rows
        return result


class DashboardCommon:
    """Documents dated 2001, far from any real data of the database."""

    FILTERS = {"date_preset": "custom", "date_from": "2001-01-01",
               "date_to": "2001-12-31"}

    @classmethod
    def _setup_documents(cls):
        cls.env = cls.env(context=dict(
            cls.env.context, skip_partner_required_fields=True,
            tracking_disable=True, no_reset_password=True))
        salesman = ("base.group_user,sales_team.group_sale_salesman,"
                    "buz_sales_dashboard.group_own")
        cls.user_a = new_test_user(cls.env, "bsd_a", groups=salesman,
                                   name="BSD Seller A", password="bsd_a_pass_123")
        cls.user_b = new_test_user(cls.env, "bsd_b", groups=salesman,
                                   name="BSD Seller B", password="bsd_b_pass_123")
        cls.leader = new_test_user(cls.env, "bsd_lead", groups=salesman,
                                   name="BSD Leader")
        cls.manager = new_test_user(
            cls.env, "bsd_boss", name="BSD Manager",
            groups="base.group_user,sales_team.group_sale_manager")
        cls.manager.write({"groups_id": [Command.link(
            cls.env.ref("buz_sales_dashboard.group_all").id)]})
        cls.team_1 = cls.env["crm.team"].create(
            {"name": "BSD Team 1", "user_id": cls.leader.id})
        cls.team_2 = cls.env["crm.team"].create({"name": "BSD Team 2"})
        cls.partner = cls.env["res.partner"].create({"name": "BSD Customer"})
        product = cls.env["product.product"]
        cls.goods = product.create({"name": "BSD Goods", "detailed_type": "consu"})
        cls.service = product.create(
            {"name": "BSD Service", "detailed_type": "service"})
        cls.deposit = product.create({
            "name": "BSD Deposit", "detailed_type": "service",
            "exclude_from_sales_dashboard": True})

    @classmethod
    def _order(cls, user, team, lines, state="sale",
               date=datetime(2001, 3, 10, 3, 0), name=None):
        """``lines``: (product, qty, price, delivered).

        State and delivered quantity are written in SQL: the dashboard only
        reads the tables, and confirming would start unrelated stock flows.
        """
        order = cls.env["sale.order"].create({
            "partner_id": cls.partner.id,
            "user_id": user.id if user else False,
            "team_id": team.id if team else False,
            "order_line": [Command.create({
                "product_id": product.id, "product_uom_qty": qty,
                "price_unit": price, "discount": 0.0,
                "tax_id": [Command.clear()],
            }) for product, qty, price, _delivered in lines],
        })
        cls.env.flush_all()
        for line, spec in zip(order.order_line, lines):
            cls.env.cr.execute(
                "UPDATE sale_order_line SET qty_delivered=%s, price_subtotal=%s,"
                " price_total=%s WHERE id=%s",
                (spec[3], spec[1] * spec[2], spec[1] * spec[2] * 1.07, line.id))
        cls.env.cr.execute(
            "UPDATE sale_order SET state=%s, date_order=%s, user_id=%s,"
            " team_id=%s, name=COALESCE(%s, name) WHERE id=%s",
            (state, date, user.id if user else None,
             team.id if team else None, name, order.id))
        cls.env.invalidate_all()
        return order

    @classmethod
    def _move(cls, user, team, amount, move_type="out_invoice", journal=None,
              state="posted", date="2001-03-15", name=None, **values):
        """An invoice with one line, put in its final state by SQL."""
        journal = journal or cls.other_journal
        move = cls.env["account.move"].create({
            "move_type": move_type, "partner_id": cls.partner.id,
            "journal_id": journal.id, "invoice_date": date,
            "invoice_line_ids": [Command.create({
                "name": "line", "quantity": 1, "price_unit": amount,
                "tax_ids": [Command.clear()],
            })],
        })
        cls.env.flush_all()
        values = dict(values, state=state, invoice_user_id=user.id if user else None,
                      team_id=team.id if team else None,
                      name=name or "BSDX/%s" % move.id, invoice_date=date)
        cls.env.cr.execute(
            "UPDATE account_move SET %s WHERE id=%%s" % ", ".join(
                "%s=%%s" % key for key in values),
            list(values.values()) + [move.id])
        cls.env.invalidate_all()
        return move

    @classmethod
    def _setup_journals(cls):
        company = cls.env.company
        sale_journals = cls.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", company.id)])
        pos_journals = cls.env["pos.lite.config"].search([]).sale_journal_id
        cls.pos_journal = (pos_journals & sale_journals)[:1]
        cls.other_journal = (sale_journals - pos_journals)[:1]

    def _data(self, user, **filters):
        return self.env["buz.sales.dashboard.report"].with_user(user).get_dashboard_data(
            dict(self.FILTERS, **filters))


@tagged("post_install", "-at_install")
class TestSalesDashboard(DashboardCommon, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_documents()
        cls._setup_journals()

    def _row(self, record):
        field = "order_id" if record._name == "sale.order" else "move_id"
        self.env.flush_all()
        return self.env["buz.sales.dashboard.report"].search(
            [(field, "=", record.id), ("state", "not in",
             ("so_credit", "bill_invoice", "bill_refund"))])

    def assertAmounts(self, row, **expected):
        for name in [f for f in row._fields if f.startswith("amount_")]:
            self.assertAlmostEqual(
                row[name], expected.get(name[7:], 0.0), places=2, msg=name)

    # ------------------------------------------------------------ sale orders
    def test_report_is_read_without_jit(self):
        self.env.cr.execute("SET LOCAL jit = on")
        self.env["buz.sales.dashboard.report"].search([], limit=1)
        self.env.cr.execute("SHOW jit")
        self.assertEqual(self.env.cr.fetchone()[0], "off")

    def test_confirmed_order_is_split_by_line_kind(self):
        order = self._order(self.user_a, self.team_1, [
            (self.goods, 10, 100, 4),      # 400 delivered, 600 pending
            (self.goods, 2, 50, 5),        # over delivered: capped at 100
            (self.service, 1, 300, 0),
            (self.goods, 1, -80, 1),       # negative amount: adjustment
            (self.service, -1, 20, 0),     # negative quantity: adjustment
            (self.deposit, 1, 999, 0),     # excluded everywhere
        ])
        row = self._row(order)
        self.assertEqual(row.state, "sale")
        self.assertAmounts(
            row, so=1100 + 300 - 80 - 20, delivered=500, pending=600,
            service=300, adjust=-100, total=1300, total_vat=1300 * 1.07,
            pending_other=600)

    def test_quotation_counts_only_as_quotation(self):
        order = self._order(self.user_a, self.team_1,
                            [(self.goods, 1, 500, 0), (self.deposit, 1, 9, 0)],
                            state="sent")
        self.assertAmounts(self._row(order), quotation=500)

    def test_cancelled_and_pos_named_orders_are_left_out(self):
        cancelled = self._order(self.user_a, None, [(self.goods, 1, 5, 0)],
                                state="cancel")
        legacy = self._order(self.user_a, None, [(self.goods, 1, 5, 0)],
                             name="POSBSD0001")
        self.assertFalse(self._row(cancelled))
        self.assertFalse(self._row(legacy))

    def test_order_date_is_bangkok_time(self):
        order = self._order(self.user_a, None, [(self.goods, 1, 5, 0)],
                            date=datetime(2001, 12, 30, 18, 0))
        row = self._row(order)
        self.assertEqual(str(row.date), "2001-12-31")
        self.assertEqual(row.month, "2001-12")
        # ISO week: 31/12/2001 is the Monday of 2002-W01
        self.assertEqual(row.week, "2002-W01 (31/12-06/01)")

    def test_documents_named_cancelled_are_left_out(self):
        name = "ยกเลิก BSD-0001"
        confirmed = self._order(self.user_a, None, [(self.goods, 1, 5, 0)], name=name)
        quotation = self._order(self.user_a, None, [(self.goods, 1, 5, 0)],
                                state="draft", name="BSD-0002 ยกเลิก")
        invoice = self._move(self.user_a, None, 9, name="POSBSD-ยกเลิก")
        for record in (confirmed, quotation, invoice):
            self.assertFalse(self._row(record), record.id)
        # only the document number counts, not the team's name
        team = self.env["crm.team"].create({"name": "ยกเลิก BSD Team"})
        kept = self._order(self.user_a, team, [(self.goods, 1, 5, 0)])
        self.assertEqual(len(self._row(kept)), 1)

    def test_pending_is_split_in_three_groups(self):
        order = self._order(self.user_a, self.team_1, [
            (self.goods, 10, 10, 0),    # open delivery, even though billed
            (self.goods, 10, 20, 4),    # fully billed: 120 left
            (self.goods, 10, 30, 0),    # only done and cancelled deliveries
            (self.goods, 10, 40, 0),    # nothing at all
        ])
        lines = order.order_line
        stock = self.env.ref("stock.stock_location_stock")
        customers = self.env.ref("stock.stock_location_customers")
        for line, state in ((lines[0], "confirmed"), (lines[2], "done"),
                            (lines[2], "cancel")):
            move = self.env["stock.move"].create({
                "name": "BSD", "product_id": self.goods.id, "product_uom_qty": 1,
                "product_uom": self.goods.uom_id.id, "location_id": stock.id,
                "location_dest_id": customers.id})
            self.env.flush_all()
            self.env.cr.execute(
                "UPDATE stock_move SET sale_line_id=%s, state=%s WHERE id=%s",
                (line.id, state, move.id))
        self.env.cr.execute(
            "UPDATE sale_order_line SET qty_invoiced=product_uom_qty WHERE id IN %s",
            ((lines[0].id, lines[1].id),))
        self.env.invalidate_all()
        row = self._row(order)
        self.assertAlmostEqual(row.amount_pending, 100 + 120 + 300 + 400)
        self.assertAlmostEqual(row.amount_pending_open, 100)
        self.assertAlmostEqual(row.amount_pending_billed, 120)
        self.assertAlmostEqual(row.amount_pending_other, 700)

    # ------------------------------------------------------------ credit notes
    def _bill(self, line, amount, refund=False, date="2001-03-20", **values):
        """A posted invoice or credit note on an order line, 7% VAT."""
        move = self._move(
            self.user_b, None, amount,
            move_type="out_refund" if refund else "out_invoice", date=date, **values)
        self.env.cr.execute(
            "UPDATE account_move_line SET price_total=price_subtotal * 1.07"
            " WHERE move_id=%s AND display_type='product' RETURNING id", (move.id,))
        self.env.cr.execute(
            "INSERT INTO sale_order_line_invoice_rel (invoice_line_id, order_line_id)"
            " VALUES (%s, %s)", (self.env.cr.fetchone()[0], line.id))
        self.env.invalidate_all()
        return move

    def _credits(self, order):
        self.env.flush_all()
        return self.env["buz.sales.dashboard.report"].search(
            [("order_id", "=", order.id), ("state", "=", "so_credit")],
            order="date, name")

    def test_credit_note_lowers_the_order_on_its_own_date(self):
        order = self._order(self.user_a, self.team_1, [(self.goods, 1, 100, 1)])
        self._bill(order.order_line, 100)
        credit = self._bill(order.order_line, 40, refund=True, date="2001-05-02")
        row = self._credits(order)
        self.assertEqual((row.move_id, row.name, str(row.date), row.month),
                         (credit, credit.name, "2001-05-02", "2001-05"))
        self.assertEqual((row.user_id, row.team_id), (self.user_a, self.team_1),
                         "salesperson and team of the order")
        self.assertAmounts(row, so=-40, so_credit=-40, total=-40, total_vat=-42.8)
        self.assertEqual(row.action_open_document()["res_model"], "account.move")
        total = self._data(self.manager)["total"]
        self.assertAlmostEqual(total["amount_so"], 60)
        self.assertAlmostEqual(total["amount_total"], 60)
        self.assertAlmostEqual(total["amount_delivered"], 100)
        self.assertEqual(total["count"], 1, "the credit note is not a document")
        self.assertAlmostEqual(
            self._data(self.user_b)["total"]["amount_total"], 0)

    def test_negative_credit_note_line_is_ignored(self):
        order = self._order(self.user_a, None, [(self.goods, 1, 100, 1)])
        # half billed, so the cap is not what limits the deduction
        self._bill(order.order_line, 50)
        negative = self._bill(order.order_line, 10, refund=True)
        self.env.cr.execute(
            "UPDATE account_move_line SET price_subtotal=-10, price_total=-10.7"
            " WHERE move_id=%s AND display_type='product'", (negative.id,))
        real = self._bill(order.order_line, 30, refund=True, date="2001-04-01")
        rows = self._credits(order)
        self.assertEqual(rows.move_id, real)
        self.assertAlmostEqual(rows.amount_so_credit, -30)

    def test_credit_note_billed_again_is_not_deducted(self):
        order = self._order(self.user_a, None, [(self.goods, 1, 100, 1)])
        self._bill(order.order_line, 100)
        self._bill(order.order_line, 100, refund=True)
        self._bill(order.order_line, 100)
        self.assertFalse(self._credits(order))

    def test_credit_note_not_deducted_twice_with_negative_lines(self):
        order = self._order(self.user_a, None, [
            (self.goods, 1, 100, 1), (self.goods, 1, -30, 0)])
        self._bill(order.order_line[0], 100)
        old = self._bill(order.order_line[0], 25, refund=True, date="2001-04-01")
        new = self._bill(order.order_line[0], 25, refund=True, date="2001-04-09")
        # 50 credited, 30 already in the order lines; net 70 - billed 50 = 20
        rows = self._credits(order)
        self.assertEqual(rows.move_id, new, "negative lines use up the oldest note")
        self.assertNotIn(old, rows.move_id)
        self.assertAlmostEqual(rows.amount_so_credit, -20)

    def test_credit_note_of_an_earlier_year_order(self):
        order = self._order(self.user_a, None, [(self.goods, 1, 100, 1)],
                            date=datetime(2000, 6, 1, 3, 0))
        self._bill(order.order_line, 100, date="2000-06-02")
        self._bill(order.order_line, 10, refund=True, date="2001-02-01")
        total = self._data(self.manager)["total"]
        self.assertAlmostEqual(total["amount_so_credit"], -10)
        self.assertAlmostEqual(total["amount_total"], -10)

    def test_credit_notes_that_do_not_count(self):
        order = self._order(self.user_a, None, [
            (self.goods, 1, 100, 1), (self.deposit, 1, 50, 0)])
        goods, deposit = order.order_line
        self._bill(goods, 100)
        pos = self._bill(goods, 10, refund=True, name="CNPBSD/9")
        self._bill(goods, 10, refund=True, state="draft")
        self._bill(deposit, 10, refund=True)
        self.assertFalse(self._credits(order))
        self.assertAlmostEqual(self._row(pos).amount_pos_refund, -10)
        cancelled = self._order(self.user_a, None, [(self.goods, 1, 100, 1)],
                                name="ยกเลิก BSD-0003")
        self._bill(cancelled.order_line, 10, refund=True)
        self.assertFalse(self._credits(cancelled))

    # ------------------------------------------------------------ invoicing
    def _bills(self, move):
        self.env.flush_all()
        return self.env["buz.sales.dashboard.report"].search(
            [("move_id", "=", move.id),
             ("state", "in", ("bill_invoice", "bill_refund"))])

    def test_invoicing_follows_the_invoice(self):
        order = self._order(self.user_a, self.team_1, [(self.goods, 1, 100, 1)])
        invoice = self._bill(order.order_line, 100, date="2001-04-02")
        credit = self._bill(order.order_line, 30, refund=True, date="2001-05-03")
        loose = self._move(self.user_b, self.team_2, 7, date="2001-04-05")
        row = self._bills(invoice)
        # salesperson, team and date of the invoice, not of the order
        self.assertEqual((row.user_id, str(row.date), row.source),
                         (self.user_b, "2001-04-02", "so"))
        self.assertAmounts(row, inv_so_invoice=100, inv_so=100, invoiced=100)
        self.assertAmounts(self._bills(credit), inv_so_refund=-30, inv_so=-30,
                           invoiced=-30)
        self.assertAmounts(self._bills(loose), inv_other=7, invoiced=7)
        self.assertEqual(row.action_open_document()["res_id"], invoice.id)
        total = self._data(self.manager)["total"]
        self.assertAlmostEqual(total["amount_inv_so"], 70)
        self.assertAlmostEqual(total["amount_inv_other"], 7)
        self.assertAlmostEqual(total["amount_invoiced"], 77)
        # the sales columns keep their own rules and gain nothing
        self.assertAlmostEqual(total["amount_total"], 100 - 30)
        self.assertEqual(total["count"], 1, "invoices are not counted again")
        # the invoice belongs to its own salesperson
        self.assertAlmostEqual(
            self._data(self.user_b)["total"]["amount_invoiced"], 77)
        self.assertAlmostEqual(
            self._data(self.user_a)["total"]["amount_invoiced"], 0)

    def test_invoiced_includes_pos_once_and_skips_excluded_and_drafts(self):
        pos = self._move(self.user_a, None, 50, name="POSBSD/I1")
        draft = self._move(self.user_a, None, 9, state="draft")
        deposit = self._move(self.user_a, None, 11)
        self.env.cr.execute(
            "UPDATE account_move_line SET product_id=%s WHERE move_id=%s"
            " AND display_type='product'", (self.deposit.id, deposit.id))
        for move in (pos, draft, deposit):
            self.assertFalse(self._bills(move), move.id)
        total = self._data(self.manager)["total"]
        self.assertAlmostEqual(total["amount_invoiced"], 50)
        self.assertAlmostEqual(total["amount_pos"], 50)

    def test_cancelled_name_rule_does_not_apply_to_invoicing(self):
        plain = self._move(self.user_a, None, 5, name="BSD-ยกเลิก-1")
        pos = self._move(self.user_a, None, 6, name="POSBSD-ยกเลิก-2")
        for move, amount in ((plain, 5), (pos, 6)):
            self.assertAmounts(self._bills(move), inv_other=amount, invoiced=amount)
        total = self._data(self.manager)["total"]
        self.assertAlmostEqual(total["amount_pos"], 0)
        self.assertAlmostEqual(total["amount_invoiced"], 11)

    def test_pos_invoiced_is_in_company_currency(self):
        # a foreign currency document: the balance differs from the line amount
        pos = self._move(self.user_a, None, 10, name="POSBSD/FX1")
        self.env.cr.execute(
            "UPDATE account_move_line SET balance=-350, credit=350"
            " WHERE move_id=%s AND display_type='product'", (pos.id,))
        self.env.invalidate_all()
        self.assertAmounts(self._row(pos), pos_invoice=10, pos=10, total=10,
                           total_vat=10, invoiced=350)

    def test_invoiced_matches_invoice_analysis(self):
        order = self._order(self.user_a, self.team_1, [(self.goods, 1, 100, 1)])
        self._bill(order.order_line, 100)
        self._bill(order.order_line, 30, refund=True)
        self._move(self.user_a, self.team_1, 12, name="POSBSD/I2")
        self.env.flush_all()
        [(analysis,)] = self.env["account.invoice.report"]._read_group(
            [("state", "=", "posted"),
             ("move_type", "in", ("out_invoice", "out_refund")),
             ("invoice_date", ">=", "2001-01-01"),
             ("invoice_date", "<=", "2001-12-31")],
            aggregates=["price_subtotal:sum"])
        self.assertAlmostEqual(
            self._data(self.manager)["total"]["amount_invoiced"], analysis)

    # ------------------------------------------------------------ POS
    def test_pos_journal_invoice_and_credit_note(self):
        if not self.pos_journal:
            self.skipTest("no POS sale journal configured")
        invoice = self._move(self.user_a, self.team_1, 1000,
                             journal=self.pos_journal)
        refund = self._move(self.user_a, self.team_1, 100, "out_refund",
                            journal=self.pos_journal)
        self.assertAmounts(self._row(invoice), pos_invoice=1000, pos=1000,
                           total=1000, total_vat=1000, invoiced=1000)
        self.assertAmounts(self._row(refund), pos_refund=-100, pos=-100,
                           total=-100, total_vat=-100, invoiced=-100)

    def test_pos_selection_rules(self):
        by_name = self._move(self.user_a, None, 1, name="POSBSD/1")
        by_cnp = self._move(self.user_a, None, 1, "out_refund", name="CNPBSD/1")
        by_origin = self._move(self.user_a, None, 1, invoice_origin="POS123")
        by_ref = self._move(self.user_a, None, 1, "out_refund",
                            ref="คืนของ POS26010001")
        original = self._move(self.user_a, None, 1, invoice_origin="POS9")
        reversal = self._move(self.user_a, None, 1, "out_refund",
                              reversed_entry_id=original.id)
        second = self._move(self.user_a, None, 1, reversed_entry_id=reversal.id)
        for move in (by_name, by_cnp, by_origin, by_ref, original, reversal, second):
            self.assertEqual(len(self._row(move)), 1, move.id)
        plain = self._move(self.user_a, None, 1)
        invoice_with_ref = self._move(self.user_a, None, 1, ref="POS26010001")
        draft = self._move(self.user_a, None, 1, state="draft", name="POSBSD/2")
        for move in (plain, invoice_with_ref, draft):
            self.assertFalse(self._row(move), move.id)

    def test_pos_lite_and_legacy_order_links_count_once(self):
        lite = self._move(self.user_a, None, 70, name="POSBSD/3")
        self.env.cr.execute("SELECT id FROM pos_lite_order ORDER BY id LIMIT 1")
        found = self.env.cr.fetchone()
        if found:
            self.env.cr.execute(
                "UPDATE pos_lite_order SET invoice_id=%s WHERE id=%s",
                (lite.id, found[0]))
        legacy = self._order(self.user_a, None, [(self.goods, 1, 40, 0)],
                             name="POSBSD0002")
        invoice = self._move(self.user_a, None, 40)
        self.env.cr.execute(
            "SELECT id FROM account_move_line WHERE move_id=%s"
            " AND display_type='product'", (invoice.id,))
        self.env.cr.execute(
            "INSERT INTO sale_order_line_invoice_rel (invoice_line_id, order_line_id)"
            " VALUES (%s, %s)", (self.env.cr.fetchone()[0], legacy.order_line.id))
        self.assertEqual(len(self._row(lite)), 1)
        self.assertAmounts(self._row(invoice), pos_invoice=40, pos=40, total=40,
                           total_vat=40, invoiced=40)

    def test_excluded_product_on_pos_invoice(self):
        invoice = self._move(self.user_a, None, 55, name="POSBSD/4")
        self.env.cr.execute(
            "UPDATE account_move_line SET product_id=%s WHERE move_id=%s"
            " AND display_type='product'", (self.deposit.id, invoice.id))
        self.assertAmounts(self._row(invoice))

    # ------------------------------------------------------------ filters
    def _dataset(self):
        self._order(self.user_a, self.team_1, [(self.goods, 1, 100, 1)])
        self._order(self.user_b, self.team_2, [(self.goods, 1, 200, 0)],
                    date=datetime(2001, 4, 20, 3, 0))
        self._order(self.leader, self.team_2, [(self.goods, 1, 400, 0)])
        self._order(None, None, [(self.goods, 1, 800, 0)])
        self._move(self.user_b, self.team_1, 50, name="POSBSD/F1")
        self.env.flush_all()

    def test_multi_select_filters(self):
        self._dataset()

        def total(**filters):
            return self._data(self.manager, **filters)["total"]["amount_total"]

        self.assertEqual(total(), 1550)
        self.assertEqual(total(user_ids=[self.user_a.id, self.user_b.id]), 350)
        self.assertEqual(total(user_ids=[0]), 800)
        self.assertEqual(total(user_ids=[0, self.user_a.id]), 900)
        self.assertEqual(total(team_ids=[self.team_1.id, self.team_2.id]), 750)
        self.assertEqual(total(team_ids=[0]), 800)
        self.assertEqual(
            total(user_ids=[self.user_b.id], team_ids=[self.team_1.id]), 50)
        self.assertEqual(total(sources=["pos"]), 50)
        self.assertEqual(total(sources=["so"]), 1500)
        self.assertEqual(total(date_from="2001-04-01"), 200)

    def test_breakdowns_add_up_to_the_total(self):
        self._dataset()
        data = self._data(self.manager)
        for dim in ("month", "week", "user", "team"):
            self.assertAlmostEqual(
                sum(r["amount_total"] for r in data[dim]), 1550, msg=dim)
            self.assertEqual(sum(r["count"] for r in data[dim]), 5, dim)
        self.assertEqual([r["key"] for r in data["month"]], ["2001-03", "2001-04"])
        self.assertEqual(
            self.env["buz.sales.dashboard.report"].with_user(
                self.manager).search_count(data["domain"]), 5)

    def test_sanitize_ignores_bad_input(self):
        clean = self.env["buz.sales.dashboard.report"]._sanitize_filters({
            "date_preset": "x", "date_from": "nonsense", "user_ids": ["1", 2, -3, True],
            "team_ids": "7", "sources": [], "granularity": "day"})
        self.assertEqual(clean, {
            "date_preset": "this_month", "date_from": False, "date_to": False,
            "granularity": False, "user_ids": [2], "team_ids": [],
            "sources": ["so", "pos"]})

    # ------------------------------------------------------------ access
    def test_each_user_sees_only_what_is_allowed(self):
        self._dataset()
        total = lambda user: self._data(user)["total"]["amount_total"]
        self.assertEqual(total(self.user_a), 100)
        self.assertEqual(total(self.user_b), 250)
        # a sales team leader sees every team
        self.assertEqual(total(self.leader), 1550)
        self.assertEqual(total(self.manager), 1550)
        # asking for somebody else does not widen access
        self.assertEqual(
            self._data(self.user_a, user_ids=[self.user_b.id])["total"]["amount_total"], 0)

    def test_naming_or_replacing_a_team_leader_takes_effect_at_once(self):
        self._dataset()
        report = self.env["buz.sales.dashboard.report"].with_user(self.user_a)
        total = lambda: self._data(self.user_a)["total"]["amount_total"]
        self.assertEqual(total(), 100)
        self.assertFalse(report.search([], limit=1).viewer_leads_team)
        self.team_2.user_id = self.user_a
        self.assertEqual(total(), 1550)
        self.team_2.user_id = self.user_b
        self.assertEqual(total(), 100)
        self.assertEqual(self._data(self.user_b)["total"]["amount_total"], 1550)
        # an archived team no longer opens every team: its former leader keeps
        # only own documents and that team's (the own-and-led rule)
        self.team_2.active = False
        self.assertEqual(self._data(self.user_b)["total"]["amount_total"], 650)

    def test_target_managers_see_everything(self):
        self._dataset()
        boss = new_test_user(
            self.env, "bsd_tm",
            groups="base.group_user,buz_sales_dashboard.group_target_manager")
        self.assertTrue(boss.has_group("buz_sales_dashboard.group_all"))
        self.assertEqual(self._data(boss)["total"]["amount_total"], 1550)

    def test_sales_roles_alone_give_no_access(self):
        self._dataset()
        menu = self.env.ref("buz_sales_dashboard.menu_root")
        for login, role in (("bsd_man", "group_sale_salesman"),
                            ("bsd_mgr", "group_sale_manager")):
            plain = new_test_user(
                self.env, login, groups="base.group_user,sales_team.%s" % role)
            self.assertFalse(plain.has_group("buz_sales_dashboard.group_own"))
            self.assertNotIn(
                menu.id,
                self.env["ir.ui.menu"].with_user(plain)._visible_menu_ids())
            Report = self.env["buz.sales.dashboard.report"].with_user(plain)
            Target = self.env["buz.sales.target"].with_user(plain)
            for call in (
                    lambda: self._data(plain),
                    lambda: Report.get_dashboard_options(),
                    lambda: Report.search([]),
                    lambda: Report._export_xlsx(self.FILTERS),
                    lambda: Target.search([]),
                    lambda: Target.get_board("2001-03-01")):
                with self.assertRaises(AccessError):
                    call()
            with self.assertRaises(UserError):
                self.env["buz.sales.target.import"].with_user(plain)._template_xlsx()

    def test_a_granted_user_sees_the_menu(self):
        menu = self.env.ref("buz_sales_dashboard.menu_root")
        self.assertIn(
            menu.id,
            self.env["ir.ui.menu"].with_user(self.user_a)._visible_menu_ids())

    def test_upgrade_takes_the_automatic_access_back(self):
        own = self.env.ref("buz_sales_dashboard.group_own")
        salesman = self.env.ref("sales_team.group_sale_salesman")
        # the state left by 17.0.1.5.x
        salesman.write({"implied_ids": [Command.link(own.id)]})
        auto = new_test_user(
            self.env, "bsd_auto",
            groups="base.group_user,sales_team.group_sale_salesman")
        gone = new_test_user(
            self.env, "bsd_gone",
            groups="base.group_user,sales_team.group_sale_salesman")
        gone.active = False
        self.assertIn(own, auto.groups_id)

        revoke_automatic_access(self.env)

        self.assertNotIn(own, salesman.implied_ids)
        self.assertNotIn(own, auto.groups_id)
        self.assertNotIn(own, gone.groups_id)
        self.assertIn(salesman, auto.groups_id)
        self.assertIn(own, self.manager.groups_id)
        self.assertTrue(self.env.ref("base.user_admin").has_group(
            "buz_sales_dashboard.group_target_manager"))

    def test_members_are_added_and_removed_on_the_group_or_the_user(self):
        self._dataset()
        own = self.env.ref("buz_sales_dashboard.group_own")
        every = self.env.ref("buz_sales_dashboard.group_all")
        user = new_test_user(
            self.env, "bsd_member",
            groups="base.group_user,sales_team.group_sale_salesman")
        # on the group form
        own.write({"users": [Command.link(user.id)]})
        self.assertEqual(self._data(user)["total"]["amount_total"], 0)
        every.write({"users": [Command.link(user.id)]})
        self.assertEqual(self._data(user)["total"]["amount_total"], 1550)
        # leaving "see all" there keeps the narrow level
        every.write({"users": [Command.unlink(user.id)]})
        self.assertEqual(self._data(user)["total"]["amount_total"], 0)
        own.write({"users": [Command.unlink(user.id)]})
        with self.assertRaises(AccessError):
            self._data(user)
        # on the user form
        user.write({"groups_id": [Command.link(own.id)]})
        self.assertEqual(self._data(user)["total"]["amount_total"], 0)
        user.write({"groups_id": [Command.unlink(own.id)]})
        self.assertFalse(user.has_group("buz_sales_dashboard.group_own"))

    def test_user_without_sales_group_has_no_access(self):
        outsider = new_test_user(self.env, "bsd_out", groups="base.group_user")
        with self.assertRaises(AccessError):
            self._data(outsider)

    def test_saved_filters_are_personal(self):
        Saved = self.env["buz.sales.dashboard.filter"]
        first = Saved.with_user(self.user_a).create(
            {"name": "A1", "is_default": True,
             "filters": {"user_ids": [self.user_a.id], "junk": 1}})
        second = Saved.with_user(self.user_a).create(
            {"name": "A2", "is_default": True, "filters": {}})
        other = Saved.with_user(self.user_b).create(
            {"name": "B1", "is_default": True, "filters": {}})
        self.assertNotIn("junk", first.filters)
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)
        self.assertTrue(other.is_default, "another user's default is untouched")
        for user, names in ((self.user_a, ["A1", "A2"]), (self.user_b, ["B1"]),
                            (self.manager, [])):
            options = self.env["buz.sales.dashboard.report"].with_user(
                user).get_dashboard_options()
            self.assertEqual([f["name"] for f in options["saved_filters"]], names)
        with self.assertRaises(AccessError):
            first.with_user(self.user_b).write({"name": "hacked"})
        with self.assertRaises(AccessError):
            first.with_user(self.manager).unlink()
        with self.assertRaises(AccessError):
            Saved.with_user(self.user_a).create(
                {"name": "x", "user_id": self.user_b.id})
        with self.assertRaises(AccessError):
            first.with_user(self.user_a).write({"user_id": self.user_b.id})
        first.with_user(self.user_a).write({"is_default": True})
        self.assertFalse(second.is_default)
        first.with_user(self.user_a).unlink()

    def test_custom_dates_are_bounded_and_ordered(self):
        report = self.env["buz.sales.dashboard.report"]

        def resolve(**values):
            return tuple(str(d) for d in report._resolve_dates(
                report._sanitize_filters(dict(values, date_preset="custom"))))

        today = fields.Date.context_today(report)
        self.assertEqual(resolve(), (str(today.replace(month=1, day=1)), str(today)))
        self.assertEqual(resolve(date_to="2001-05-02"), ("2001-01-01", "2001-05-02"))
        self.assertEqual(resolve(date_from="2001-06-01", date_to="2001-02-01"),
                         ("2001-02-01", "2001-06-01"))

    def test_open_document_without_access_warns_instead_of_failing(self):
        order = self._order(self.user_a, self.team_1, [(self.goods, 1, 100, 0)])
        self.env.flush_all()
        report = self.env["buz.sales.dashboard.report"]

        def open_as(user):
            return report.with_user(user).search(
                [("order_id", "=", order.id)]).action_open_document()

        self.assertEqual(open_as(self.user_a)["res_id"], order.id)
        # the leader reads the figures; the standard sales rule hides the order
        action = open_as(self.leader)
        self.assertEqual(action["tag"], "display_notification")
        self.assertIn(order.name, action["params"]["message"])

    def test_last_months_presets_end_with_the_current_month(self):
        report = self.env["buz.sales.dashboard.report"]
        today = fields.Date.context_today(report)
        end = today.replace(day=1) + relativedelta(months=1, days=-1)
        for preset, months in (("last_3_months", 3), ("last_6_months", 6)):
            clean = report._sanitize_filters({"date_preset": preset})
            self.assertEqual(clean["date_preset"], preset)
            start, stop = report._resolve_dates(clean)
            self.assertEqual(
                (start, stop),
                (today.replace(day=1) - relativedelta(months=months - 1), end))
            data = report.get_dashboard_data(clean)
            self.assertEqual(data["granularity"], "month")

    def test_saved_preset_keeps_rolling(self):
        report = self.env["buz.sales.dashboard.report"]
        clean = report._sanitize_filters({"date_preset": "this_month"})
        date_from, date_to = report._resolve_dates(clean)
        self.assertEqual(date_from.day, 1)
        self.assertEqual(date_from.month, date_to.month)
        self.assertEqual((date_to + timedelta(days=1)).day, 1, "the whole month")

    def test_system_default_is_the_current_month(self):
        report = self.env["buz.sales.dashboard.report"]
        today = fields.Date.context_today(report)
        for values in ({}, {"date_preset": "nonsense"}):
            clean = report._sanitize_filters(values)
            self.assertEqual(clean["date_preset"], "this_month")
            self.assertEqual(report._resolve_dates(clean)[0], today.replace(day=1))
        saved = report._sanitize_filters({"date_preset": "this_year"})
        self.assertEqual(saved["date_preset"], "this_year", "own choice is kept")

    # ------------------------------------------------------------ analysis page
    def test_analysis_page_adds_up_like_the_dashboard(self):
        self._dataset()
        similar = self.env["crm.team"].create({"name": "ยกเลิก BSD Team 12"})
        self._order(self.user_a, similar, [(self.goods, 1, 3200, 0)])
        self.env.flush_all()
        report = self.env["buz.sales.dashboard.report"].with_user(self.manager)
        names = [f for f in report._fields if f.startswith("amount_")]
        # what the analysis page sends: whole month from its date filter, and
        # the team picked in the search panel
        domain = [("date", ">=", "2001-03-01"), ("date", "<=", "2001-03-31"),
                  ("team_id", "in", [self.team_1.id])]
        [sums] = report._read_group(domain, aggregates=["%s:sum" % n for n in names])
        total = self._data(
            self.manager, date_from="2001-03-01", date_to="2001-03-31",
            team_ids=[self.team_1.id])["total"]
        for name, value in zip(names, sums):
            self.assertAlmostEqual(value or 0.0, total[name], msg=name)
        # a typed team name must be exact, or the look-alike team is added
        exact = report.search([("team_id", "=", "BSD Team 1")])
        self.assertEqual(exact.team_id, self.team_1)

    def test_analysis_page_opens_on_the_current_month(self):
        action = self.env.ref("buz_sales_dashboard.action_report")
        self.assertIn("search_default_date", action.context)
        arch = self.env["buz.sales.dashboard.report"].get_view(
            self.env.ref("buz_sales_dashboard.report_view_search").id, "search")["arch"]
        self.assertIn('default_period="this_month"', arch)
        self.assertIn("searchpanel", arch)
        self.assertEqual(arch.count('operator="="'), 2)

    # ------------------------------------------------------------ export
    def test_export_matches_dashboard_for_two_users(self):
        self._dataset()
        self._order(self.user_a, self.team_1, [(self.goods, 1, 7, 0)],
                    name="=1+1")
        for user in (self.user_a, self.user_b):
            report = self.env["buz.sales.dashboard.report"].with_user(user)
            sheets = read_xlsx(report._export_xlsx(self.FILTERS))
            self.assertEqual(list(sheets), [
                "รายเดือน", "รายสัปดาห์", "พนักงานขาย", "ทีมขาย", "ข้อมูลรายใบ", "เงื่อนไข"])
            data = self._data(user)
            header, rows = sheets["ข้อมูลรายใบ"][0], sheets["ข้อมูลรายใบ"][1:]
            column = header.index("ยอดขายรวม (SO+POS)")
            self.assertEqual(len(rows), data["total"]["count"])
            self.assertAlmostEqual(
                sum(r[column] for r in rows), data["total"]["amount_total"])
            self.assertEqual({r[5] for r in rows}, {user.name})
            self.assertTrue(all(isinstance(r[2], float) for r in rows), "real dates")
            for name in ("รายเดือน", "รายสัปดาห์", "พนักงานขาย", "ทีมขาย"):
                self.assertAlmostEqual(
                    sheets[name][-1][sheets[name][0].index("ยอดขายรวม (SO+POS)")],
                    data["total"]["amount_total"], msg=name)
            if user == self.user_a:
                self.assertIn("=1+1", [r[1] for r in rows])

    def test_export_of_empty_result(self):
        report = self.env["buz.sales.dashboard.report"].with_user(self.user_a)
        sheets = read_xlsx(report._export_xlsx(
            {"date_preset": "custom", "date_from": "1990-01-01",
             "date_to": "1990-01-02"}))
        self.assertEqual(len(sheets["ข้อมูลรายใบ"]), 1)


@tagged("post_install", "-at_install")
class TestSalesTarget(DashboardCommon, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_documents()
        cls._setup_journals()
        cls.boss = new_test_user(
            cls.env, "bsd_target", name="BSD Target Manager",
            groups="base.group_user,buz_sales_dashboard.group_target_manager")
        # user_b belongs to the team that the leader leads
        cls.env["crm.team.member"].create(
            {"crm_team_id": cls.team_1.id, "user_id": cls.user_b.id})

    def _target(self, owner, amount, month="2001-03-01", **values):
        level = "user" if owner._name == "res.users" else "team"
        return self.env["buz.sales.target"].with_user(self.boss).create(dict(
            values, level=level, month=month, amount=amount,
            **{"%s_id" % level: owner.id}))

    def _progress(self, user, **filters):
        self.env.flush_all()
        return self._data(user, **dict(
            {"date_from": "2001-03-01", "date_to": "2001-03-31"}, **filters))["target"]

    def _sales(self):
        self._order(self.user_a, self.team_1, [(self.goods, 1, 100, 1)])
        self._order(self.user_b, self.team_2, [(self.goods, 1, 200, 0)])
        self._order(self.user_a, self.team_1, [(self.goods, 1, 40, 0)],
                    date=datetime(2001, 4, 5, 3, 0))
        self._move(self.user_a, self.team_1, 7, name="POSBSD/T1")

    def test_target_rules(self):
        target = self._target(self.user_a, 100, month="2001-03-19")
        self.assertEqual(str(target.month), "2001-03-01")
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self._target(self.user_a, 5)
        self._target(self.user_a, 5, month="2001-04-01")
        self._target(self.team_1, 5)
        with self.assertRaises(ValidationError):
            self._target(self.team_2, 5, user_id=self.user_b.id)
        with mute_logger("odoo.sql_db"), self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self._target(self.user_b, -1)

    def test_target_access(self):
        own = self._target(self.user_a, 1)
        member = self._target(self.user_b, 2)
        led = self._target(self.team_1, 3)
        other = self._target(self.team_2, 4)
        everything = own + member + led + other
        Target = self.env["buz.sales.target"]

        def seen(user):
            return Target.with_user(user).search([("id", "in", everything.ids)])

        self.assertEqual(seen(self.user_a), own)
        self.assertEqual(seen(self.user_b), member)
        self.assertEqual(seen(self.leader), everything, "leaders read every target")
        self.assertEqual(seen(self.manager), everything)
        self.assertEqual(seen(self.boss), everything)
        # a salesperson, and seeing everything, give no right to set targets
        for user, readable in ((self.user_a, own), (self.manager, everything)):
            with self.assertRaises(AccessError):
                Target.with_user(user).create({
                    "level": "user", "user_id": user.id, "month": "2001-07-01",
                    "amount": 1})
            with self.assertRaises(AccessError):
                readable[:1].with_user(user).write({"amount": 999})
            with self.assertRaises(AccessError):
                readable[:1].with_user(user).unlink()
        (own + other).with_user(self.boss).write({"amount": 8})

    def test_team_leader_sets_targets_of_own_team_only(self):
        outsider = self._target(self.user_a, 1)
        member = self._target(self.user_b, 2)
        led = self._target(self.team_1, 3)
        other = self._target(self.team_2, 4)
        Target = self.env["buz.sales.target"].with_user(self.leader)
        (member + led).with_user(self.leader).write({"amount": 50})
        self.assertEqual((member.amount, led.amount), (50, 50))
        Target.create([
            {"level": "user", "user_id": self.user_b.id, "month": "2001-08-01",
             "amount": 1},
            {"level": "team", "team_id": self.team_1.id, "month": "2001-08-01",
             "amount": 1}])
        for values in (
                {"level": "user", "user_id": self.user_a.id, "month": "2001-08-01"},
                {"level": "team", "team_id": self.team_2.id, "month": "2001-08-01"},
                {"level": "user", "user_id": self.leader.id, "month": "2001-08-01"}):
            with self.assertRaises(AccessError), self.env.cr.savepoint():
                Target.create(dict(values, amount=1))
        for record in (outsider, other):
            with self.assertRaises(AccessError):
                record.with_user(self.leader).write({"amount": 9})
            with self.assertRaises(AccessError):
                record.with_user(self.leader).unlink()
        # they are all readable, though
        self.assertEqual(
            Target.search([("id", "in", (outsider + other).ids)]), outsider + other)
        # nor can an own record be handed over to another team or person
        for record, values in (
                (led, {"team_id": self.team_2.id, "month": "2001-09-01"}),
                (member, {"user_id": self.user_a.id, "month": "2001-09-01"})):
            with self.assertRaises(AccessError), self.env.cr.savepoint():
                record.with_user(self.leader).write(values)
            record.invalidate_recordset()
        self.assertEqual((led.team_id, member.user_id), (self.team_1, self.user_b))
        # leaving the team ends the right
        self.env["crm.team.member"].search([
            ("crm_team_id", "=", self.team_1.id),
            ("user_id", "=", self.user_b.id)]).unlink()
        with self.assertRaises(AccessError):
            member.with_user(self.leader).write({"amount": 60})
        member.with_user(self.leader).check_access_rights("write")
        led.with_user(self.leader).unlink()

    def test_team_leader_import(self):
        domain = [("month", "=", "2001-05-01")]
        data = self._file([["2001-05", "ทีม", None, "BSD Team 1", 5],
                           ["2001-05", "ทีม", None, "BSD Team 2", 5],
                           ["2001-05", "คน", "bsd_b", None, 6]])
        wizard = self.env["buz.sales.target.import"].with_user(self.leader)
        check = wizard.preview(data)
        self.assertEqual((check["ready"], check["bad_rows"]), (2, 1))
        self.assertEqual(check["errors"][0]["row"], 3)
        self.assertIn("ไม่มีสิทธิ์", check["errors"][0]["problem"])
        self.assertEqual(wizard.apply(data)["skipped"], 1)
        self.assertEqual(
            sorted(self.env["buz.sales.target"].search(domain).mapped("amount")), [5, 6])
        sheets = read_xlsx(wizard._template_xlsx())
        names = [value for row in sheets["รายชื่อ"][1:] for value in row if value]
        self.assertEqual(sorted(names), ["BSD Seller B", "BSD Team 1", "bsd_b"])

    def test_own_progress_by_default(self):
        self._sales()
        self.assertEqual(self._progress(self.user_a)["status"], "none")
        self._target(self.user_a, 500)
        result = self._progress(self.user_a)
        self.assertEqual((result["level"], result["status"]), ("user", "ok"))
        self.assertEqual((result["target"], result["actual"], result["remaining"]),
                         (500, 107, 393))
        self.assertAlmostEqual(result["percent"], 21.4)
        self.assertFalse(result["days_left"])
        # the source filter does not change the progress
        self.assertEqual(self._progress(self.user_a, sources=["pos"])["actual"], 107)
        part = self._progress(self.user_a, date_to="2001-03-12")
        self.assertEqual((part["target"], part["actual"]), (500, 100))
        self.assertTrue(any("ไม่เต็มเดือน" in note for note in part["notes"]))

    def test_over_target(self):
        self._sales()
        self._target(self.user_a, 50)
        result = self._progress(self.user_a)
        self.assertEqual((result["remaining"], result["over"]), (0, 57))

    def test_selected_people_and_months_without_target_stay_out(self):
        self._sales()
        self._target(self.user_a, 500)
        both = [self.user_a.id, self.user_b.id]
        result = self._progress(self.manager, user_ids=both, date_to="2001-04-30")
        # user_b has no target and user_a none for April: neither side counts them
        self.assertEqual((result["target"], result["actual"]), (500, 107))
        self.assertTrue(any("3 รายการ" in note for note in result["notes"]))
        self._target(self.user_a, 100, month="2001-04-01")
        self._target(self.user_b, 1000)
        result = self._progress(self.manager, user_ids=both, date_to="2001-04-30",
                                team_ids=[self.team_1.id])
        self.assertEqual((result["target"], result["actual"]), (1600, 347))

    def test_team_targets_are_not_added_to_personal_ones(self):
        self._sales()
        self._target(self.user_a, 500)
        self._target(self.team_1, 1000)
        self._target(self.team_2, 2000)
        everyone = self._progress(self.manager)
        self.assertEqual((everyone["level"], everyone["target"], everyone["actual"]),
                         ("team", 3000, 307))
        chosen = self._progress(self.manager, team_ids=[self.team_2.id])
        self.assertEqual((chosen["target"], chosen["actual"]), (2000, 200))
        leader = self._progress(self.leader)
        self.assertEqual((leader["level"], leader["target"], leader["actual"]),
                         ("team", 3000, 307))
        self.assertFalse(any("สิทธิ์เห็น" in note for note in leader["notes"]))
        # a salesperson cannot read team targets
        self.assertEqual(self._progress(
            self.user_a, team_ids=[self.team_1.id])["status"], "none")

    def test_current_month_shows_days_left(self):
        self._target(self.user_a, 3000,
                     month=fields.Date.context_today(self.boss))
        report = self.env["buz.sales.dashboard.report"].with_user(self.user_a)
        result = report.get_dashboard_data({})["target"]
        today = fields.Date.context_today(report)
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        self.assertEqual(result["days_left"], (next_month - today).days)
        self.assertAlmostEqual(
            result["per_day"], result["remaining"] / result["days_left"])
        self.assertEqual(result["notes"], [])

    def test_export_states_the_target(self):
        self._sales()
        self._target(self.user_a, 500)
        report = self.env["buz.sales.dashboard.report"].with_user(self.user_a)
        rows = read_xlsx(report._export_xlsx(dict(
            self.FILTERS, date_from="2001-03-01", date_to="2001-03-31")))["เงื่อนไข"]
        values = {row[0]: row[1] for row in rows if len(row) > 1}
        self.assertEqual((values["เป้า"], values["ทำได้"]), (500, 107))

    # ------------------------------------------------------------ import
    def _file(self, rows):
        book = openpyxl.Workbook()
        book.active.append(["เดือน", "ระดับ", "พนักงานขาย", "ทีมขาย", "เป้ายอดขาย"])
        for row in rows:
            book.active.append(row)
        output = io.BytesIO()
        book.save(output)
        return base64.b64encode(output.getvalue()).decode()

    def _import(self, rows, user=None):
        return self.env["buz.sales.target.import"].with_user(
            user or self.boss).apply(self._file(rows))

    def test_import_creates_then_updates(self):
        Target = self.env["buz.sales.target"]
        domain = [("month", "in", ["2001-05-01", "2001-06-01"])]
        result = self._import([
            ["2001-05", "คน", "bsd_a", None, "1,500.50"],
            [datetime(2001, 6, 15), "ทีม", None, "BSD Team 1", 900],
            [None, None, None, None, None],
            ["05/2001", "รายคน", "BSD Seller B", "", 0],
        ])
        self.assertEqual((result["created"], result["updated"], result["skipped"]), (3, 0, 0))
        targets = Target.search(domain)
        self.assertEqual(sorted(targets.mapped("amount")), [0, 900, 1500.5])
        result = self._import([["2001-05", "คน", "BSD_A", None, 2000]])
        self.assertEqual((result["created"], result["updated"]), (0, 1))
        self.assertEqual(Target.search_count(domain), 3)
        self.assertEqual(Target.search(
            domain + [("user_id", "=", self.user_a.id)]).amount, 2000)

    def test_preview_writes_nothing_and_apply_saves_only_good_rows(self):
        Target = self.env["buz.sales.target"]
        before = Target.search_count([])
        data = self._file([
            ["2001-05", "คน", "bsd_a", None, 10],
            ["2569-05", "คน", "bsd_a", None, 10],
            ["2001-05", "คน", "nobody@example", None, 10],
            ["2001-05", "ทีม", "bsd_a", "BSD Team 1", 10],
            ["2001-05", "คน", "bsd_a", None, 20],
            ["2001-05", "ฝ่าย", "bsd_a", None, -1],
        ])
        wizard = self.env["buz.sales.target.import"].with_user(self.boss)
        check = wizard.preview(data)
        self.assertEqual(
            (check["ready"], check["new"], check["update"], check["bad_rows"]), (1, 1, 0, 5))
        self.assertEqual({e["row"] for e in check["errors"]}, {3, 4, 5, 6, 7})
        self.assertEqual(Target.search_count([]), before)
        self.assertEqual(wizard.apply(data), {"created": 1, "updated": 0, "skipped": 5})
        self.assertEqual(Target.search_count([]), before + 1)
        self.assertEqual(Target.search(
            [("month", "=", "2001-05-01"), ("user_id", "=", self.user_a.id)]).amount, 10)

    def test_import_refuses_missing_big_or_unreadable_files(self):
        wizard = self.env["buz.sales.target.import"].with_user(self.boss)
        for data, message in (
                (False, "กรุณาเลือกไฟล์"),
                (base64.b64encode(b"x" * (5 * 1024 * 1024 + 10)).decode(), "5 MB"),
                (base64.b64encode(b"not excel").decode(), "อ่านไฟล์ไม่ได้"),
                ("%%%", "อ่านไฟล์ไม่ได้")):
            with self.assertRaisesRegex(UserError, message):
                wizard.preview(data)
        with self.assertRaisesRegex(UserError, "ไม่มีแถวที่นำเข้าได้"):
            self._import([["bad", "คน", "bsd_a", None, 1]])

    # ------------------------------------------------------------ board
    def _board(self, user, month="2001-03-01"):
        self.env.flush_all()
        board = self.env["buz.sales.target"].with_user(user).get_board(month)
        rows = {}
        for team in board["teams"]:
            rows[team["key"]] = team
            rows.update({m["key"]: m for m in team["members"]})
        rows.update({o["key"]: o for o in board["others"]})
        return board, rows

    def test_board_shows_teams_people_and_the_month_before(self):
        self._order(self.user_b, self.team_1, [(self.goods, 1, 70, 0)],
                    date=datetime(2001, 2, 10, 3, 0))
        self._order(self.user_a, self.team_2, [(self.goods, 1, 30, 0)],
                    date=datetime(2001, 2, 11, 3, 0))
        self._target(self.team_1, 500)
        self._target(self.user_b, 100, month="2001-02-01")
        board, rows = self._board(self.boss, "2001-03-20")
        self.assertEqual((board["month"], board["previous_month"], board["can_edit"]),
                         ("2001-03-01", "2001-02-01", True))
        team = rows["team:%s" % self.team_1.id]
        self.assertEqual((team["target"], team["previous_actual"], team["editable"]),
                         (500, 70, True))
        self.assertIn("user:%s" % self.user_b.id, [m["key"] for m in team["members"]])
        member = rows["user:%s" % self.user_b.id]
        self.assertEqual(
            (member["target"], member["previous_target"], member["previous_actual"]),
            (False, 100, 70))
        # sold something but belongs to no team
        self.assertIn("user:%s" % self.user_a.id, [o["key"] for o in board["others"]])

    def test_board_follows_the_rights(self):
        board, rows = self._board(self.user_a)
        self.assertEqual((board["can_edit"], board["teams"], list(rows)),
                         (False, [], ["user:%s" % self.user_a.id]))
        board, rows = self._board(self.leader)
        self.assertTrue(board["can_edit"])
        self.assertEqual(board["teams"][0]["id"], self.team_1.id, "own team first")
        self.assertTrue(rows["team:%s" % self.team_1.id]["editable"])
        self.assertTrue(rows["user:%s" % self.user_b.id]["editable"])
        self.assertFalse(rows["team:%s" % self.team_2.id]["editable"])
        board, rows = self._board(self.manager)
        self.assertFalse(board["can_edit"])
        self.assertFalse(any(row["editable"] for row in rows.values()))
        for month in ("nonsense", "1900-01-01", False):
            with self.assertRaises(UserError):
                self.env["buz.sales.target"].with_user(self.boss).get_board(month)

    def test_save_board_sets_changes_and_removes(self):
        Target = self.env["buz.sales.target"]
        domain = [("month", "=", "2001-07-01")]

        def save(user, *changes):
            return Target.with_user(user).save_board("2001-07-01", [
                {"level": level, "id": record.id, "amount": amount}
                for level, record, amount in changes])

        self.assertEqual(
            save(self.boss, ("user", self.user_a, 10), ("team", self.team_1, 0)),
            {"saved": 2, "removed": 0})
        self.assertEqual(
            save(self.boss, ("user", self.user_a, False), ("team", self.team_1, 25.5)),
            {"saved": 1, "removed": 1})
        self.assertEqual(Target.search(domain).mapped("amount"), [25.5])
        save(self.leader, ("user", self.user_b, 5), ("team", self.team_1, 30))
        for user, change in (
                (self.leader, ("team", self.team_2, 1)),
                (self.leader, ("user", self.user_a, 1)),
                (self.user_a, ("user", self.user_a, 1)),
                (self.manager, ("team", self.team_1, 1))):
            with self.assertRaises(AccessError), self.env.cr.savepoint():
                save(user, change)
        for bad in (-1, "5", None, True, 1e14, float("nan")):
            with self.assertRaises(UserError), self.env.cr.savepoint():
                save(self.boss, ("user", self.user_a, bad))
        # unknown, archived and portal owners are refused with a message
        portal = self.env["res.users"].create({
            "name": "BSD portal", "login": "bsd_portal_target",
            "groups_id": [(6, 0, [self.env.ref("base.group_portal").id])]})
        archived = self.env["res.users"].create({
            "name": "BSD left", "login": "bsd_left_target", "active": False})
        for level, owner in (("user", 2 ** 31 - 1), ("team", 2 ** 31 - 1),
                             ("user", 2 ** 40), ("user", -1),
                             ("user", portal.id), ("user", archived.id)):
            with self.assertRaises(UserError), self.env.cr.savepoint():
                Target.with_user(self.boss).save_board(
                    "2001-07-01", [{"level": level, "id": owner, "amount": 1}])
        # an old target of somebody who has left can still be removed
        Target.create({"month": "2001-07-01", "level": "user",
                       "user_id": archived.id, "amount": 3})
        self.assertEqual(
            save(self.boss, ("user", archived, False)), {"saved": 0, "removed": 1})
        # all or nothing: the good change before the refused one is undone
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            save(self.leader, ("team", self.team_1, 99), ("team", self.team_2, 99))
        self.env.invalidate_all()
        self.assertEqual(sorted(Target.search(domain).mapped("amount")), [5, 30])

    def test_a_team_leader_outside_the_groups_gets_no_template(self):
        self.leader.write({"groups_id": [Command.unlink(
            self.env.ref("buz_sales_dashboard.group_own").id)]})
        self.assertEqual(self.team_1.user_id, self.leader)
        with self.assertRaises(AccessError):
            self.env["buz.sales.target.import"].with_user(
                self.leader)._template_xlsx()

    def test_import_needs_the_right_and_template_is_empty(self):
        data = self._file([["2001-05", "คน", "bsd_a", None, 10]])
        for user in (self.manager, self.user_a):
            wizard = self.env["buz.sales.target.import"].with_user(user)
            for call in (wizard.preview, wizard.apply):
                with self.assertRaisesRegex(UserError, "ไม่มีสิทธิ์ตั้งเป้า"):
                    call(data)
            with self.assertRaises(UserError):
                wizard._template_xlsx()
        content = self.env["buz.sales.target.import"].with_user(
            self.boss)._template_xlsx()
        sheets = read_xlsx(content)
        self.assertEqual(list(sheets), ["เป้า", "วิธีกรอก", "รายชื่อ"])
        self.assertEqual(len(sheets["เป้า"]), 1, "no target is filled in")

@tagged("post_install", "-at_install")
class TestSalesDashboardLayout(DashboardCommon, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_documents()
        cls._setup_journals()
        cls.env["crm.team.member"].create(
            {"crm_team_id": cls.team_1.id, "user_id": cls.user_a.id})
        cls.env["crm.team.member"].create(
            {"crm_team_id": cls.team_1.id, "user_id": cls.user_b.id})

    def _target(self, owner, amount):
        level = "user" if owner._name == "res.users" else "team"
        return self.env["buz.sales.target"].create({
            "level": level, "%s_id" % level: owner.id, "month": "2001-03-01",
            "amount": amount})

    def _march(self, user, **filters):
        self.env.flush_all()
        return self._data(user, **dict(
            {"date_from": "2001-03-01", "date_to": "2001-03-31"}, **filters))

    def test_measures_come_grouped_with_the_leading_figure_first(self):
        options = self.env["buz.sales.dashboard.report"].with_user(
            self.manager).get_dashboard_options()
        order = [m["group"] for m in options["measures"]]
        self.assertEqual(
            sorted(set(order), key=order.index), ["sales", "wait", "pos", "invoice"])
        self.assertEqual(order, sorted(order, key=["sales", "wait", "pos", "invoice"].index))
        first = {}
        for measure in options["measures"]:
            first.setdefault(measure["group"], measure["id"])
        self.assertEqual(first, {
            "sales": "amount_total", "wait": "amount_pending", "pos": "amount_pos",
            "invoice": "amount_invoiced"})
        self.assertEqual(len(options["measures"]), 20)
        header = read_xlsx(self.env["buz.sales.dashboard.report"].with_user(
            self.manager)._export_xlsx(self.FILTERS))["ข้อมูลรายใบ"][0]
        self.assertEqual(header[8:], [m["name"] for m in options["measures"]])

    def test_a_single_month_is_shown_by_week_unless_chosen(self):
        self.assertEqual(self._march(self.manager)["granularity"], "week")
        self.assertEqual(self._data(self.manager)["granularity"], "month")
        self.assertEqual(
            self._march(self.manager, granularity="month")["granularity"], "month")

    def test_card_status_against_the_pace(self):
        report = self.env["buz.sales.dashboard.report"]
        for percent, pace, expected in (
                (100, 100, "done"), (130, 10, "done"), (60, 50, "ahead"),
                (40, 50, "behind"), (90, 100, "missed"), (False, 50, "set")):
            self.assertEqual(report._target_status(percent, pace), expected)
        today = fields.Date.context_today(report)
        month = today.replace(day=1)
        pace, days_left = report._pace([month])
        self.assertTrue(0 <= pace < 100 and days_left >= 1)
        self.assertEqual(report._pace([datetime(2001, 3, 1).date()]), (100, 0))
        self._order(self.user_a, self.team_1, [(self.goods, 1, 90, 0)])
        self._target(self.user_a, 100)
        target = self._march(self.user_a)["target"]
        self.assertEqual((target["state"], target["days_left"], target["per_day"]),
                         ("missed", 0, False))

    def test_empty_card_still_tells_what_was_sold(self):
        self._order(self.user_a, self.team_1, [(self.goods, 1, 90, 0)])
        target = self._march(self.user_a)["target"]
        self.assertEqual((target["status"], target["actual"]), ("none", 90))

    def test_team_members_against_their_own_targets(self):
        self._order(self.user_a, self.team_1, [(self.goods, 1, 100, 0)])
        self._order(self.user_a, self.team_2, [(self.goods, 1, 20, 0)])
        self._order(self.user_b, self.team_1, [(self.goods, 1, 30, 0)])
        self._order(None, self.team_1, [(self.goods, 1, 7, 0)])
        self._target(self.user_a, 80)
        self._target(self.team_1, 500)
        members = self._march(self.manager, team_ids=[self.team_1.id])["members"]
        rows = {r["id"]: r for r in members["rows"]}
        # a person's sales count in every team, as on that person's own page
        self.assertEqual(
            (rows[self.user_a.id]["actual"], rows[self.user_a.id]["over"],
             rows[self.user_a.id]["status"]), (120, 40, "done"))
        self.assertEqual(rows[self.user_b.id]["target"], False)
        self.assertEqual((rows[0]["actual"], rows[0]["status"]), (7, "none"))
        self.assertEqual(members["rows"][-1]["id"], 0)
        # "(unspecified)" is not a person without a target
        self.assertEqual(members["without_target"], 1)
        self.assertEqual(
            (members["team_target"], members["member_target"]), (500, 80))
        # a leader gets the led teams without choosing; a salesperson never does
        self.assertEqual(
            self._march(self.leader)["members"]["teams"], self.team_1.display_name)
        self.assertFalse(self._march(self.user_a, team_ids=[self.team_1.id])["members"])
        self.assertFalse(self._march(self.manager)["members"])
        self.assertFalse(
            self._march(self.manager, user_ids=[self.user_a.id])["members"])


@tagged("post_install", "-at_install")
class TestSalesDashboardHttp(DashboardCommon, HttpCase):

    def test_export_route_for_two_users(self):
        self._setup_documents()
        self._order(self.user_a, self.team_1, [(self.goods, 1, 100, 0)])
        self._order(self.user_b, self.team_2, [(self.goods, 1, 200, 0)])
        self.env.flush_all()
        for user, password, expected in (
                ("bsd_a", "bsd_a_pass_123", 100.0), ("bsd_b", "bsd_b_pass_123", 200.0)):
            self.authenticate(user, password)
            response = self.url_open("/buz_sales_dashboard/export", data={
                "filters": json.dumps(self.FILTERS),
                "csrf_token": self._csrf_token(),
            }, timeout=60)
            self.assertEqual(response.status_code, 200, response.text[:500])
            self.assertIn("attachment", response.headers["Content-Disposition"])
            rows = read_xlsx(response.content)["ข้อมูลรายใบ"]
            self.assertEqual(
                [r[rows[0].index("ยอดขายรวม (SO+POS)")] for r in rows[1:]], [expected])

    @mute_logger("odoo.http")
    def test_export_routes_refuse_a_user_without_access(self):
        new_test_user(self.env, "bsd_noaccess", password="bsd_noaccess_pass_123",
                      groups="base.group_user,sales_team.group_sale_manager",
                      context=dict(skip_partner_required_fields=True,
                                   no_reset_password=True))
        self.authenticate("bsd_noaccess", "bsd_noaccess_pass_123")
        response = self.url_open("/buz_sales_dashboard/export", data={
            "filters": json.dumps(self.FILTERS),
            "csrf_token": self._csrf_token()}, timeout=60)
        self.assertEqual(response.status_code, 403, response.text[:300])
        self.assertNotIn("Content-Disposition", response.headers)
        template = self.url_open("/buz_sales_dashboard/target_template", timeout=60)
        self.assertEqual(template.status_code, 403)

    def test_export_route_rejects_bad_json(self):
        new_test_user(self.env, "bsd_json", password="bsd_json_pass_123",
                      groups="base.group_user,sales_team.group_sale_salesman,"
                             "buz_sales_dashboard.group_own",
                      context=dict(skip_partner_required_fields=True,
                                   no_reset_password=True))
        self.authenticate("bsd_json", "bsd_json_pass_123")
        response = self.url_open("/buz_sales_dashboard/export", data={
            "filters": "notjson", "csrf_token": self._csrf_token()}, timeout=60)
        self.assertEqual(response.status_code, 400)

    def _csrf_token(self):
        from odoo.http import Request
        return Request.csrf_token(self)
