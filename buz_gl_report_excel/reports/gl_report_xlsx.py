from odoo import models

class GeneralLedgerXlsx(models.AbstractModel):
    _name = 'report.buz_gl_report_excel.report_general_ledger_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, wizards):
        # We can re-use the logic from the PDF report to get the same data
        # We need to call _get_report_values on the PDF report model
        
        pdf_report = self.env['report.buz_gl_report_excel.report_general_ledger']
        # _get_report_values expects docids, which are wizards.ids here
        report_data = pdf_report._get_report_values(wizards.ids, data=data)
        
        accounts = report_data.get('accounts', [])
        date_from = report_data.get('date_from')
        date_to = report_data.get('date_to')
        company = self.env.user.company_id

        sheet = workbook.add_worksheet('General Ledger')
        
        # Formats
        bold = workbook.add_format({'bold': True})
        header_fmt = workbook.add_format({'bold': True, 'align': 'center', 'bg_color': '#DDDDDD', 'border': 1})
        date_fmt = workbook.add_format({'num_format': 'yyyy-mm-dd'})
        amount_fmt = workbook.add_format({'num_format': '#,##0.00'})
        
        # Header Info
        sheet.write(0, 0, f"{company.name}: General Ledger", bold)
        sheet.write(1, 0, f"Date From: {date_from}")
        sheet.write(2, 0, f"Date To: {date_to}")

        # Table Header
        headers = ['Date', 'JRNL', 'Partner', 'Ref', 'Move', 'Analytic Account', 'Entry Label', 'Debit', 'Credit', 'Balance', 'Currency']
        for col_idx, header in enumerate(headers):
            sheet.write(4, col_idx, header, header_fmt)
        
        row = 5
        
        for account in accounts:
            # Account Header
            sheet.write(row, 0, f"{account['code']} {account['name']}", bold)
            
            init_balance = account.get('init_balance')
            if init_balance:
                sheet.write(row, 7, init_balance['debit'], amount_fmt)
                sheet.write(row, 8, init_balance['credit'], amount_fmt)
                sheet.write(row, 9, init_balance['balance'], amount_fmt)
                
                cum_balance = init_balance['balance']
            else:
                cum_balance = 0.0

            row += 1
            
            for line in account['lines']:
                sheet.write(row, 0, line['date'], date_fmt)
                sheet.write(row, 1, line['journal_code'])
                sheet.write(row, 2, line['partner_name'])
                sheet.write(row, 3, line['ref'])
                sheet.write(row, 4, line['move_name'])
                sheet.write(row, 5, line['analytic_account'])
                sheet.write(row, 6, line['entry_label'])
                sheet.write(row, 7, line['debit'], amount_fmt)
                sheet.write(row, 8, line['credit'], amount_fmt)
                
                cum_balance += line['balance']
                sheet.write(row, 9, cum_balance, amount_fmt)
                
                if line['amount_currency']:
                    curr_str = f"{line['amount_currency']} {line['currency_symbol'] if line['currency_symbol'] else ''}"
                    sheet.write(row, 10, curr_str)
                
                row += 1
            
            row += 1 # Empty row between accounts
