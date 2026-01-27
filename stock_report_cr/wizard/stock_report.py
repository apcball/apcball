# -*- coding: utf-8 -*-
# Part of Odoo Module Developed by CandidRoot Solutions Pvt. Ltd.
# See LICENSE file for full copyright and licensing details.
from odoo import fields, models, api, _
import io, base64
import logging

_logger = logging.getLogger(__name__)

from odoo.tools.misc import xlsxwriter


class ReportWizard(models.TransientModel):
    _name = "stock.reports"
    _description = "stock report"

    start_date = fields.Datetime('Start date')
    end_date = fields.Datetime('End date')
    location_id = fields.Many2one('stock.location', 'Location')
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env['res.company']._company_default_get('stock.reports'))
    filterby = fields.Selection([('no_filtred', ' No Filterd'), ('product', 'Product')],
                                'Filter by',
                                default='no_filtred')
    products = fields.Many2many('product.product', 'products')
    group_by_category = fields.Boolean('Group By Category')

    xls_file = fields.Binary(string="XLS file")
    xls_filename = fields.Char()

    def button_export_pdf(self):
        if not self.products:
            if self.location_id:
                category_group = self.env['stock.move.line'].read_group(
                    [('date', '>=', self.start_date), ('date', '<=', self.end_date),
                     ('location_dest_id', 'in', self.location_id.ids)], ['product_id'],
                    ['product_id'])
            else:
                category_group = self.env['stock.move.line'].read_group(
                    [('date', '>=', self.start_date), ('date', '<=', self.end_date)], ['product_id'],
                    ['product_id'])

        else:
            if self.location_id:
                category_group = self.env['stock.move.line'].read_group(
                    [('date', '>=', self.start_date), ('date', '<=', self.end_date),
                     ('product_id', 'in', self.products.ids), ('location_dest_id', 'in', self.location_id.ids)],
                    fields=['product_id'],
                    groupby=['product_id'], lazy=False)
            else:
                category_group = self.env['stock.move.line'].read_group(
                    [('date', '>=', self.start_date), ('date', '<=', self.end_date),
                     ('product_id', 'in', self.products.ids)],
                    fields=['product_id'],
                    groupby=['product_id'], lazy=False)

        filter_ids = []
        for rec in category_group:
            product_id = rec['product_id'][0]
            if product_id not in filter_ids:
                filter_ids.append(product_id)
        all_search = self.env['stock.move.line'].search([('product_id', 'in', filter_ids)])
        search = []
        product_list = []
        for each_item in all_search:
            if each_item.product_id.id not in product_list:
                search.append(each_item)
            product_list.append(each_item.product_id.id)

        object = self.env['stock.move.line'].search([])
        incoming_dict = {}
        outgoing_dict = {}
        for rec in object:
            if rec.location_dest_id == self.location_id:
                if rec.product_id.id in incoming_dict:
                    incoming_dict[rec.product_id.id] += rec.quantity
                else:
                    incoming_dict[rec.product_id.id] = rec.quantity
            if rec.location_id == self.location_id:
                if rec.product_id.id in outgoing_dict:
                    outgoing_dict[rec.product_id.id] += rec.quantity
                else:
                    outgoing_dict[rec.product_id.id] = rec.quantity

        record_list = []
        for res in search:
            in_com = incoming_dict[res.product_id.id] if (res.product_id.id in incoming_dict) else 0
            out_go = outgoing_dict[res.product_id.id] if (res.product_id.id in outgoing_dict) else 0
            balance = in_com - out_go
            initial_stock = 0

            vals = {
                'product': res.product_id.name,
                'default_code': res.product_id.default_code,
                'uom': res.product_uom_id.name,
                'reference': res.reference,
                'initial_stock': initial_stock,
                'in': incoming_dict[res.product_id.id] if (res.product_id.id in incoming_dict) else 0,
                'out': outgoing_dict[res.product_id.id] if (res.product_id.id in outgoing_dict) else 0,
                'balance': balance,
                'rec_set': res,
            }
            record_list.append(vals)

        category_dict = {}
        for rec_list in record_list:
            category_name = rec_list.get('rec_set').product_id.categ_id.name
            if category_name in category_dict:
                category_dict[category_name].append(rec_list)
            else:
                category_dict[category_name] = [rec_list]
        locations = (self.read()[0]['location_id'] and self.read()[0]['location_id'][1]) or \
                    self.env['stock.location'].search([]).mapped('name')
        data = {
            'report_start_date': self.read()[0]['start_date'],
            'report_end_date': self.read()[0]['end_date'],
            'report_company_id': self.read()[0]['company_id'][1],
            'report_location': locations,
        }
        if self.group_by_category == True:
            data.update({
                'serach_record': category_dict,
            })
        else:
            data.update({
                'report_group_by_category': self.read()[0]['group_by_category'],
                'search_record': record_list,
            })

        return self.env.ref('stock_report_cr.action_report_stock_report').report_action(self, data=data)

    def button_export_xlsx(self):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Inventory Excel Report')

        if not self.products:
            if self.location_id:
                category_group = self.env['stock.move.line'].read_group(
                    [('date', '>=', self.start_date), ('date', '<=', self.end_date),
                     ('location_dest_id', 'in', self.location_id.ids)], ['product_id'],
                    ['product_id'])
            else:
                category_group = self.env['stock.move.line'].read_group(
                    [('date', '>=', self.start_date), ('date', '<=', self.end_date)], ['product_id'],
                    ['product_id'])

        else:
            if self.location_id:
                category_group = self.env['stock.move.line'].read_group(
                    [('date', '>=', self.start_date), ('date', '<=', self.end_date),
                     ('product_id', 'in', self.products.ids), ('location_dest_id', 'in', self.location_id.ids)],
                    fields=['product_id'],
                    groupby=['product_id'], lazy=False)
            else:
                category_group = self.env['stock.move.line'].read_group(
                    [('date', '>=', self.start_date), ('date', '<=', self.end_date),
                     ('product_id', 'in', self.products.ids)],
                    fields=['product_id'],
                    groupby=['product_id'], lazy=False)

        filter_ids = []
        for rec in category_group:
            product_id = rec['product_id'][0]
            if product_id not in filter_ids:
                filter_ids.append(product_id)
        all_search = self.env['stock.move.line'].search([('product_id', 'in', filter_ids)])
        search = []
        product_list = []
        for each_item in all_search:
            if each_item.product_id.id not in product_list:
                search.append(each_item)
            product_list.append(each_item.product_id.id)

        object = self.env['stock.move.line'].search([])
        incoming_dict = {}
        outgoing_dict = {}
        for rec in object:
            if rec.location_dest_id == self.location_id:
                if rec.product_id.id in incoming_dict:
                    incoming_dict[rec.product_id.id] += rec.quantity
                else:
                    incoming_dict[rec.product_id.id] = rec.quantity
            if rec.location_id == self.location_id:
                if rec.product_id.id in outgoing_dict:
                    outgoing_dict[rec.product_id.id] += rec.quantity
                else:
                    outgoing_dict[rec.product_id.id] = rec.quantity

        record_list = []
        for res in search:
            in_com = incoming_dict[res.product_id.id] if (res.product_id.id in incoming_dict) else 0
            out_go = outgoing_dict[res.product_id.id] if (res.product_id.id in outgoing_dict) else 0
            balance = in_com - out_go
            initial_stock = 0

            vals = {
                'product': res.product_id.name,
                'default_code': res.product_id.default_code,
                'uom': res.product_uom_id.name,
                'reference': res.reference,
                'initial_stock': initial_stock,
                'in': incoming_dict[res.product_id.id] if (res.product_id.id in incoming_dict) else 0,
                'out': outgoing_dict[res.product_id.id] if (res.product_id.id in outgoing_dict) else 0,
                'balance': balance,
                'rec_set': res,
            }
            record_list.append(vals)

        category_dict = {}
        for rec_list in record_list:
            category_name = rec_list.get('rec_set').product_id.categ_id.name
            if category_name in category_dict:
                category_dict[category_name].append(rec_list)
            else:
                category_dict[category_name] = [rec_list]

        header_style = workbook.add_format({'bold': True, 'align': 'center'})
        date_style = workbook.add_format({'align': 'center', 'num_format': 'dd-mm-yyyy'})
        loactions = self.env['stock.location'].search([])
        locations_name = ''
        for loc in loactions:
            locations_name += str(loc.name) + ", "

        sheet.write(0, 0, 'Warehouse', header_style)
        sheet.write(2, 0, 'Location', header_style)
        sheet.write(4, 0, 'Start Date', header_style)
        sheet.write(6, 0, 'End Date', header_style)
        sheet.write(0, 1, self.company_id.name, date_style)
        sheet.write(2, 1, self.location_id.name or locations_name, date_style)
        sheet.write(4, 1, self.start_date, date_style)
        sheet.write(6, 1, self.end_date, date_style)

        sheet.set_column('A2:D5', 27)
        head_style = workbook.add_format({'align': 'center', 'bold': True, 'bg_color': '#dedede'})
        row_head = 8
        sheet.write(row_head, 0, 'Reference', head_style)
        sheet.write(row_head, 1, 'Designation', head_style)
        sheet.write(row_head, 2, 'Uom', head_style)
        sheet.write(row_head, 3, 'Initial stock', head_style)
        sheet.write(row_head, 4, 'IN', head_style)
        sheet.write(row_head, 5, 'OUT', head_style)
        sheet.write(row_head, 6, 'Balance', head_style)
        sheet.freeze_panes(10, 0)

        categ_style = workbook.add_format({'bg_color': '#dedede', 'align': 'center'})
        data_font_style = workbook.add_format({'align': 'center'})
        row = 10
        if self.group_by_category == True:
            for main in category_dict:
                sheet.write(row, 0, main, categ_style)
                sheet.write(row, 1, '', categ_style)
                sheet.write(row, 2, '', categ_style)
                sheet.write(row, 3, '', categ_style)
                sheet.write(row, 4, '', categ_style)
                sheet.write(row, 5, '', categ_style)
                sheet.write(row, 6, '', categ_style)
                for line in category_dict[main]:
                    row += 1
                    sheet.write(row, 0, line.get('default_code'), data_font_style)
                    sheet.write(row, 1, line.get('product'), data_font_style)
                    sheet.write(row, 2, line.get('uom'), data_font_style)
                    sheet.write(row, 3, line.get('initial_stock'), data_font_style)
                    sheet.write(row, 4, line.get('in'), data_font_style)
                    sheet.write(row, 5, line.get('out'), data_font_style)
                    sheet.write(row, 6, line.get('balance'), data_font_style)
                row += 2

        else:
            for line in record_list:
                row += 1
                sheet.write(row, 0, line.get('default_code'), data_font_style)
                sheet.write(row, 1, line.get('product'), data_font_style)
                sheet.write(row, 2, line.get('uom'), data_font_style)
                sheet.write(row, 3, line.get('initial_stock'), data_font_style)
                sheet.write(row, 4, line.get('in'), data_font_style)
                sheet.write(row, 5, line.get('out'), data_font_style)
                sheet.write(row, 6, line.get('balance'), data_font_style)
        row += 2

        workbook.close()
        xlsx_data = output.getvalue()
        self.xls_file = base64.encodebytes(xlsx_data)
        self.xls_filename = "Stock Excel Report.xlsx"

        return {
            'type': 'ir.actions.act_url',
            'name': 'Inventory Excel Report',
            'url': '/web/content/stock.reports/%s/xls_file/%s?download=true' % (
                self.id, 'Stock Excel Report.xlsx'),

        }
