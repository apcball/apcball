
from odoo import http
from odoo.http import request, content_disposition
import json

class XLSXReportController(http.Controller):
    @http.route('/xlsx_reports', type='http', auth='user')
    def get_report_xlsx(self, model, options, output_format, report_name, **kw):
        try:
            uid = request.session.uid
            report_obj = request.env[model].with_user(uid)

            response = request.make_response(
                None,
                headers=[
                    ('Content-Type', 'application/vnd.ms-excel'),
                    ('Content-Disposition', content_disposition(report_name + '.xlsx'))
                ]
            )

            # Handle options based on type
            if isinstance(options, str):
                options = json.loads(options)

            report_obj.get_xlsx_report(options, response)
            return response

        except Exception as e:
            return request.make_response(str(e))