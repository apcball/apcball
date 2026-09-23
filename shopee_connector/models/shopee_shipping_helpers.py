"""Pure validation used by the fulfillment worker and offline tests."""


class ShippingValidationError(ValueError):
    pass


def response(data):
    if not isinstance(data, dict) or data.get('error'):
        raise ShippingValidationError('Invalid or failed Shopee response.')
    value = data.get('response')
    if not isinstance(value, dict):
        raise ShippingValidationError('Missing Shopee response object.')
    return value


def document_result(data, order_sn):
    value = response(data)
    for row in value.get('error_list') or []:
        if row.get('order_sn') == order_sn:
            raise ShippingValidationError(str(row.get('fail_message') or row.get('message') or row.get('fail_error') or row))
    rows = [r for r in value.get('result_list') or [] if r.get('order_sn') == order_sn]
    if len(rows) != 1:
        raise ShippingValidationError('Shopee returned no unique document result for this order.')
    row = rows[0]
    if row.get('fail_error') or row.get('error'):
        raise ShippingValidationError(str(row.get('fail_message') or row.get('message') or row.get('fail_error') or row.get('error')))
    return row


def shipping_choices(data):
    """Return labelled, explicit choices; never choose the first pickup slot."""
    value = response(data)
    needed = value.get('info_needed') or {}
    choices = []
    if 'dropoff' in needed:
        required = set(needed.get('dropoff') or [])
        if required <= {'branch_id', 'sender_real_name'}:
            branches = (value.get('dropoff') or {}).get('branch_list') or []
            if 'branch_id' not in required:
                choices.append(('Drop off / นำส่งเอง', 'dropoff', {}))
            for branch in branches:
                if branch.get('branch_id') is not None:
                    choices.append((str(branch.get('branch_name') or branch['branch_id']),
                                    'dropoff', {'branch_id': branch['branch_id']}))
    if 'pickup' in needed:
        required = set(needed.get('pickup') or [])
        if required <= {'address_id', 'pickup_time_id'}:
            for address in (value.get('pickup') or {}).get('address_list') or []:
                address_id = address.get('address_id')
                if address_id is None:
                    continue
                title = str(address.get('address') or address.get('full_address') or address_id)
                slots = address.get('time_slot_list') or []
                if not slots and 'pickup_time_id' not in required:
                    choices.append((f'Pickup / นัดรับ: {title}', 'pickup', {'address_id': address_id}))
                for slot in slots:
                    slot_id = slot.get('pickup_time_id')
                    if slot_id is not None:
                        label = slot.get('time_text') or slot.get('date') or slot_id
                        choices.append((f'Pickup / นัดรับ: {title} — {label}', 'pickup',
                                        {'address_id': address_id, 'pickup_time_id': str(slot_id)}))
    if not choices:
        raise ShippingValidationError('No supported pickup/dropoff option. Check the carrier in Seller Centre (non-integrated channels are not supported).')
    return choices


def validate_choice(data, method, payload, sender_name=''):
    choices = shipping_choices(data)
    if not any(m == method and p == payload for _, m, p in choices):
        raise ShippingValidationError('Shipping option expired or changed. Reload options and select again.')
    result = dict(payload)
    required = set(response(data).get('info_needed', {}).get(method) or [])
    if 'sender_real_name' in required:
        if not sender_name.strip():
            raise ShippingValidationError('This carrier requires the sender name.')
        result['sender_real_name'] = sender_name.strip()
    return result


def order_detail(data, order_sn):
    rows = [row for row in response(data).get('order_list') or [] if row.get('order_sn') == order_sn]
    if len(rows) != 1:
        raise ShippingValidationError('Shopee returned no unique order detail.')
    row = rows[0]
    packages = row.get('package_list') or []
    if len(packages) > 1:
        raise ShippingValidationError('Split-package orders must be handled in Seller Centre in this version.')
    return row, packages[0] if packages else {}


def shipment_already_arranged(detail, package):
    return detail.get('order_status') in {'PROCESSED', 'SHIPPED', 'COMPLETED'} or package.get('logistics_status') in {
        'LOGISTICS_REQUEST_CREATED', 'LOGISTICS_PICKUP_DONE', 'LOGISTICS_PICKUP_RETRY',
        'LOGISTICS_DELIVERY_DONE',
    }
