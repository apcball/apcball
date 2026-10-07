from datetime import datetime, time

from xlsxwriter.utility import xl_col_to_name

from odoo import fields, models

FONT = 'Arial'
HEADER_BG = '#1F4E78'
BAND_BG = '#2E75B6'
ZEBRA_BG = '#F2F6FA'
HIGHLIGHT_BG = '#E2F0D9'
TOTAL_BG = '#DDEBF7'

STATE_LABELS = {'draft': 'Draft', 'done': 'Posted', 'cancel': 'Cancelled'}
BASE_SOURCE_LABELS = {'move': 'Receipt move', 'svl': 'Valuation layer'}
NUM = '#,##0.00;[Red]-#,##0.00;-'
QTY = '#,##0.##'
DATE = 'dd/mm/yyyy'

HEADER_ROW = 5  # 0-based; rows 0-3 title block, row 4 optional group band


class LandedCostXlsx(models.AbstractModel):
    _name = 'report.buz_landed_cost_report.xlsx'
    _inherit = 'report.report_xlsx.abstract'

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _make_fmt_getter(self, workbook):
        cache = {}

        def fmt(**props):
            props.setdefault('font_name', FONT)
            props.setdefault('font_size', 10)
            props.setdefault('valign', 'vcenter')
            key = tuple(sorted(props.items()))
            if key not in cache:
                cache[key] = workbook.add_format(props)
            return cache[key]
        return fmt

    def _filter_text(self, domain):
        parts = ['%s %s %s' % (leaf[0], leaf[1], leaf[2])
                 for leaf in domain if isinstance(leaf, (list, tuple)) and len(leaf) == 3]
        return '  |  '.join(parts) or 'No filter'

    def _write_title(self, sheet, fmt, title, filter_text, ncols):
        last = max(ncols - 1, 1)
        sheet.set_row(0, 18)
        sheet.set_row(1, 24)
        sheet.merge_range(0, 0, 0, last, self.env.company.name or '', fmt(bold=True, font_size=11))
        sheet.merge_range(1, 0, 1, last, title, fmt(bold=True, font_size=16, font_color=HEADER_BG))
        sheet.merge_range(2, 0, 2, last, filter_text, fmt(italic=True, font_color='#595959'))
        sheet.merge_range(3, 0, 3, last, 'Printed: %s by %s' % (
            fields.Datetime.to_string(fields.Datetime.context_timestamp(self, fields.Datetime.now())),
            self.env.user.name), fmt(italic=True, font_color='#7F7F7F', font_size=9))

    def _write_table(self, sheet, fmt, headers, rows, col_types, widths,
                     total_cols=(), highlight_cols=(), warn_cols=(), freeze_cols=0,
                     bands=()):
        """headers: list[str]; rows: list[list]; col_types: 'text'|'date'|'num'|'qty'|'center' per col.

        bands: [(first_col, last_col, label)] group header row above the header row.
        """
        hr = HEADER_ROW
        head_fmt = fmt(bold=True, font_color='#FFFFFF', bg_color=HEADER_BG, border=1,
                       border_color='#FFFFFF', align='center', text_wrap=True)
        for col, w in enumerate(widths):
            sheet.set_column(col, col, w)
        for first, last, label in bands:
            band_fmt = fmt(bold=True, font_color='#FFFFFF', bg_color=BAND_BG, align='center',
                           border=1, border_color='#FFFFFF')
            if first == last:
                sheet.write(hr - 1, first, label, band_fmt)
            else:
                sheet.merge_range(hr - 1, first, hr - 1, last, label, band_fmt)
        sheet.set_row(hr, 32)
        for col, h in enumerate(headers):
            sheet.write(hr, col, h, head_fmt)

        def cell_fmt(col, zebra, value):
            kind = col_types[col]
            props = {'border': 1, 'border_color': '#D9D9D9'}
            if kind in ('num', 'qty'):
                props['num_format'] = NUM if kind == 'num' else QTY
            elif kind == 'date':
                props.update(num_format=DATE, align='center')
            elif kind == 'center':
                props['align'] = 'center'
            if col in highlight_cols:
                props.update(bold=True, bg_color=HIGHLIGHT_BG)
            elif zebra:
                props['bg_color'] = ZEBRA_BG
            if col in warn_cols and isinstance(value, (int, float)) and abs(value) > 0.005:
                props.update(font_color='#C00000', bold=True)
            return fmt(**props)

        first_data = hr + 1
        for i, values in enumerate(rows):
            r = first_data + i
            zebra = i % 2 == 1
            for col, value in enumerate(values):
                f = cell_fmt(col, zebra, value)
                if value in (None, False, ''):
                    sheet.write_blank(r, col, None, f)
                elif col_types[col] == 'date':
                    sheet.write_datetime(r, col, datetime.combine(value, time()), f)
                else:
                    sheet.write(r, col, value, f)

        last_data = first_data + len(rows) - 1
        if rows:
            total_row = last_data + 1
            label_fmt = fmt(bold=True, bg_color=TOTAL_BG, top=2, bottom=1)
            sheet.write(total_row, 0, 'TOTAL', label_fmt)
            for col in range(1, len(headers)):
                if col in total_cols:
                    name = xl_col_to_name(col)
                    total = sum((row[col] or 0.0) for row in rows)
                    sheet.write_formula(
                        total_row, col,
                        '=SUBTOTAL(109,%s%d:%s%d)' % (name, first_data + 1, name, last_data + 1),
                        fmt(bold=True, bg_color=TOTAL_BG, top=2, bottom=1,
                            num_format=NUM if col_types[col] == 'num' else QTY),
                        total)
                else:
                    sheet.write_blank(total_row, col, None, label_fmt)
            sheet.autofilter(hr, 0, last_data, len(headers) - 1)
        else:
            sheet.merge_range(first_data, 0, first_data, len(headers) - 1, 'No data',
                              fmt(italic=True, align='center', font_color='#7F7F7F'))
        sheet.freeze_panes(first_data, freeze_cols)
        sheet.hide_gridlines(2)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.repeat_rows(hr)
        sheet.set_footer('&L&A&RPage &P / &N')

    # ------------------------------------------------------------------
    # report
    # ------------------------------------------------------------------
    def generate_xlsx_report(self, workbook, data, wizards):
        domain = data.get('domain', [])
        lines = self.env['buz.landed.cost.report'].search(domain, order='doc_no, product_id, id')
        sheets = data.get('sheets') or ['summary', 'breakdown', 'audit']
        filter_text = self._filter_text(domain)
        fmt = self._make_fmt_getter(workbook)

        # one column per cost type (configurable); untyped lines go to 'Other'
        types = self.env['buz.landed.cost.type'].search([])

        # SHEET 1: SUMMARY (per landed cost x product line)
        headers = [
            'Landed Cost', 'LC Date', 'Status', 'Source Doc', 'Transfer', 'Vendor',
            'Product Code', 'Product Name', 'Qty', 'Base Unit Cost', 'Base Cost',
        ] + types.mapped('name') + [
            'Other Type', 'Landed Amount', 'Total Cost', 'Final Unit Cost',
            'SVL Landed', 'Not Capitalised', 'Base Source',
        ]
        n_types = len(types) + 1  # + Other
        first_type = 11
        landed_col = first_type + n_types
        rows = []
        for line in lines:
            by_type = {}
            for d in line.detail_ids:
                by_type[d.cost_type_id.id] = by_type.get(d.cost_type_id.id, 0.0) + d.amount
            type_vals = [by_type.pop(t.id, 0.0) for t in types]
            rows.append([
                line.doc_no, line.date, STATE_LABELS.get(line.state, line.state), line.ref_no,
                line.inventory_name, line.partner_id.name, line.product_id.default_code,
                line.product_id.name, line.qty, line.base_unit_cost, line.base_cost,
            ] + type_vals + [
                sum(by_type.values()), line.landed_cost, line.total_cost, line.unit_cost,
                line.svl_landed_value, line.svl_landed_diff,
                BASE_SOURCE_LABELS.get(line.base_source, line.base_source),
            ])
        col_types = (['text', 'date', 'center', 'text', 'text', 'text', 'text', 'text',
                      'qty', 'num', 'num'] + ['num'] * n_types
                     + ['num', 'num', 'num', 'num', 'num', 'text'])
        widths = [16, 12, 11, 16, 16, 24, 14, 34, 10, 14, 15] + [14] * n_types \
            + [15, 15, 15, 14, 15, 16]
        total_cols = {8, 10} | set(range(first_type, landed_col + 2)) | {landed_col + 3, landed_col + 4}
        if 'summary' in sheets:
            sheet = workbook.add_worksheet('Summary')
            self._write_title(sheet, fmt, 'Landed Cost Report - Summary', filter_text, len(headers))
            self._write_table(
                sheet, fmt, headers, rows, col_types, widths,
                total_cols=total_cols, highlight_cols={landed_col + 1, landed_col + 2},
                warn_cols={landed_col + 4}, freeze_cols=2,
                bands=[(8, 10, 'Base'), (first_type, landed_col - 1, 'Landed Cost by Type'),
                       (landed_col, landed_col + 2, 'Result'), (landed_col + 3, landed_col + 4, 'Valuation')])

        # SHEET 2: COST BREAKDOWN (cost line x product)
        headers_d = [
            'Landed Cost', 'Transfer', 'Product', 'Cost Line', 'Type',
            'Split Method', 'Account Code', 'Account Name', 'Allocated Amount',
        ]
        rows_d = [[
            line.doc_no, line.inventory_name, line.product_id.display_name,
            d.cost_line_name, d.cost_type_id.name, d.split_method, d.account_code,
            d.account_name, d.amount,
        ] for line in lines for d in line.detail_ids]
        if 'breakdown' in sheets:
            sheet_d = workbook.add_worksheet('Cost Breakdown')
            self._write_title(sheet_d, fmt, 'Landed Cost Report - Cost Breakdown', filter_text, len(headers_d))
            self._write_table(
                sheet_d, fmt, headers_d, rows_d,
                ['text'] * 8 + ['num'], [16, 18, 36, 28, 16, 14, 14, 30, 16],
                total_cols={8}, freeze_cols=1)

        # SHEET 3: AUDIT (per landed cost, same LC set as the filter)
        headers_a = [
            'Landed Cost', 'Date', 'Status', 'LC Total', 'Allocated', 'SVL Value',
            'LC Total - Allocated', 'Not Capitalised', 'Moves', 'SVL Layers', 'Journal Entry',
        ]
        audits = self.env['buz.landed.cost.audit'].search(
            [('landed_cost_id', 'in', lines.mapped('landed_cost_id').ids)], order='name')
        rows_a = [[
            a.name, a.date, STATE_LABELS.get(a.state, a.state), a.amount_total, a.alloc_total,
            a.svl_total, a.alloc_diff, a.uncapitalised, a.move_count, a.svl_count,
            '✓' if a.has_account_move else '✗',
        ] for a in audits]
        if 'audit' in sheets:
            sheet_a = workbook.add_worksheet('Audit')
            self._write_title(sheet_a, fmt, 'Landed Cost Report - Audit', filter_text, len(headers_a))
            self._write_table(
                sheet_a, fmt, headers_a, rows_a,
                ['text', 'date', 'center', 'num', 'num', 'num', 'num', 'num', 'qty', 'qty', 'center'],
                [16, 12, 11, 15, 15, 15, 18, 16, 9, 11, 14],
                total_cols={3, 4, 5, 6, 7}, warn_cols={6}, freeze_cols=1)
