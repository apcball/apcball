from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta


class IrSequenceExtend(models.Model):
    _inherit = 'ir.sequence'

    generate_next_number = fields.Selection(
        [
            ("1", "Month"),
            ("2", "Year"),
        ],
        string="Generate next number by", default="1", store=False
    )

    @staticmethod
    def generate_monthly_start_dates():
        """
        Generates start dates for each month over a 5-year period
        (current year + 4 future years).

        Returns:
            list: A list of starting dates for each month over 5 years.
        """
        monthly_start_dates = []
        current_year = datetime.now().year
        for year_offset in range(5):  # current year + 4 next years
            year = current_year + year_offset
            for month in range(1, 13):
                start_date = datetime(year, month, 1)
                monthly_start_dates.append(start_date)

        return monthly_start_dates

    def start_generate(self):
        temporary_value = self.env.context.get('temporary_value')
        if temporary_value == '1':
            monthly_start_dates = self.generate_monthly_start_dates()
            for month in monthly_start_dates:
                self._create_monthly_date_range_seq(month)

        elif temporary_value == '2':
            self._create_yearly_date_range_seq()

    def _create_monthly_date_range_seq(self, date):
        """
            Creates ir.sequence.date_range records for month based on the given date, if one does not already exist.

            :param date: Date in 'YYYY-MM-DD' format, indicating the given year and month.
            :return: created ir.sequence.date_range record.
        """
        year = fields.Date.from_string(date).year
        month = fields.Date.from_string(date).month

        first_day_of_month = fields.Date.from_string(f'{year}-{month:02}-01')
        last_day_of_month = first_day_of_month + relativedelta(day=31)

        existing_date_range = self.env['ir.sequence.date_range'].search([
            ('sequence_id', '=', self.id),
            ('date_from', '>=', first_day_of_month),
            ('date_from', '<=', last_day_of_month)
        ], order='date_from desc', limit=1)

        if existing_date_range:
            return existing_date_range

        seq_date_range = self.env['ir.sequence.date_range'].sudo().create({
            'date_from': first_day_of_month,
            'date_to': last_day_of_month,
            'sequence_id': self.id,
        })

        return seq_date_range

    def unlink_all_date_ranges(self):
        """
            Deletes all ir.sequence.date_range records associated with the current sequence.

            This method searches for all ir.sequence.date_range records linked to the current sequence
            (identified by self.id) and deletes them all.
        """
        date_ranges = self.env['ir.sequence.date_range'].search([('sequence_id', '=', self.id)])
        date_ranges.unlink()

    def _create_yearly_date_range_seq(self):
        """
            Creates an ir.sequence.date_range record for annual ranges based on the year basis,
            if one does not already exist.
            :return: controlled record ir.sequence.date_range.
        """
        current_year = datetime.now().year
        date_from = '{}-01-01'.format(current_year)
        date_to = '{}-12-31'.format(current_year)

        existing_date_range = self.env['ir.sequence.date_range'].search([
            ('sequence_id', '=', self.id),
            ('date_from', '>=', date_from),
            ('date_from', '<=', date_to)
        ], order='date_from desc', limit=1)

        if existing_date_range:
            return existing_date_range

        seq_date_range = self.env['ir.sequence.date_range'].sudo().create({
            'date_from': date_from,
            'date_to': date_to,
            'sequence_id': self.id,
        })
        return seq_date_range
