import re
from datetime import datetime, time

from odoo import models

HEAD = ['วันที่', 'เลขที่', 'จำนวนรับ', '@', 'มูลค่ารับ', 'จำนวนจ่าย', '@',
        'มูลค่าจ่าย', 'จำนวนคงเหลือ', '@', 'มูลค่าคงเหลือ']
EXTRA_HEAD = ['คลังสินค้า', 'ล็อต (PO ต้นทาง)', 'วันที่เข้าคลัง', 'ต้นทุนรวม LC (All-in @)',
              'วันที่บันทึกในระบบ', 'ย้อนหลัง', 'จำนวนตามระบบ', 'มูลค่าตามระบบ', 'ผลต่างจำนวน',
              'ผลต่างมูลค่า']
CHECK_COLS = ('ledger_qty', 'sys_qty', 'lot_qty', 'diff_sys_qty', 'ledger_value', 'sys_value',
              'lot_value', 'diff_sys_value', 'diff_lot_value', 'backdated_count', 'short_qty',
              'lc_moved_value')
CHECK_HEAD = ['รหัสสินค้า', 'ชื่อสินค้า', 'คลังสินค้า', 'จำนวนตามบัญชี', 'จำนวนคิวระบบ',
              'จำนวนล็อตรายงาน', 'ผลต่างจำนวน (ระบบ−บัญชี)', 'มูลค่าตามบัญชี', 'มูลค่าคิวระบบ',
              'มูลค่าล็อตรายงาน', 'ผลต่างมูลค่า (ระบบ−บัญชี)', 'ผลต่างมูลค่า (ล็อต−บัญชี)',
              'รายการย้อนหลัง', 'จำนวนจ่ายก่อนรับ', 'landed cost ล็อตหมดแล้ว', 'สาเหตุที่พบ']

# ' (ล็อต A, B +N)' / ' (ลงล็อต A)' suffix the engine puts on a movement's document
LOT_SUFFIX = re.compile(r'\s*\((?:ลง)?ล็อต (.*)\)\s*$')


def split_lot(ref):
    """'DOC (ล็อต LOT)' -> ('LOT', 'DOC'); no lot suffix -> (ref, '')."""
    m = LOT_SUFFIX.search(ref)
    if not m:
        return ref, ''
    return m.group(1).strip(), ref[:m.start()].strip()


def move_cells(doc_ref):
    """Movement / ending-lot row -> (document number, lot). The document column
    shows the transaction (transfer / bill / sale / receipt); the lot it belongs
    to goes to its own column. No lot suffix: the document is the lot, nothing to add."""
    lot, ref = split_lot((doc_ref or '').split(' · ')[0])
    return (ref, lot) if ref else (lot, '')


