# Copyright 2023 Ecosoft Co., Ltd. (http://ecosoft.co.th)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import datetime
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

_logger = logging.getLogger(__name__)


class ResCurrencyRateProviderBOT(models.Model):
    _inherit = "res.currency.rate.provider"

    service = fields.Selection(
        selection_add=[("BOT", "Bank of Thailand")],
        ondelete={"BOT": "set default"},
    )

    @api.depends("service")
    def _compute_available_currency_ids(self):
        res = super()._compute_available_currency_ids()
        Currency = self.env["res.currency"]
        for provider in self:
            if provider.service == "BOT":
                provider.available_currency_ids = Currency.search(
                    [("bot_currency_name", "in", provider._get_supported_currencies())]
                )
        return res

    def _get_supported_currencies(self):
        self.ensure_one()
        if self.service != "BOT":
            return super()._get_supported_currencies()

        return [
            "USD", "GBP", "EUR", "JPY", "HKD", "MYR", "SGD", "BND",
            "PHP", "IDR", "INR", "CHF", "AUD", "NZD", "CAD", "SEK",
            "DKK", "NOK", "CNY", "MXN", "ZAR", "KRW", "TWD", "KWD",
            "SAR", "AED", "MMK", "BDT", "CZK", "KHR", "KES", "LAK",
            "RUB", "VND", "EGP", "PLN", "LKR", "IQD", "BHD", "OMR",
            "JOD", "QAR", "MVR", "NPR", "PGK", "ILS", "HUF", "PKR",
        ]

    def _update_content_currency_update(
        self, bot_currency, content, result, date_from, date_to
    ):
        data = result["data"]
        last_updated = data["data_header"]["last_updated"]
        date_last_update = datetime.datetime.strptime(last_updated, "%Y-%m-%d").date()
        if date_from > date_last_update and date_to > date_last_update:
            _logger.info(
                "BOT: data not yet available for %s to %s (last updated: %s), "
                "will retry on next run",
                date_from,
                date_to,
                last_updated,
            )
            return
        data_details = data["data_detail"]
        for data_detail in data_details:
            period = (
                fields.Date.from_string(data_detail["period"]).strftime(
                    DEFAULT_SERVER_DATE_FORMAT
                )
                if data_detail["period"]
                else False
            )
            if period:
                rate_value = float(data_detail[bot_currency.bot_currency_rate_type])
                if period in content.keys():
                    content[period][bot_currency.name] = 1.0 / rate_value
                else:
                    content[period] = {
                        bot_currency.name: 1.0 / rate_value
                    }

    def _obtain_rates(self, base_currency, currencies, date_from, date_to):
        self.ensure_one()
        if self.service == "BOT":
            if base_currency != "THB":
                raise UserError(
                    _(
                        "Bank of Thailand is suitable only for companies with THB as "
                        "base currency!"
                    )
                )
            ICP = self.env["ir.config_parameter"].sudo()
            bot_api_token = self.company_id.bot_api_token
            if not bot_api_token:
                raise UserError(
                    _("No BOT API token configured. "
                      "Please set it in Settings → Currency Rate Update → BOT API Token.")
                )
            hostname = ICP.get_param("hostname_TH_BOT")
            route_BOT = ICP.get_param("route_TH_BOT_exchange_daily")
            headers = {
                "Authorization": bot_api_token,
                "accept": "application/json",
            }
            bot_currencies = self.env["res.currency"].search(
                [("name", "in", currencies)]
            )
            content = dict()
            # BOT API limits query range to 31 days
            max_period_days = 30
            chunk_start = date_from
            while chunk_start <= date_to:
                chunk_end = min(
                    chunk_start + datetime.timedelta(days=max_period_days),
                    date_to,
                )
                url = "{}{}?start_period={}&end_period={}".format(
                    hostname,
                    route_BOT,
                    chunk_start.strftime("%Y-%m-%d"),
                    chunk_end.strftime("%Y-%m-%d"),
                )
                for bot_currency in bot_currencies:
                    currency = bot_currency.bot_currency_name
                    req_url = f"{url}&currency={currency}"
                    _logger.info("BOT API request: %s", req_url)
                    response = requests.get(req_url, headers=headers, timeout=15)
                    data_dict = response.json()
                    result = data_dict.get("result", False)
                    if not result:
                        error_msg = data_dict.get("error", "")
                        http_code = data_dict.get(
                            "httpCode", response.status_code
                        )
                        more_info = data_dict.get(
                            "moreInformation", error_msg
                        )
                        raise UserError(
                            _(
                                "BOT API Error %(http_code)s\n%(more_info)s"
                            )
                            % {
                                "http_code": http_code,
                                "more_info": more_info,
                            }
                        )
                    self._update_content_currency_update(
                        bot_currency, content, result,
                        chunk_start, chunk_end,
                    )
                chunk_start = chunk_end + datetime.timedelta(days=1)
            if not content:
                _logger.info(
                    "BOT: no new rate data for %s to %s", date_from, date_to
                )
                self.message_post(
                    body=_(
                        "BOT: No exchange rate data available for "
                        "%(date_from)s to %(date_to)s. "
                        "BOT typically publishes on business days only. "
                        "Will retry on next scheduled run."
                    )
                    % {"date_from": date_from, "date_to": date_to},
                    subject=_("BOT Rate Update - No New Data"),
                )
            return content
        return super()._obtain_rates(base_currency, currencies, date_from, date_to)
