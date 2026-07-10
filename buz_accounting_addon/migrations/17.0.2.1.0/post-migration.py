# Backfill the new stored M2M account.payment.voucher.line.payment_ids
# (previously a broken non-stored compute) and recompute stored amounts
# that were corrupted by the old compute returning every payment in the DB.
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    lines = env['account.payment.voucher.line'].search([('move_id', '!=', False)])
    _logger.info("Backfilling payment links for %d payment voucher lines", len(lines))
    for line in lines:
        payments = line.move_id._get_reconciled_payments()
        # Also include payments explicitly linked to the parent voucher
        payments |= line.voucher_id.payment_ids.filtered(lambda p: p.state == 'posted')
        if payments:
            line.payment_ids = [(6, 0, payments.ids)]

    # Recompute stored values that depended on the broken compute
    all_lines = env['account.payment.voucher.line'].search([])
    all_lines._compute_payment_state()

    vouchers = env['account.payment.voucher'].search([])
    vouchers._compute_amount_paid()
    vouchers._compute_amount_residual()
    vouchers._compute_payment_state()
    _logger.info("Recomputed payment state/amounts for %d payment vouchers", len(vouchers))
