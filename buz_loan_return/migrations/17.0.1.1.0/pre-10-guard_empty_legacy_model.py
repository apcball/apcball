"""Guard and remove the empty legacy BG/RBG operation type model metadata."""

import logging

from odoo import SUPERUSER_ID, api
from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG


_logger = logging.getLogger(__name__)
_TABLE = 'buz_loan_return_operation_type'
_MODEL = 'buz.loan.return.operation.type'


def migrate(cr, version):
    cr.execute('SELECT to_regclass(%s)', ['public.%s' % _TABLE])
    table_exists = bool(cr.fetchone()[0])
    if table_exists:
        cr.execute('SELECT COUNT(*) FROM %s' % _TABLE)
        row_count = cr.fetchone()[0]
        if row_count:
            raise RuntimeError(
                'Refusing to remove %s: %s configuration row(s) still exist.'
                % (_MODEL, row_count)
            )

        cr.execute(
            """
            SELECT constraint_row.conname, constraint_row.conrelid::regclass::text
              FROM pg_constraint AS constraint_row
             WHERE constraint_row.contype = 'f'
               AND constraint_row.confrelid = to_regclass(%s)
               AND constraint_row.conrelid <> to_regclass(%s)
            """,
            ['public.%s' % _TABLE, 'public.%s' % _TABLE],
        )
        foreign_keys = cr.fetchall()
        if foreign_keys:
            raise RuntimeError(
                'Refusing to remove %s: incoming foreign key(s) exist: %s'
                % (_MODEL, foreign_keys)
            )

    cr.execute(
        'SELECT model, name FROM ir_model_fields WHERE relation = %s',
        [_MODEL],
    )
    related_fields = cr.fetchall()
    if related_fields:
        raise RuntimeError(
            'Refusing to remove %s: other model fields still reference it: %s'
            % (_MODEL, related_fields)
        )

    # ใช้ ORM ลบ metadata ของโมเดลเพื่อให้ Odoo จัดการ fields และ selection metadata
    # ส่วนตารางจริงจะถูกลบภายหลัง หลังตรวจซ้ำว่าไม่มีข้อมูลหรือ FK
    env = api.Environment(cr, SUPERUSER_ID, {MODULE_UNINSTALL_FLAG: True})
    model_record = env['ir.model'].search([('model', '=', _MODEL)])
    if model_record:
        model_record.unlink()

    remaining = env['ir.model'].search_count([('model', '=', _MODEL)])
    if remaining:
        raise RuntimeError('Odoo did not remove ir.model metadata for %s.' % _MODEL)

    _logger.info(
        'Removed empty legacy model metadata for %s; its table will be checked '
        'and dropped in the end migration.',
        _MODEL,
    )