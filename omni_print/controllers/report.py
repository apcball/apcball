import json
import logging
import werkzeug.exceptions

from werkzeug.urls import url_parse
from urllib.parse import quote

from odoo import http
from odoo.http import content_disposition, request, route
from odoo.tools.misc import html_escape
from odoo.tools.safe_eval import safe_eval, time

from odoo.addons.web.controllers import report

_logger = logging.getLogger(__name__)


class ReportController(report.ReportController):

    @route()
    def report_download(self, data, context=None, token=None):
        resp = super().report_download(data, context, token)

        requestcontent = json.loads(data)
        url, type_ = requestcontent[0], requestcontent[1]

        if type_ not in ['qweb-pdf', 'qweb-text']:
            return resp

        pattern = '/report/pdf/' if type_ == 'qweb-pdf' else '/report/text/'
        reportname = url.split(pattern)[1].split('?')[0]
        docids = None
        if '/' in reportname:
            reportname, docids = reportname.split('/')

        report = request.env['ir.actions.report']._get_report_from_name(reportname)

        resp.headers.add("X-Report-Name", reportname)
        resp.headers.add("X-Report-Title", quote(report.name))

        if not docids:
            return resp

        ids = [int(x) for x in docids.split(",") if x.isdigit()]
        records = request.env[report.model].browse(ids)
        doc_names = ",".join([r.display_name for r in records])

        resp.headers.add("X-Report-Docnames", quote(doc_names))

        return resp
