from odoo import models

class GeneralLedgerXlsx(models.AbstractModel):
    _name = 'report.buz_gl_report_excel.report_general_ledger_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, wizards):
        # We can re-use logic from PDF report to get same data
        # We need to call _get_report_values on the PDF report model
        
        pdf_report = self.env['report.buz_gl_report_excel.report_general_ledger']
        # _get_report_values expects docids, which are wizards.ids here
        report_data = pdf_report._get_report_values(wizards.ids, data=data)
        
        accounts = report_data.get('accounts', [])
        date_from = report_data.get('date_from')
        date_to = report_data.get('date_to')
        company = self.env['res.company'].browse(report_data.get('company_id', self.env.company.id))

        sheet = workbook.add_worksheet('General Ledger')
        
        # Formats
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
        date_fmt = workbook.add_format({'num_format': 'yyyy-mm-dd'})
        amount_fmt = workbook.add_format({'num_format': '#,##0.00', 'align': 'right'})
        row_fmt = workbook.add_format({'border': 1, 'text_wrap': True, 'valign': 'vcenter'})
        account_header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D9E2F3', 'border': 1})
        total_fmt = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'bg_color': '#E7E6E6', 'border': 1})
        
        # Column widths
        sheet.set_column('A:A', 12)
        sheet.set_column('B:B', 8)
        sheet.set_column('C:C', 30)
        sheet.set_column('D:D', 15)
        sheet.set_column('E:E', 15)
        sheet.set_column('F:F', 20)
        sheet.set_column('G:G', 35)
        sheet.set_column('H:J', 15)
        sheet.set_column('K:K', 15)
        
        # Header Info
        sheet.merge_range('A1:K1', f"{company.name}: General Ledger", title_fmt)
        sheet.write('A2', f"Date From: {date_from}")
        sheet.write('A3', f"Date To: {date_to}")

        # Table Header
        headers = ['Date', 'JRNL', 'Partner', 'Ref', 'Move', 'Analytic Account', 'Entry Label', 'Debit', 'Credit', 'Balance', 'Currency']
        for col_idx, header in enumerate(headers):
            sheet.write(4, col_idx, header, header_fmt)
        
        row = 5
        sheet.freeze_panes(5, 0)
        
        for account in accounts:
            # Account Header
            sheet.merge_range(f'A{row+1}:K{row+1}', f"{account['code']} {account['name']}", account_header_fmt)
            
            init_balance = account.get('init_balance')
            if init_balance:
                sheet.write(row, 6, 'Brought Forward', bold)
                sheet.write(row, 7, init_balance['debit'], amount_fmt)
                sheet.write(row, 8, init_balance['credit'], amount_fmt)
                sheet.write(row, 9, init_balance['balance'], amount_fmt)
                
                cum_balance = init_balance['balance']
            else:
                cum_balance = 0.0

            row += 1
            
            for line in account['lines']:
                sheet.write(row, 0, line['date'], date_fmt)
                sheet.write(row, 1, line['journal_code'], row_fmt)
                sheet.write(row, 2, line['partner_name'], row_fmt)
                sheet.write(row, 3, line['ref'], row_fmt)
                sheet.write(row, 4, line['move_name'], row_fmt)
                sheet.write(row, 5, line['analytic_account'], row_fmt)
                sheet.write(row, 6, line['entry_label'], row_fmt)
                sheet.write(row, 7, line['debit'], amount_fmt)
                sheet.write(row, 8, line['credit'], amount_fmt)
                
                cum_balance += line['balance']
                sheet.write(row, 9, cum_balance, amount_fmt)
                
                if line['amount_currency']:
                    curr_str = f"{line['amount_currency']} {line['currency_symbol'] if line['currency_symbol'] else ''}"
                    sheet.write(row, 10, curr_str, row_fmt)
                
                row += 1
            
            # Carried Forward
            sheet.write(row, 6, 'Carried Forward', total_fmt)
            sheet.write(row, 9, cum_balance, total_fmt)
            
            row += 1 # Empty row between accounts
