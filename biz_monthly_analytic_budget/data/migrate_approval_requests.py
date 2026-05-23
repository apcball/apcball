#!/usr/bin/env python3
"""
Migration Script: Recalculate legacy Monthly Budget Approval Requests.

อ่านข้อมูลจากเอกสารต้นทางของ request แล้วคำนวณค่าเหล่านี้ใหม่:
- amount_requested
- amount_analytic
- amount_limit
- amount_used
- amount_reserved
- amount_overage
- budget_line_name
- plan_id

รองรับ request ที่ผูกกับ:
- PR
- PO
- Bill

วิธีรัน:
  docker exec -i odoo python3 /mnt/extra-addons/biz_monthly_analytic_budget/data/migrate_approval_requests.py
"""

import os
import sys
import logging

os.environ['ODOO_SKIP_MODULE_WARNINGS'] = '1'

from odoo import api, SUPERUSER_ID, registry

_logger = logging.getLogger(__name__)

DB = 'MOG_LIVE'


def _format_value(value):
    if isinstance(value, float):
        return f'{value:,.2f}'
    return repr(value)


def _doc_label(req):
    if req.document_type == 'pr' and req.ref_pr_id:
        return 'PR', req.ref_pr_id.name or str(req.ref_pr_id.id)
    if req.document_type == 'po' and req.ref_po_id:
        return 'PO', req.ref_po_id.name or str(req.ref_po_id.id)
    if req.document_type == 'bill' and req.ref_bill_id:
        return 'Bill', req.ref_bill_id.name or str(req.ref_bill_id.id)
    return req.document_type.upper(), '-'


def main():
    with registry(DB).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})

        ApprovalReq = env['buz.monthly.budget.approval.request'].sudo()
        requests = ApprovalReq.search([
            ('document_type', 'in', ('pr', 'po', 'bill')),
            '|', '|',
            ('ref_pr_id', '!=', False),
            ('ref_po_id', '!=', False),
            ('ref_bill_id', '!=', False),
        ])

        updated = []
        skipped = []

        for req in requests:
            label, doc_name = _doc_label(req)
            old_vals = {
                'amount_requested': req.amount_requested,
                'amount_analytic': req.amount_analytic,
                'amount_limit': req.amount_limit,
                'amount_used': req.amount_used,
                'amount_reserved': req.amount_reserved,
                'amount_overage': req.amount_overage,
                'budget_line_name': req.budget_line_name,
                'plan_id': req.plan_id.id,
            }

            vals, _plan_ids = req._prepare_amounts_from_source_document()
            if not vals:
                sys.stdout.write(
                    f'SKIP  {req.name:<18} {label}={doc_name:<20} cannot recompute from current source document\n'
                )
                skipped.append(req.id)
                continue

            changes = {}
            for field_name, old_value in old_vals.items():
                new_value = vals.get(field_name, old_value)
                if isinstance(old_value, float):
                    if abs(old_value - new_value) > 0.01:
                        changes[field_name] = (old_value, new_value)
                elif old_value != new_value:
                    changes[field_name] = (old_value, new_value)

            if req.name in (False, 'New'):
                req._ensure_approval_request_sequence()
                new_name = env['ir.sequence'].next_by_code('buz.monthly.budget.approval.request') or req.name
                if new_name != req.name:
                    vals['name'] = new_name
                    changes['name'] = (req.name, new_name)

            if not changes:
                sys.stdout.write(f'SAME  {req.name:<18} {label}={doc_name:<20} no changes needed\n')
                continue

            req.write(vals)

            parts = [
                f'{field_name} {_format_value(old)}→{_format_value(new)}'
                for field_name, (old, new) in changes.items()
            ]
            sys.stdout.write(
                f'FIX   {req.name:<18} {label}={doc_name:<20} {len(changes)} field(s): '
                f'{", ".join(parts)}\n'
            )
            updated.append(req.id)

        cr.commit()

        sys.stdout.write(f'\n{"=" * 60}\n')
        sys.stdout.write(f'Total records updated: {len(updated)}\n')
        sys.stdout.write(f'Total records skipped: {len(skipped)}\n')
        sys.stdout.write(f'{"=" * 60}\n')


if __name__ == '__main__':
    main()