class PoLotXlsx(models.AbstractModel):
    _name = 'report.buz_stock_po_lot_report.po_lot_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Tax stock report xlsx'

    def get_workbook_options(self):
        # rows are written strictly top-down -> constant memory is safe
        opts = super().get_workbook_options() or {}
        opts['constant_memory'] = True
        return opts

    def generate_xlsx_report(self, workbook, data, wizards):
        for wiz in wizards:
            sheet = workbook.add_worksheet('Stock')
            bold = workbook.add_format({'bold': True})
            head = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
            num = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
            cost = workbook.add_format({'num_format': '#,##0.0000', 'border': 1})
            tot = workbook.add_format({'num_format': '#,##0.00', 'border': 1, 'bold': True})
            txt = workbook.add_format({'border': 1})
            doc = workbook.add_format({'border': 1, 'text_wrap': True, 'valign': 'top'})
            dat = workbook.add_format({'num_format': 'dd/mm/yyyy', 'border': 1})
            n_sys = workbook.add_format({'num_format': '#,##0.00', 'border': 1, 'bg_color': '#FFF2CC'})
            sheet.set_column('A:A', 12)
            sheet.set_column('B:B', 44)
            sheet.set_column('C:K', 14)
            comp = wiz.company_id
            r = 0
            sheet.write(r, 0, 'รายงานสินค้าและวัตถุดิบ', bold)
            r += 1
            sheet.write(r, 0, 'ปีภาษี:', bold)
            sheet.write(r, 1, 'ปี %s  (ช่วงวันที่ %s - %s)' % (
                wiz.date_to.year + 543, wiz.date_from, wiz.date_to))
            r += 1
            sheet.write(r, 0, 'เลขประจำตัวผู้เสียภาษีอากร', bold)
            sheet.write(r, 1, comp.vat or '')
            r += 1
            sheet.write(r, 0, 'ชื่อผู้ประกอบการ:', bold)
            sheet.write(r, 1, '%s;%s' % (comp.name, comp.vat or ''))
            r += 1
            sheet.write(r, 0, '□  สำนักงานใหญ่    □ สาขาที่')
            if wiz._show_system():
                r += 1
                sheet.write(r, 0, 'คอลัมน์ผลต่าง: แถวล็อตปลายงวด = ระบบ − ล็อตในรายงาน, '
                                  'แถวรวม = ระบบ − บัญชี (ยอดตามระบบคือ ณ วันนี้)')
            r += 2
            last_model = None
            # one pass: group lines by product (keeps line order), no per-product filtered()
            fields_ = ['product_id', 'seq', 'model_code', 'line_type', 'date', 'doc_ref',
                       'in_qty', 'in_cost', 'in_value', 'out_qty', 'out_cost', 'out_value',
                       'bal_qty', 'bal_cost', 'bal_value']
            cols = ['product_id'] + fields_[1:] + [
                'warehouse_id', 'wh_date', 'in_allin', 'rec_date', 'backdated', 'has_sys',
                'sys_qty', 'sys_value', 'diff_qty', 'diff_value']
            numeric = fields_[6:]  # in_qty .. bal_value
            # warehouse column (lot / movement rows are per warehouse)
            show_wh = True
            wh_names = {w.id: w.name for w in self.env['stock.warehouse'].with_context(
                active_test=False).search([])}
            sheet.set_column('L:L', 24)
            sheet.set_column('M:M', 34)
            sheet.set_column('N:N', 14)
            sheet.set_column('O:O', 16)
            sheet.set_column('P:P', 18)
            sheet.set_column('Q:Q', 10)
            sheet.set_column('R:U', 16)
            self.env.cr.execute(
                'SELECT %s FROM buz_po_lot_line WHERE wizard_id = %%s ORDER BY product_id, seq'
                % ', '.join(cols), (wiz.id,))
            grouped = {}
            for tup in self.env.cr.fetchall():
                rec = dict(zip(cols, tup))
                for k in numeric:
                    rec[k] = rec[k] or 0.0
                grouped.setdefault(rec['product_id'], []).append(rec)
            # same product order as the on-screen list (product model _order)
            products = self.env['product.product'].with_context(active_test=False).search(
                [('id', 'in', list(grouped))])
            for prod in products:
                lines = grouped[prod.id]
                categ = prod.categ_id
                model = lines[0]['model_code'] or ''
                if model != last_model:
                    sheet.write(r, 0, 'รุ่นสินค้า', bold)
                    sheet.write(r, 1, model, bold)
                    r += 1
                    last_model = model
                sheet.write(r, 0, 'รหัสสินค้า', bold)
                sheet.write(r, 1, prod.default_code or '')
                r += 1
                sheet.write(r, 0, 'ชื่อสินค้า/วัตถุดิบ', bold)
                sheet.write(r, 1, prod.name or '')
                r += 1
                sheet.write(r, 0, 'ชนิดสินค้า', bold)
                sheet.write(r, 1, categ.name or '')
                r += 1
                sheet.write(r, 0, 'ประเภทสินค้า', bold)
                sheet.write(r, 1, categ.parent_id.name or '')
                r += 1
                for c, h in enumerate(HEAD + EXTRA_HEAD):
                    sheet.write(r, c, h, head)
                r += 1
                lot_header_done = False
                for l in lines:
                    lt = l['line_type']
                    if lt == 'lot' and not lot_header_done:
                        r += 1
                        sheet.write(r, 0, 'สินค้าปลายงวด', bold)
                        r += 1
                        lot_header_done = True
                    n = tot if lt == 'total' else num
                    if lt == 'move' and l['rec_date']:
                        sheet.write_datetime(r, 15, datetime.combine(l['rec_date'], time.min), dat)
                        sheet.write(r, 16, 'ย้อนหลัง' if l['backdated'] else '', txt)
                    if l['has_sys']:
                        for c, k in enumerate(('sys_qty', 'sys_value', 'diff_qty', 'diff_value'), 17):
                            sheet.write(r, c, l[k] or 0.0, n_sys)
                    if show_wh:
                        sheet.write(r, 11, wh_names.get(l['warehouse_id'], '') if lt in (
                            'move', 'lot', 'lotbal') else '', txt)
                    if lt == 'move' and l['in_allin']:
                        sheet.write(r, 14, l['in_allin'], cost)
                    if lt in ('lot', 'lotbal') and l['wh_date']:
                        sheet.write_datetime(r, 13, datetime.combine(l['wh_date'], time.min), dat)
                    if l['date']:
                        sheet.write_datetime(r, 0, datetime.combine(l['date'], time.min), dat)
                    else:
                        sheet.write(r, 0, '', txt)
                    # movement and ending-lot rows show the bare document number (no
                    # warehouse tag) so a lot with stock left can be identified; the lot
                    # snapshots under every movement (lotbal) keep only the date
                    if lt == 'lotbal' and l['date']:
                        sheet.write(r, 1, '', doc)
                    elif lt == 'move' or (lt == 'lot' and l['date']):
                        # document number (transfer / bill / sale) in the first
                        # column, the origin lot it belongs to in its own column
                        number, lot = move_cells(l['doc_ref'])
                        sheet.write(r, 1, number, doc)
                        if lot and show_wh:
                            sheet.write(r, 12, lot, doc)
                    else:
                        sheet.write(r, 1, l['doc_ref'] or '', doc)
                    if lt == 'lotbal':
                        for c in range(2, 8):
                            sheet.write(r, c, '', txt)
                        sheet.write(r, 8, l['bal_qty'], num)
                        sheet.write(r, 9, '', txt)
                        sheet.write(r, 10, l['bal_value'], num)
                        r += 1
                        continue
                    if lt in ('move', 'total'):
                        # like the sample: the unused side (in or out) stays blank
                        has_in = lt == 'total' or l['in_qty'] or l['in_value']
                        has_out = lt == 'total' or l['out_qty'] or l['out_value']
                        for c, val, f, ok in ((2, l['in_qty'], n, has_in), (3, l['in_cost'], cost, has_in),
                                              (4, l['in_value'], n, has_in), (5, l['out_qty'], n, has_out),
                                              (6, l['out_cost'], cost, has_out), (7, l['out_value'], n, has_out)):
                            if ok:
                                sheet.write(r, c, val, f)
                            else:
                                sheet.write(r, c, '', txt)
                    else:
                        for c in range(2, 8):
                            sheet.write(r, c, '', txt)
                    sheet.write(r, 8, l['bal_qty'], n)
                    sheet.write(r, 9, l['bal_cost'], cost)
                    sheet.write(r, 10, l['bal_value'], n)
                    r += 1
                r += 2
            self._write_checks(workbook, wiz, head, num, txt)

    def _write_checks(self, workbook, wiz, head, num, txt):
        """Sheet for accounting: product x warehouse where ledger, system FIFO
        queue and the document-date replay disagree, biggest value gap first."""
        sheet = workbook.add_worksheet('ให้บัญชีตรวจ')
        sheet.set_column('A:A', 20)
        sheet.set_column('B:B', 44)
        sheet.set_column('C:C', 24)
        sheet.set_column('D:O', 17)
        sheet.set_column('P:P', 80)
        sheet.write(0, 0, 'รายการให้บัญชีตรวจสอบ ณ วันที่ %s' % wiz.date_to)
        sheet.write(1, 0, 'คิวระบบ = ยอดคงเหลือตาม FIFO ที่ระบบเก็บ ณ วันนี้ (เว้นว่างเมื่อวันสิ้นงวดย้อนหลัง) '
                          '/ ล็อตรายงาน = ตัด FIFO ใหม่ตามวันที่เอกสาร')
        for c, h in enumerate(CHECK_HEAD):
            sheet.write(3, c, h, head)
        checks = wiz.env['buz.po.lot.check'].search([('wizard_id', '=', wiz.id)]).sorted(
            lambda k: (-max(abs(k.diff_sys_value), abs(k.diff_lot_value)),
                       k.product_id.default_code or '', k.warehouse_id.name or ''))
        for r, k in enumerate(checks, 4):
            sheet.write(r, 0, k.product_id.default_code or '', txt)
            sheet.write(r, 1, k.product_id.name or '', txt)
            sheet.write(r, 2, k.warehouse_id.name or '', txt)
            for c, name in enumerate(CHECK_COLS, 3):
                if not k.has_sys and 'sys' in name:
                    sheet.write(r, c, '', txt)
                else:
                    sheet.write(r, c, k[name], num)
            sheet.write(r, 15, k.note or '', txt)
