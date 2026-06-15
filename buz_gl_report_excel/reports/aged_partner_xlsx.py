from odoo import models

class AgedPartnerXlsx(models.AbstractModel):
    _name = 'report.buz_gl_report_excel.report_aged_partner_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, wizards):
        pdf_report = self.env['report.buz_gl_report_excel.report_aged_partner']
        report_data = pdf_report._get_report_values(wizards.ids, data=data)
        
        partners = report_data.get('partners', [])
        date_as_of = report_data.get('date_as_of')
        period_length = report_data.get('period_length', 30)
        direction_selection = report_data.get('direction_selection', 'past')
        result_selection = report_data.get('result_selection', 'Receivable/Payable')
        company = self.env['res.company'].browse(report_data.get('company_id', self.env.company.id))

        sheet = workbook.add_worksheet('Aged Partner')
        
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        header_fmt = workbook.add_format({
            'bold': True, 
            'align': 'center', 
            'bg_color': '#4F81BD', 
            'border': 1,
            'font_color': 'white',
            'text_wrap': True
        })
        subtotal_fmt = workbook.add_format({
            'bold': True,
            'num_format': '#,##0.00',
            'border': 1,
            'bg_color': '#D9D9D9'
        })
        subtotal_name_fmt = workbook.add_format({
            'bold': True,
            'border': 1,
            'bg_color': '#D9D9D9'
        })
        row_fmt = workbook.add_format({'border': 0})
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
        
        sheet.set_column('A:A', 35)
        sheet.set_column('B:C', 12)
        sheet.set_column('D:D', 8)
        sheet.set_column('E:L', 15)

        sheet.merge_range('A1:L1', f"{company.name}: Aged Partner", title_fmt)
        sheet.write('A2', f"As of Date: {date_as_of}")
        if 'aged_partner_xlsx.py' == 'aged_partner_xlsx.py':
            sheet.write('A3', f"Type: {result_selection.title()}")
        
        headers = [
            'Partner / Entry', 'Date', 'Due Date', 'Ccy', 'Amount Ccy',
            'Not Due', '1-30 Days', '31-60 Days', '61-90 Days', '91-120 Days', '120+ Days', 'Total'
        ]
        
        for col_idx, header in enumerate(headers):
            sheet.write(4, col_idx, header, header_fmt)
        
        row = 5
        grand_totals = {
            'Not Due': 0.0,
            '1-30': 0.0,
            '31-60': 0.0,
            '61-90': 0.0,
            '91-120': 0.0,
            '120+': 0.0,
            'Total': 0.0
        }

        bucket_to_col = {
            'Not Due': 5,
            '1-30': 6,
            '31-60': 7,
            '61-90': 8,
            '91-120': 9,
            '120+': 10
        }

        for partner in partners:
            # Partner row (Subtotal)
            sheet.write(row, 0, partner['partner_name'], subtotal_name_fmt)
            for i in range(1, 4):
                sheet.write(row, i, '', subtotal_name_fmt)
            sheet.write(row, 4, '', subtotal_fmt)
            
            sheet.write(row, 5, partner['periods']['Not Due'], subtotal_fmt)
            sheet.write(row, 6, partner['periods']['1-30'], subtotal_fmt)
            sheet.write(row, 7, partner['periods']['31-60'], subtotal_fmt)
            sheet.write(row, 8, partner['periods']['61-90'], subtotal_fmt)
            sheet.write(row, 9, partner['periods']['91-120'], subtotal_fmt)
            sheet.write(row, 10, partner['periods']['120+'], subtotal_fmt)
            sheet.write(row, 11, partner['total'], subtotal_fmt)
            
            grand_totals['Not Due'] += partner['periods']['Not Due']
            grand_totals['1-30'] += partner['periods']['1-30']
            grand_totals['31-60'] += partner['periods']['31-60']
            grand_totals['61-90'] += partner['periods']['61-90']
            grand_totals['91-120'] += partner['periods']['91-120']
            grand_totals['120+'] += partner['periods']['120+']
            grand_totals['Total'] += partner['total']
            
            row += 1
            
            # Detail lines
            for line in partner['lines']:
                sheet.write(row, 0, f"      {line['move_name']}", row_fmt)
                sheet.write(row, 1, str(line['date']) if line['date'] else '', row_fmt)
                sheet.write(row, 2, str(line['date_maturity']) if line['date_maturity'] else '', row_fmt)
                sheet.write(row, 3, line['currency_name'] or '', row_fmt)
                sheet.write(row, 4, line['residual_amount_currency'] if line['currency_name'] else '', amount_fmt)
                
                # Write amount in correct bucket
                col_idx = bucket_to_col[line['bucket']]
                sheet.write(row, col_idx, line['residual_amount'], amount_fmt)
                
                # Total for line
                sheet.write(row, 11, line['residual_amount'], amount_fmt)
                
                row += 1

        # Grand Total row
        row += 1
        sheet.write(row, 0, 'Grand Total', total_fmt)
        for i in range(1, 4):
            sheet.write(row, i, '', total_fmt)
        sheet.write(row, 4, '', total_fmt)
        
        sheet.write(row, 5, grand_totals['Not Due'], total_fmt)
        sheet.write(row, 6, grand_totals['1-30'], total_fmt)
        sheet.write(row, 7, grand_totals['31-60'], total_fmt)
        sheet.write(row, 8, grand_totals['61-90'], total_fmt)
        sheet.write(row, 9, grand_totals['91-120'], total_fmt)
        sheet.write(row, 10, grand_totals['120+'], total_fmt)
        sheet.write(row, 11, grand_totals['Total'], total_fmt)
        
        sheet.freeze_panes(5, 0)
