from odoo import models

class AgedPartnerXlsx(models.AbstractModel):
    _name = 'report.buz_gl_report_excel.report_aged_partner_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, wizards):
        pdf_report = self.env['report.buz_gl_report_excel.report_aged_partner']
        report_data = pdf_report._get_report_values(wizards.ids, data=data)
        
        partners = report_data.get('partners', [])
        date_from = report_data.get('date_from')
        date_to = report_data.get('date_to')
        period_length = report_data.get('period_length', 30)
        direction_selection = report_data.get('direction_selection', 'past')
        result_selection = report_data.get('result_selection', 'customer')
        company = self.env.user.company_id

        sheet = workbook.add_worksheet('Aged Partner')
        
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        bold = workbook.add_format({'bold': True})
        header_fmt = workbook.add_format({
            'bold': True, 
            'align': 'center', 
            'bg_color': '#4F81BD', 
            'border': 1,
            'font_color': 'white',
            'text_wrap': True
        })
        amount_fmt = workbook.add_format({
            'num_format': '#,##0.00', 
            'align': 'right'
        })
        total_fmt = workbook.add_format({
            'bold': True, 
            'num_format': '#,##0.00', 
            'align': 'right',
            'bg_color': '#E7E6E6',
            'border': 1
        })
        
        sheet.set_column('A:A', 40)
        sheet.set_column('B:G', 18)

        sheet.merge_range('A1:G1', f"{company.name}: Aged Partner Report", title_fmt)
        sheet.write('A2', f"Date From: {date_from}")
        sheet.write('A3', f"Date To: {date_to}")
        sheet.write('A4', f"Type: {dict(self.env['aged.partner.wizard']._fields['result_selection'].selection).get(result_selection)}")

        headers = ['Partner', 'Total']
        
        if direction_selection == 'past':
            for i in range(5):
                period_label = f"{i * period_length + 1}-{(i + 1) * period_length} Days"
                headers.append(period_label)
        else:
            for i in range(5):
                period_label = f"{i * period_length + 1}-{(i + 1) * period_length} Days"
                headers.append(period_label)

        for col_idx, header in enumerate(headers):
            sheet.write(5, col_idx, header, header_fmt)
        
        row_fmt = workbook.add_format({'border': 1, 'text_wrap': True, 'valign': 'vcenter'})
        
        row = 6
        grand_total = 0.0
        period_totals = {}

        for partner in partners:
            sheet.write(row, 0, partner['partner_name'], row_fmt)
            sheet.write(row, 1, partner['total'], amount_fmt)
            grand_total += partner['total']

            col = 2
            if direction_selection == 'past':
                for i in range(5):
                    period_key = f"{i * period_length + 1}-{(i + 1) * period_length}"
                    amount = partner['periods'].get(period_key, 0.0)
                    sheet.write(row, col, amount, amount_fmt)
                    
                    if period_key not in period_totals:
                        period_totals[period_key] = 0.0
                    period_totals[period_key] += amount
                    col += 1
            else:
                for i in range(5):
                    period_key = f"{i * period_length + 1}-{(i + 1) * period_length}"
                    amount = partner['periods'].get(period_key, 0.0)
                    sheet.write(row, col, amount, amount_fmt)
                    
                    if period_key not in period_totals:
                        period_totals[period_key] = 0.0
                    period_totals[period_key] += amount
                    col += 1

            row += 1

        row += 1
        sheet.write(row, 0, 'Grand Total', total_fmt)
        sheet.write(row, 1, grand_total, total_fmt)

        col = 2
        if direction_selection == 'past':
            for i in range(5):
                period_key = f"{i * period_length + 1}-{(i + 1) * period_length}"
                sheet.write(row, col, period_totals.get(period_key, 0.0), total_fmt)
                col += 1
        else:
            for i in range(5):
                period_key = f"{i * period_length + 1}-{(i + 1) * period_length}"
                sheet.write(row, col, period_totals.get(period_key, 0.0), total_fmt)
                col += 1
        
        sheet.freeze_panes(6, 0)
