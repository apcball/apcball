# -*- coding: utf-8 -*-
###############################################################################
#
# Cybrosys Technologies Pvt. Ltd.
#
# Copyright (C) 2023-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
# Author: Ayana KP (odoo@cybrosys.com)
#
# You can modify it under the terms of the GNU AFFERO
# GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
# You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
# (AGPL v3) along with this program.
# If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
import json
import io
from odoo.tools import date_utils
from odoo.exceptions import ValidationError
from odoo import fields, models
try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter


class SaleReportAnalysis(models.TransientModel):
    """Model for Sale report analysis """
    _name = "sale.report.analysis"
    _description = "Sale Report Analysis"

    customer_ids = fields.Many2many('res.partner', string="Customers",
                                    required=True,
                                    help='Select the customers of sales')
    product_ids = fields.Many2many('product.product', string='Products',
                                   help="Select products of sale report")
    from_date = fields.Date(string="Start Date", help='Start date of report')
    to_date = fields.Date(string="End Date", help="End date of report")
    status = fields.Selection(
        [('all', 'All'), ('draft', 'Draft'), ('sent', 'Quotation Sent'),
         ('sale', 'Sale Order'), ('done', 'Locked')],
        string='Status', default='all', required=True,
        help="Select the status of sale order")
    print_type = fields.Selection(
        [('sale', 'Sale Order'), ('product', 'Products')],
        string='Print By', default='sale', required=True,
        help='Select the type of print: "Sale Order" or "Products".')
    today_date = fields.Date(string="Date", default=fields.Date.today(),
                             help="Date of the report")

    def action_get_analysis_report(self):
        """ Generate a sales analysis report.
            :return: Action to display the sales analysis report. """
        datas = self._get_data()
        return self.env.ref(
            'sale_report_advanced.action_sales_analysis').report_action([],
                                                                        data=datas)

    def _get_data(self):
        """ Retrieve and format data for a sales analysis report.
            :return: Formatted data for the report. """
        result = []
        if self.print_type == 'sale':
            if not self.status == 'all':
                sale_order = self.env['sale.order'].sudo().search(
                    [('state', '=', self.status), ('state', '!=', 'cancel')])
                filtered = self._get_filtered(sale_order)
            else:
                sale_order = self.env['sale.order'].search(
                    [('state', '!=', 'cancel')])
                filtered = self._get_filtered(sale_order)
            for rec in filtered:
                paid = self._get_total_paid_amount(rec.invoice_ids)
                res = {
                    'so': rec.name,
                    'date': rec.date_order,
                    'sales_person': rec.user_id.name,
                    's_amt': rec.amount_total,
                    'p_amt': paid,
                    'balance': rec.amount_total - paid,
                    'partner_id': rec.partner_id,
                }
                result.append(res)
        else:
            if not self.status == 'all':
                sale_order_line = self.env['sale.order.line'].search(
                    [('order_id.state', '=', self.status),
                     ('order_id.state', '!=', 'cancel')])
                filtered = self._get_filtered_order_line(sale_order_line)
            else:
                sale_order_line = self.env['sale.order.line'].search(
                    [('order_id.state', '!=', 'cancel')])
                filtered = self._get_filtered_order_line(sale_order_line)
            for rec in filtered:
                res = {
                    'so': rec.order_id.name,
                    'date': rec.order_id.date_order,
                    'product_id': rec.product_id.name,
                    'price': rec.product_id.list_price,
                    'quantity': rec.product_uom_qty,
                    'discount': rec.discount,
                    'tax': rec.product_id.taxes_id.amount,
                    'total': rec.price_subtotal,
                    'partner_id': rec.order_id.partner_id,
                }
                result.append(res)
        datas = {
            'ids': self,
            'model': 'sale.report.analysis',
            'form': result,
            'partner_id': self._get_customers(),
            'start_date': self.from_date,
            'end_date': self.to_date,
            'type': self.print_type
        }
        return datas

    def _get_total_paid_amount(self, invoices):
        """ Calculate the total paid amount from a list of invoices.
            :return: Total paid amount. """
        total = 0
        for inv in invoices:
            if inv.payment_state == 'paid':
                total += inv.amount_total
        return total

    def _get_filtered_order_line(self, sale_order_line):
        """ Filter sale order lines based on date, customers, and products.
            :param sale_order_line: List of sale order lines.
            :type sale_order_line: list
            :return: Filtered list of sale order lines.
            :rtype: list
            This method filters a list of sale order lines based on optional
            date range, customer selection, and product selection.
            The filtered list is returned. """
        if self.from_date and self.to_date:
            filtered = list(filter(lambda
                                       x: x.order_id.date_order.date() >= self.from_date and x.order_id.date_order.date() <= self.to_date and x.order_id.partner_id in self.customer_ids and x.product_id in self.product_ids,
                                   sale_order_line))
        elif not self.from_date and self.to_date:
            filtered = list(filter(lambda
                                       x: x.order_id.date_order.date() <= self.to_date and x.order_id.partner_id in self.customer_ids and x.product_id in self.product_ids,
                                   sale_order_line))
        elif self.from_date and not self.to_date:
            filtered = list(filter(lambda
                                       x: x.order_id.date_order.date() >= self.from_date and x.order_id.partner_id in self.customer_ids and x.product_id in self.product_ids,
                                   sale_order_line))
        else:
            filtered = list(filter(lambda
                                       x: x.order_id.partner_id in self.customer_ids and x.product_id in self.product_ids,
                                   sale_order_line))
        return filtered

    def _get_filtered(self, sale_order):
        """  Filter sale orders based on date and customers.
            :param sale_order: List of sale orders.
            :type sale_order: list
            :return: Filtered list of sale orders.
            :rtype: list
            This method filters a list of sale orders based on optional date
            range and customer selection. The filtered list is returned.  """
        if self.from_date and self.to_date:
            filtered = list(filter(lambda
                                       x: x.date_order.date() >= self.from_date and x.date_order.date() <= self.to_date and x.partner_id in self.customer_ids,
                                   sale_order))
        elif not self.from_date and self.to_date:
            filtered = list(filter(lambda
                                       x: x.date_order.date() <= self.to_date and x.partner_id in self.customer_ids,
                                   sale_order))
        elif self.from_date and not self.to_date:
            filtered = list(filter(lambda
                                       x: x.date_order.date() >= self.from_date and x.partner_id in self.customer_ids,
                                   sale_order))
        else:
            filtered = list(filter(lambda
                                       x: x.partner_id in self.customer_ids,
                                   sale_order))
        return filtered

    def _get_customers(self):
        """ Retrieve customer data.
            :return: List of customer information.
            :rtype: list
            This method retrieves customer data and returns a list of customer
            information, including their ID and name. """
        customers = []
        for rec in self.customer_ids:
            data = {'id': rec,
                    'name': rec.name}
            customers.append(data)
        return customers

    def action_get_excel_analysis_report(self):
        """ Generate an Excel analysis report.
           :return: Dictionary specifying the Excel report action.
           :rtype: dict
           This method prepares the data for an Excel analysis report and
           returns a dictionary that defines the action to generate the
           report in XLSX format. """
        datas = self._get_data()
        return {
            'type': 'ir.actions.report',
            'report_type': 'xlsx',
            'data': {'model': 'sale.report.analysis',
                     'output_format': 'xlsx',
                     'options': json.dumps(datas,
                                           default=date_utils.json_default),
                     'report_name': 'Sale Analysis Report',
                     },
        }

    def get_xlsx_report(self, options, response):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet()

        # Define formats
        format1 = workbook.add_format({'font_size': 16, 'align': 'center', 'bold': True})
        format2 = workbook.add_format({'font_size': 10, 'align': 'center'})
        format3 = workbook.add_format({'bold': True, 'border': 1, 'font_size': 10})
        format4 = workbook.add_format({'border': 1, 'font_size': 10})

        sheet.merge_range('A2:H3', 'Sales Analysis Report', format1)

        if options.get('type') == 'sale':
            # Headers for sale order report
            headers = ['Order', 'Date', 'Sales Person', 'Sales Amount', 'Paid Amount', 'Balance']
            for col, header in enumerate(headers):
                sheet.write(4, col, header, format3)

            row = 5
            for data in options.get('form', []):
                sheet.write(row, 0, data.get('so'), format4)
                sheet.write(row, 1, str(data.get('date')), format4)
                sheet.write(row, 2, data.get('sales_person'), format4)
                sheet.write(row, 3, data.get('s_amt'), format4)
                sheet.write(row, 4, data.get('p_amt'), format4)
                sheet.write(row, 5, data.get('balance'), format4)
                row += 1
        else:
            # Headers for product report
            headers = ['Order', 'Date', 'Product', 'Price', 'Quantity', 'Discount', 'Tax', 'Total']
            for col, header in enumerate(headers):
                sheet.write(4, col, header, format3)

            row = 5
            for data in options.get('form', []):
                sheet.write(row, 0, data.get('so'), format4)
                sheet.write(row, 1, str(data.get('date')), format4)
                sheet.write(row, 2, data.get('product_id'), format4)
                sheet.write(row, 3, data.get('price'), format4)
                sheet.write(row, 4, data.get('quantity'), format4)
                sheet.write(row, 5, data.get('discount'), format4)
                sheet.write(row, 6, data.get('tax'), format4)
                sheet.write(row, 7, data.get('total'), format4)
                row += 1

        workbook.close()
        output.seek(0)
        response.stream.write(output.read())
        output.close()
