from datetime import datetime, time

from odoo import models

HEAD = ['วันที่', 'เลขที่', 'จำนวนรับ', '@', 'มูลค่ารับ', 'จำนวนจ่าย', '@',
        'มูลค่าจ่าย', 'จำนวนคงเหลือ', '@', 'มูลค่าคงเหลือ']


class PoLotXlsx(models.AbstractModel):
    _name = 'report.buz_stock_po_lot_report.po_lot_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Tax stock report xlsx'

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
            sheet.write(r, 0, 'ช่วงวันที่: %s - %s' % (wiz.date_from, wiz.date_to))
            r += 1
            sheet.write(r, 0, 'เลขประจำตัวผู้เสียภาษีอากร: %s' % (comp.vat or ''))
            r += 1
            sheet.write(r, 0, 'ชื่อผู้ประกอบการ: %s' % comp.name)
            r += 2
            last_model = None
            for prod in wiz.line_ids.mapped('product_id'):
                lines = wiz.line_ids.filtered(lambda l: l.product_id == prod).sorted('seq')
                categ = prod.categ_id
                model = lines[:1].model_code or ''
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
                for c, h in enumerate(HEAD):
                    sheet.write(r, c, h, head)
                r += 1
                lot_header_done = False
                for l in lines:
                    if l.line_type == 'lot' and not lot_header_done:
                        sheet.write(r, 0, 'สินค้าปลายงวด', bold)
                        r += 1
                        lot_header_done = True
                    is_tot = l.line_type == 'total'
                    n = tot if is_tot else num
                    if l.date:
                        sheet.write_datetime(r, 0, datetime.combine(l.date, time.min), dat)
                    else:
                        sheet.write(r, 0, '', txt)
                    sheet.write(r, 1, l.doc_ref or '', doc)
                    if l.line_type in ('move', 'total', 'lot'):
                        sheet.write(r, 2, l.in_qty, n)
                        sheet.write(r, 3, l.in_cost, cost)
                        sheet.write(r, 4, l.in_value, n)
                        sheet.write(r, 5, l.out_qty, n)
                        sheet.write(r, 6, l.out_cost, cost)
                        sheet.write(r, 7, l.out_value, n)
                    else:
                        for c in range(2, 8):
                            sheet.write(r, c, '', txt)
                    sheet.write(r, 8, l.bal_qty, n)
                    sheet.write(r, 9, l.bal_cost, cost)
                    sheet.write(r, 10, l.bal_value, n)
                    r += 1
                r += 2
