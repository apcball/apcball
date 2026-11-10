# -*- coding: utf-8 -*-
import base64
import io
from collections import OrderedDict

import xlsxwriter

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class BuzCogsExportWizard(models.TransientModel):
    _name = 'buz.cogs.export.wizard'
    _description = 'Export Actual COGS to Excel'

    MAX_DAYS = 366

    period = fields.Selection(
        [('this_month', 'This Month'),
         ('last_month', 'Last Month'),
         ('last_3_months', 'Last 3 Months'),
         ('this_year', 'This Year'),
         ('custom', 'Custom')],
        string='Period', default='this_month', required=True)
    date_from = fields.Date(string='Start Date', required=True,
                            default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(string='End Date', required=True,
                          default=fields.Date.context_today)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouses')
    product_ids = fields.Many2many('product.product', string='Products')
    product_categ_ids = fields.Many2many('product.category', string='Product Categories')
    file_data = fields.Binary(string='File', readonly=True, attachment=False)
    file_name = fields.Char(readonly=True)

    @api.onchange('period')
    def _onchange_period(self):
        today = fields.Date.context_today(self)
        first = today.replace(day=1)
        if self.period == 'this_month':
            self.date_from, self.date_to = first, today
        elif self.period == 'last_month':
            self.date_from = first - relativedelta(months=1)
            self.date_to = first - relativedelta(days=1)
        elif self.period == 'last_3_months':
            self.date_from, self.date_to = first - relativedelta(months=2), today
        elif self.period == 'this_year':
            self.date_from, self.date_to = today.replace(month=1, day=1), today

    def _get_domain(self):
        self.ensure_one()
        domain = [('kind', 'in', ('sale', 'return')),
                  ('acct_date', '>=', self.date_from),
                  ('acct_date', '<=', self.date_to)]
        if self.warehouse_ids:
            domain.append(('warehouse_id', 'in', self.warehouse_ids.ids))
        if self.product_ids:
            domain.append(('product_id', 'in', self.product_ids.ids))
        if self.product_categ_ids:
            domain.append(('product_categ_id', 'child_of', self.product_categ_ids.ids))
        return domain

    def action_export(self):
        self.ensure_one()
        if not self.env.user.has_group('buz_cogs_report.group_buz_cogs_report_user'):
            raise UserError('You are not allowed to export the Actual COGS report.')
        if self.date_from > self.date_to:
            raise UserError('Start Date must be before End Date.')
        if (self.date_to - self.date_from).days + 1 > self.MAX_DAYS:
            raise UserError(
                'Date range is longer than %d days. Pick a shorter period '
                'or export in several runs to keep the export fast.' % self.MAX_DAYS)
        rows = self.env['buz.cogs.report'].search_read(
            self._get_domain(),
            ['default_code', 'product_name', 'acct_date', 'doc_no',
             'qt', 'cost', 'qt_return', 'cost_return'],
            order='default_code, acct_date, doc_no')
        # one line per product + date + document, like the accounting sheet
        agg = OrderedDict()
        for r in rows:
            key = (r['default_code'] or '', r['acct_date'], r['doc_no'] or '')
            a = agg.setdefault(key, {
                'name': r['product_name'] or '', 'qt': 0.0, 'cost': 0.0,
                'qt_return': 0.0, 'cost_return': 0.0})
            for f in ('qt', 'cost', 'qt_return', 'cost_return'):
                a[f] += r[f]

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
        ws = wb.add_worksheet('Actual COGS')
        head = wb.add_format({'bold': True, 'border': 1, 'bg_color': '#D9D9D9'})
        txt = wb.add_format({'border': 1})
        dt = wb.add_format({'border': 1, 'num_format': 'dd/mm/yyyy'})
        num = wb.add_format({'border': 1, 'num_format': '#,##0.00'})
        tot = wb.add_format({'bold': True, 'border': 1, 'num_format': '#,##0.00'})
        headers = ['prdid', 'prdname', 'date', 'no', 'qt', 'cost', 'qt_return', 'cost_return']
        for c, h in enumerate(headers):
            ws.write(0, c, h, head)
        line = 0
        for (code, date, doc), a in agg.items():
            line += 1
            ws.write(line, 0, code, txt)
            ws.write(line, 1, a['name'], txt)
            ws.write_datetime(line, 2, fields.Date.to_date(date), dt) if date else ws.write(line, 2, '', txt)
            ws.write(line, 3, doc, txt)
            ws.write_number(line, 4, a['qt'], num)
            ws.write_number(line, 5, a['cost'], num)
            ws.write_number(line, 6, a['qt_return'], num)
            ws.write_number(line, 7, a['cost_return'], num)
        if line:
            ws.write(line + 1, 3, 'Total', tot)
            for c in range(4, 8):
                col = xlsxwriter.utility.xl_col_to_name(c)
                ws.write_formula(line + 1, c, '=SUM(%s2:%s%d)' % (col, col, line + 1), tot)
        ws.set_column(0, 0, 16)
        ws.set_column(1, 1, 40)
        ws.set_column(2, 3, 16)
        ws.set_column(4, 7, 14)
        ws.freeze_panes(1, 0)
        wb.close()

        self.write({
            'file_data': base64.b64encode(buf.getvalue()),
            'file_name': 'actual_cogs_%s_%s.xlsx' % (self.date_from, self.date_to),
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/?model=%s&id=%d&field=file_data&filename_field=file_name&download=true'
                   % (self._name, self.id),
            'target': 'self',
        }
