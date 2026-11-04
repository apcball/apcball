# -*- coding: utf-8 -*-
import io
import json

from odoo import _, http
from odoo.http import content_disposition, request


class BuzAssetDashboard(http.Controller):
    """Thin JSON/HTTP layer. All logic and access checks live in
    ``buz.asset.dashboard.service`` and run as the logged-in user."""

    @http.route('/buz_asset/dashboard/data', type='json', auth='user')
    def data(self, filters=None):
        return request.env['buz.asset.dashboard.service'].get_data(filters or {})

    @http.route('/buz_asset/dashboard/export', type='http', auth='user', methods=['POST'])
    def export_xlsx(self, filters='{}', **kwargs):
        import xlsxwriter
        data = request.env['buz.asset.dashboard.service'].get_data(json.loads(filters or '{}'))
        out = io.BytesIO()
        book = xlsxwriter.Workbook(out, {'in_memory': True})
        bold, money = book.add_format({'bold': True}), book.add_format({'num_format': '#,##0.00'})

        sheet = book.add_worksheet(_('สรุป')[:31])
        sheet.write(0, 0, _('ณ วันที่'), bold)
        sheet.write(0, 1, data['meta']['as_of'])
        labels = [('asset_count', _('จำนวนทรัพย์สิน')), ('gross_cost', _('ราคาทุนรวม')),
                  ('accumulated_depreciation', _('ค่าเสื่อมราคาสะสม (ลงบัญชีแล้ว)')),
                  ('nbv', _('มูลค่าตามบัญชีสุทธิ (NBV)')), ('pending_depreciation', _('ค่าเสื่อมรอลงบัญชี')),
                  ('warranty_expiring', _('การรับประกันใกล้หมดอายุ (30 วัน)'))]
        for i, (key, label) in enumerate(labels, start=2):
            sheet.write(i, 0, label, bold)
            sheet.write(i, 1, data['kpis'][key], money)
        sheet.set_column(0, 0, 44)
        sheet.set_column(1, 1, 18)

        def table(name, headers, rows):
            ws = book.add_worksheet(name[:31])
            for c, h in enumerate(headers):
                ws.write(0, c, h, bold)
            for r, row in enumerate(rows, start=1):
                for c, value in enumerate(row):
                    ws.write(r, c, value)
            ws.set_column(0, len(headers), 24)

        t = data['tables']
        table(_('ใกล้หมดอายุการใช้งาน'), [_('รหัส'), _('ชื่อ'), _('หมวด'), _('วันสิ้นอายุ'), 'NBV'],
              [(r['code'], r['name'], r['category'], r['end_date'], r['nbv']) for r in t['end_of_life']])
        table(_('การรับประกัน'), [_('ทรัพย์สิน'), _('เลขที่'), _('วันสิ้นสุด'), _('เหลือ (วัน)')],
              [(r['asset'], r['reference'], r['date_end'], r['days_left']) for r in t['warranty']])
        table(_('รอดำเนินการทางบัญชี'), [_('รายการ'), _('จำนวน')],
              [(r['label'], r['count']) for r in t['pending_actions']])
        book.close()
        return request.make_response(out.getvalue(), headers=[
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', content_disposition('asset_dashboard_%s.xlsx' % data['meta']['as_of']))])
