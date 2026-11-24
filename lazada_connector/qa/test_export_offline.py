"""Offline checks of the Lazada Seller Center export parser (no Odoo needed)."""
import importlib.util
from datetime import datetime
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('h', ROOT / 'models' / 'lazada_export_helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

HEADERS = ['orderItemId', 'orderNumber', 'createTime', 'status', 'shippingName', 'shippingAddress',
           'shippingAddress3', 'shippingAddress4', 'shippingAddress5', 'shippingPhone',
           'shippingPostCode', 'shippingCountry', 'billingName', 'billingAddr', 'billingAddr3',
           'taxCode', 'branchNumber', 'taxInvoiceRequested', 'unitPrice', 'paidPrice',
           'sellerDiscountTotal', 'shippingFee']


def row(number, **values):
    data = dict(zip(HEADERS, ['1', number, '07 Oct 2026 21:14', 'pending', 'A B', '1 Road',
                              'นนทบุรี/ Nonthaburi', 'ปากเกร็ด/ Pak Kret', '11120', '660812345678',
                              '11120', 'Thailand', 'A B', '1 Road', 'นนทบุรี/ Nonthaburi',
                              '0105551234567', '', 'true', '100.00', '90.00', '-10.00', '5.00']))
    data.update(values)
    return [data[key] for key in HEADERS]


class TestExportParser(unittest.TestCase):
    def test_order_shape(self):
        order = h.orders_from_rows(HEADERS, [row('9001')])['9001']
        self.assertEqual(order['order_id'], '9001')
        self.assertEqual(order['created_at'], datetime(2026, 10, 7, 21, 14))
        self.assertEqual(order['address_shipping']['address3'], 'นนทบุรี/ Nonthaburi')
        self.assertEqual(order['address_shipping']['address5'], '11120')
        self.assertEqual(order['address_billing']['address1'], '1 Road')
        self.assertEqual(order['tax_code'], '0105551234567')
        self.assertEqual(order['payment'], {
            'source': 'excel', 'products_total': 100.0, 'shipping': 5.0, 'voucher_amount': 10.0,
            'voucher_codes': [], 'fees': [], 'net_income': None,
        })

    def test_items_of_one_order_add_up_and_cancelled_items_are_left_out(self):
        orders = h.orders_from_rows(HEADERS, [
            row('9002'), row('9002', unitPrice='50.00', sellerDiscountTotal='-5', shippingFee='0'),
            row('9002', status='canceled', unitPrice='999'),
        ])
        payment = orders['9002']['payment']
        self.assertEqual((payment['products_total'], payment['voucher_amount'], payment['shipping']),
                         (150.0, 15.0, 5.0))
        self.assertEqual(orders['9002']['statuses'], ['pending', 'pending', 'canceled'])

    def test_tax_code_only_when_requested(self):
        order = h.orders_from_rows(HEADERS, [row('9003', taxInvoiceRequested='false')])['9003']
        self.assertEqual(order['tax_code'], '')

    def test_title_case_headers_and_missing_money(self):
        headers = ['Order Number', 'Shipping Address', 'Shipping Name']
        orders = h.orders_from_rows(headers, [['9004', '1 Road', 'A B']])
        self.assertEqual(orders['9004']['address_shipping']['address1'], '1 Road')
        self.assertFalse(orders['9004']['payment'])

    def test_other_file_rejected(self):
        with self.assertRaises(h.ExportFormatError):
            h.orders_from_rows(['SKU', 'Stock'], [['A', '1']])

    def test_time_formats(self):
        self.assertEqual(h.parse_create_time('2026-10-07 21:14:05'), datetime(2026, 10, 7, 21, 14, 5))
        self.assertIsNone(h.parse_create_time('yesterday'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
