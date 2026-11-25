import re
from datetime import datetime, time

from odoo import models

HEAD = ['วันที่', 'เลขที่', 'จำนวนรับ', '@', 'มูลค่ารับ', 'จำนวนจ่าย', '@',
        'มูลค่าจ่าย', 'จำนวนคงเหลือ', '@', 'มูลค่าคงเหลือ']

# ' (ล็อต A, B +N)' / ' (ลงล็อต A)' suffix the engine puts on a movement's document
LOT_SUFFIX = re.compile(r'\s*\((?:ลง)?ล็อต ([^)]*)\)\s*$')


def split_lot(ref):
    """'DOC (ล็อต LOT)' -> ('LOT', 'DOC'); no lot suffix -> (ref, '')."""
    m = LOT_SUFFIX.search(ref)
    if not m:
        return ref, ''
    return m.group(1).strip(), ref[:m.start()].strip()


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
            r += 2
            last_model = None
            # one pass: group lines by product (keeps line order), no per-product filtered()
            fields_ = ['product_id', 'seq', 'model_code', 'line_type', 'date', 'doc_ref',
                       'in_qty', 'in_cost', 'in_value', 'out_qty', 'out_cost', 'out_value',
                       'bal_qty', 'bal_cost', 'bal_value']
            cols = ['product_id'] + fields_[1:] + ['warehouse_id', 'wh_date', 'in_allin']
            # warehouse column (lot / movement rows are per warehouse)
            show_wh = True
            wh_names = {w.id: w.name for w in self.env['stock.warehouse'].with_context(
                active_test=False).search([])}
            sheet.set_column('L:L', 24)
            sheet.set_column('M:M', 34)
            sheet.set_column('N:N', 14)
            sheet.set_column('O:O', 16)
            self.env.cr.execute(
                'SELECT %s FROM buz_po_lot_line WHERE wizard_id = %%s ORDER BY product_id, seq'
                % ', '.join(cols), (wiz.id,))
            grouped = {}
            for tup in self.env.cr.fetchall():
                rec = dict(zip(cols, tup))
                for k in cols[6:-2]:
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
                for c, h in enumerate(HEAD + (['คลังสินค้า', 'เอกสาร', 'วันที่เข้าคลัง', 'ต้นทุนรวม LC (All-in @)'] if show_wh else [])):
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
                    if show_wh:
                        sheet.write(r, 11, wh_names.get(l['warehouse_id'], '') if lt in (
                            'move', 'lot', 'lotbal', 'lotlc') else '', txt)
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
                    # snapshots under every movement (lotbal) keep only the lot date
                    if lt == 'lotbal' and l['date']:
                        sheet.write(r, 1, '', doc)
                    elif lt == 'move':
                        # the lot is the identifier in the document column; the
                        # transfer / bill / sale number moves to the last column
                        lot, ref = split_lot((l['doc_ref'] or '').split(' · ')[0])
                        sheet.write(r, 1, lot, doc)
                        if ref and show_wh:
                            sheet.write(r, 12, ref, doc)
                    elif lt == 'lot' and l['date']:
                        sheet.write(r, 1, (l['doc_ref'] or '').split(' · ')[0], doc)
                    else:
                        sheet.write(r, 1, l['doc_ref'] or '', doc)
                    if lt == 'lotlc':
                        # landed cost booked on the lot above: bill number + value
                        sheet.write(r, 1, '   + ค่าใช้จ่ายนำเข้า ' + (l['doc_ref'] or ''), doc)
                        for c in range(2, 11):
                            sheet.write(r, c, '', txt)
                        sheet.write(r, 3, l['in_cost'], cost)
                        sheet.write(r, 4, l['in_value'], num)
                        r += 1
                        continue
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
