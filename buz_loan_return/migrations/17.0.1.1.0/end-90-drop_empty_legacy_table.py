"""Drop the empty legacy config table after Odoo removes its model metadata."""

import logging


_logger = logging.getLogger(__name__)
_TABLE = 'buz_loan_return_operation_type'
_MODEL = 'buz.loan.return.operation.type'


def migrate(cr, version):
    # ตรวจซ้ำก่อนลบเฉพาะตารางตั้งค่าที่ว่างและไม่มี Foreign Key
    cr.execute('SELECT to_regclass(%s)', ['public.%s' % _TABLE])
    table_exists = bool(cr.fetchone()[0])
    if table_exists:
        cr.execute('SELECT COUNT(*) FROM %s' % _TABLE)
        row_count = cr.fetchone()[0]
        if row_count:
            raise RuntimeError(
                'Refusing to drop %s: %s row(s) appeared during upgrade.'
                % (_TABLE, row_count)
            )

        cr.execute(
            """
            SELECT conname, conrelid::regclass::text
              FROM pg_constraint
             WHERE contype = 'f'
               AND confrelid = to_regclass(%s)
               AND conrelid <> to_regclass(%s)
            """,
            ['public.%s' % _TABLE, 'public.%s' % _TABLE],
        )
        foreign_keys = cr.fetchall()
        if foreign_keys:
            raise RuntimeError(
                'Refusing to drop %s: incoming foreign key(s) exist: %s'
                % (_TABLE, foreign_keys)
            )

        # ไม่ใช้ CASCADE เพื่อให้ฐานข้อมูลปฏิเสธการลบ หากมี dependency ที่ไม่คาดไว้
        cr.execute('DROP TABLE %s' % _TABLE)
        _logger.info('Dropped empty legacy table %s.', _TABLE)

    cr.execute('SELECT COUNT(*) FROM ir_model WHERE model = %s', [_MODEL])
    if cr.fetchone()[0]:
        raise RuntimeError('Odoo did not remove ir.model metadata for %s.' % _MODEL)

    cr.execute('SELECT COUNT(*) FROM ir_model_fields WHERE model = %s', [_MODEL])
    if cr.fetchone()[0]:
        raise RuntimeError(
            'Odoo did not remove ir.model.fields metadata for %s.' % _MODEL
        )