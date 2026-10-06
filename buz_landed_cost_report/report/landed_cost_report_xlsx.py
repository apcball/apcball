from odoo import models


class LandedCostXlsx(models.AbstractModel):
    _name = 'report.buz_landed_cost_report.xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, wizards):
        domain = data.get('domain', [])
        lines = self.env['buz.landed.cost.report'].search(domain, order='doc_no, product_id, id')

        bold_bg = workbook.add_format({'bold': True, 'bg_color': '#f0f0f0', 'border': 1})
        bold = workbook.add_format({'bold': True, 'num_format': '#,##0.00'})
        date_fmt = workbook.add_format({'num_format': 'dd/mm/yyyy'})
        num_fmt = workbook.add_format({'num_format': '#,##0.00'})

        # one column per cost type (configurable); untyped lines go to 'Other'
        types = self.env['buz.landed.cost.type'].search([])

        # SHEET 1: SUMMARY (per landed cost x product line)
        sheet = workbook.add_worksheet("Summary")
        headers = [
            'Landed Cost', 'LC Date', 'Status', 'Source Doc', 'Transfer', 'Vendor',
            'Product Code', 'Product Name', 'Qty', 'Base Unit Cost', 'Base Cost',
        ] + types.mapped('name') + [
            'Other Type', 'Landed Amount', 'Total Cost', 'Final Unit Cost',
            'SVL Landed', 'Not Capitalised', 'Base Source',
        ]
        for col, h in enumerate(headers):
            sheet.write(0, col, h, bold_bg)
        for row, line in enumerate(lines, start=1):
            sheet.write(row, 0, line.doc_no or '')
            if line.date:
                sheet.write(row, 1, line.date, date_fmt)
            sheet.write(row, 2, line.state or '')
            sheet.write(row, 3, line.ref_no or '')
            sheet.write(row, 4, line.inventory_name or '')
            sheet.write(row, 5, line.partner_id.name or '')
            sheet.write(row, 6, line.product_id.default_code or '')
            sheet.write(row, 7, line.product_id.name or '')
            for i, val in enumerate([line.qty, line.base_unit_cost, line.base_cost], start=8):
                sheet.write(row, i, val, num_fmt)
            by_type = {}
            for d in line.detail_ids:
                by_type[d.cost_type_id.id] = by_type.get(d.cost_type_id.id, 0.0) + d.amount
            col = 11
            for t in types:
                sheet.write(row, col, by_type.pop(t.id, 0.0), num_fmt)
                col += 1
            sheet.write(row, col, sum(by_type.values()), num_fmt)
            sheet.write(row, col + 1, line.landed_cost, num_fmt)
            sheet.write(row, col + 2, line.total_cost, bold)
            sheet.write(row, col + 3, line.unit_cost, bold)
            sheet.write(row, col + 4, line.svl_landed_value, num_fmt)
            sheet.write(row, col + 5, line.svl_landed_diff, num_fmt)
            sheet.write(row, col + 6, line.base_source or '')

        # SHEET 2: COST BREAKDOWN (cost line x product)
        sheet_d = workbook.add_worksheet("Cost Breakdown")
        headers_d = [
            'Landed Cost', 'Transfer', 'Product', 'Cost Line', 'Type',
            'Split Method', 'Account Code', 'Account Name', 'Allocated Amount',
        ]
        for col, h in enumerate(headers_d):
            sheet_d.write(0, col, h, bold_bg)
        row = 1
        for line in lines:
            for detail in line.detail_ids:
                sheet_d.write(row, 0, line.doc_no or '')
                sheet_d.write(row, 1, line.inventory_name or '')
                sheet_d.write(row, 2, line.product_id.display_name or '')
                sheet_d.write(row, 3, detail.cost_line_name or '')
                sheet_d.write(row, 4, detail.cost_type_id.name or '')
                sheet_d.write(row, 5, detail.split_method or '')
                sheet_d.write(row, 6, detail.account_code or '')
                sheet_d.write(row, 7, detail.account_name or '')
                sheet_d.write(row, 8, detail.amount, num_fmt)
                row += 1

        # SHEET 3: AUDIT (per landed cost, same LC set as the filter)
        sheet_a = workbook.add_worksheet("Audit")
        headers_a = [
            'Landed Cost', 'Date', 'Status', 'LC Total', 'Allocated', 'SVL Value',
            'LC Total - Allocated', 'Not Capitalised', 'Moves', 'SVL Layers', 'Journal Entry',
        ]
        for col, h in enumerate(headers_a):
            sheet_a.write(0, col, h, bold_bg)
        audits = self.env['buz.landed.cost.audit'].search(
            [('landed_cost_id', 'in', lines.mapped('landed_cost_id').ids)], order='name')
        for row, a in enumerate(audits, start=1):
            sheet_a.write(row, 0, a.name or '')
            if a.date:
                sheet_a.write(row, 1, a.date, date_fmt)
            sheet_a.write(row, 2, a.state or '')
            for i, val in enumerate(
                    [a.amount_total, a.alloc_total, a.svl_total, a.alloc_diff, a.uncapitalised], start=3):
                sheet_a.write(row, i, val, num_fmt)
            sheet_a.write(row, 8, a.move_count)
            sheet_a.write(row, 9, a.svl_count)
            sheet_a.write(row, 10, 'Y' if a.has_account_move else 'N')
