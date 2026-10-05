"""Offline checks: actual API adapter + pure validation, no Odoo/database needed."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'models' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

api = load('shopee_api')
h = load('shopee_shipping_helpers')


class TestShippingAdapter(unittest.TestCase):
    def setUp(self):
        self.client = api.ShopeeAPI('100', 'not-a-real-key', '200')

    def test_pickup_payload(self):
        with patch.object(self.client, '_request', return_value={}) as call:
            self.client.ship_order('token', 'SN1', 'PK1', pickup={'address_id': 12, 'pickup_time_id': 'slot'})
        self.assertEqual(call.call_args.kwargs['body'], {'order_sn': 'SN1', 'package_number': 'PK1', 'pickup': {'address_id': 12, 'pickup_time_id': 'slot'}})
        self.assertEqual(call.call_args.kwargs['retries'], 1)

    def test_empty_dropoff_is_preserved(self):
        with patch.object(self.client, '_request', return_value={}) as call:
            self.client.ship_order('token', 'SN1', dropoff={})
        self.assertIn('dropoff', call.call_args.kwargs['body'])

    def test_method_required_and_exclusive(self):
        for kwargs in ({}, {'pickup': {}, 'dropoff': {}}):
            with self.assertRaises(api.ShopeeAPIError):
                self.client.ship_order('token', 'SN1', **kwargs)

    def test_timeout_never_replays_shipment(self):
        with patch.object(api.requests, 'request', side_effect=api.requests.Timeout('timeout')) as call:
            with self.assertRaises(api.ShopeeAPIError):
                self.client.ship_order('token', 'SN1', dropoff={})
        self.assertEqual(call.call_count, 1)

    def test_server_error_never_replays_shipment(self):
        with patch.object(api.requests, 'request', return_value=Mock(status_code=503)) as call:
            with self.assertRaises(api.ShopeeAPIError):
                self.client.ship_order('token', 'SN1', dropoff={})
        self.assertEqual(call.call_count, 1)

    def test_binary_pdf_not_json(self):
        reply = Mock(status_code=200, content=b'%PDF-1.4\nexample')
        with patch.object(api.requests, 'request', return_value=reply) as call:
            content = self.client.download_shipping_document('token', {'order_sn': 'SN1'}, 'NORMAL_AIR_WAYBILL')
        self.assertTrue(content.startswith(b'%PDF-'))
        reply.json.assert_not_called()
        self.assertEqual(call.call_args.kwargs['json']['shipping_document_type'], 'NORMAL_AIR_WAYBILL')

    def test_json_failure_not_saved_as_pdf(self):
        reply = Mock(status_code=200, content=b'{"error":"not_ready"}')
        reply.json.return_value = {'error': 'not_ready', 'message': 'Try later'}
        with patch.object(api.requests, 'request', return_value=reply):
            with self.assertRaises(api.ShopeeAPIError):
                self.client.download_shipping_document('token', {'order_sn': 'SN1'}, 'NORMAL_AIR_WAYBILL')

    def test_json_success_is_not_a_pdf(self):
        reply = Mock(status_code=200, content=b'{}')
        reply.json.return_value = {'response': {}}
        with patch.object(api.requests, 'request', return_value=reply):
            with self.assertRaises(api.ShopeeAPIError):
                self.client.download_shipping_document('token', {'order_sn': 'SN1'}, 'NORMAL_AIR_WBILL')

    def test_create_document_not_automatically_retried(self):
        with patch.object(self.client, '_request', return_value={}) as call:
            self.client.create_shipping_document('token', {'order_sn': 'SN1'})
        self.assertEqual(call.call_args.kwargs['retries'], 1)

    def test_document_logs_do_not_contain_binary(self):
        logs = []
        self.client.log_callback = lambda **values: logs.append(values)
        with patch.object(api.requests, 'request', return_value=Mock(status_code=200, content=b'%PDF-data')):
            self.client.download_shipping_document('secret-token', {'order_sn': 'SN1'}, 'NORMAL_AIR_WAYBILL')
        self.assertEqual(logs[0]['response_data']['format'], 'pdf')
        self.assertEqual(logs[0]['request_data']['params']['access_token'], '***')


class TestShippingValidation(unittest.TestCase):
    def test_dropoff_no_extra_fields(self):
        self.assertEqual(h.validate_choice({'response': {'info_needed': {'dropoff': []}}}, 'dropoff', {}), {})

    def test_sender_required(self):
        data = {'response': {'info_needed': {'dropoff': ['sender_real_name']}}}
        with self.assertRaises(h.ShippingValidationError):
            h.validate_choice(data, 'dropoff', {})
        self.assertEqual(h.validate_choice(data, 'dropoff', {}, ' Sender ')['sender_real_name'], 'Sender')

    def test_pickup_slots_remain_distinct(self):
        data = {'response': {'info_needed': {'pickup': ['address_id', 'pickup_time_id']}, 'pickup': {'address_list': [
            {'address_id': 1, 'time_slot_list': [{'pickup_time_id': 'AM'}, {'pickup_time_id': 'PM'}]}
        ]}}}
        choices = h.shipping_choices(data)
        self.assertEqual(len(choices), 2)
        self.assertEqual(h.validate_choice(data, 'pickup', choices[1][2])['pickup_time_id'], 'PM')
        with self.assertRaises(h.ShippingValidationError):
            h.validate_choice(data, 'pickup', {'address_id': 1, 'pickup_time_id': 'EXPIRED'})

    def test_required_branch_not_guessed(self):
        with self.assertRaises(h.ShippingValidationError):
            h.shipping_choices({'response': {'info_needed': {'dropoff': ['branch_id']}}})

    def test_unsupported_carrier_not_guessed(self):
        for needed in ({'non_integrated': ['tracking_number']}, {'pickup': ['extra_unknown_field']}):
            with self.assertRaises(h.ShippingValidationError):
                h.shipping_choices({'response': {'info_needed': needed}})

    def test_per_order_document_error(self):
        with self.assertRaises(h.ShippingValidationError):
            h.document_result({'response': {'result_list': [{'order_sn': 'SN1', 'fail_error': 'bad', 'fail_message': 'Unavailable'}]}}, 'SN1')

    def test_missing_result_not_success(self):
        with self.assertRaises(h.ShippingValidationError):
            h.document_result({'response': {'result_list': [{'order_sn': 'OTHER'}]}}, 'SN1')

    def test_error_list_is_checked(self):
        with self.assertRaises(h.ShippingValidationError):
            h.document_result({'response': {'error_list': [{'order_sn': 'SN1', 'fail_error': 'bad'}]}}, 'SN1')

    def test_ready_document_result(self):
        self.assertEqual(h.document_result({'response': {'result_list': [{'order_sn': 'SN1', 'status': 'READY'}]}}, 'SN1')['status'], 'READY')

    def test_split_packages_blocked(self):
        with self.assertRaises(h.ShippingValidationError):
            h.order_detail({'response': {'order_list': [{'order_sn': 'SN1', 'package_list': [{}, {}]}]}}, 'SN1')

    def test_already_arranged_order(self):
        self.assertTrue(h.shipment_already_arranged({'order_status': 'PROCESSED'}, {}))
        self.assertTrue(h.shipment_already_arranged({'order_status': 'READY_TO_SHIP'}, {'logistics_status': 'LOGISTICS_REQUEST_CREATED'}))
        self.assertFalse(h.shipment_already_arranged({'order_status': 'READY_TO_SHIP'}, {'logistics_status': 'LOGISTICS_NOT_START'}))

    def test_duplicate_order_details_rejected(self):
        with self.assertRaises(h.ShippingValidationError):
            h.order_detail({'response': {'order_list': [{'order_sn': 'SN1'}, {'order_sn': 'SN1'}]}}, 'SN1')

if __name__ == '__main__':
    unittest.main(verbosity=2)
