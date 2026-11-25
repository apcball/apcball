# -*- coding: utf-8 -*-
{
    "name": "Smart Finance",
    "summary": "CFO strategy, cost control, break-even, cash, margin and financial actions",
    "description": """
CFO Strategy & Action and Cost Control & Break-even: monthly cost imports,
fixed/variable costs and payroll analysis, quarterly KPIs, rule-based financial
issues, approved cross-functional actions, scenario simulation and verified savings.

CFO Cockpit dashboard: Overview, Financial Statements (SAP-style
Balance Sheet / P&L / indirect Cash Flow / AR aging with drill-down),
Financial Ratios (liquidity / leverage / profitability / efficiency vs prior
year), Sales Channel (monthly income statement split by sales channel —
customer chain / sales team / analytic cost centre — with per-channel margin
and cost-type breakdown), Compare BI (P&L, condensed balance sheet and margin ratios across up to
six fiscal years, quarters or months side by side with trend chart and
per-column drill-down), Controlling (cost centre budget vs actual vs commitment
on any analytic plan), Cash & Liquidity, Forecast (12-18 month cash / P&L /
sales pipeline / cost-to-complete grid layered by certainty, with an
overflow column so nothing past the horizon is lost), Sales to Cash,
Project Margin, AP & Payment Plan,
Inventory (valuation by category, trend, turnover / DIO, top products),
Risk Radar, AI Copilot.

Inventory, ratio, open invoice (AR/AP) and cost-centre budget figures can come
from Odoo or from an external system, chosen per company; external data arrives
by manual entry, CSV/XLSX import wizard, or API sync into the External Figures /
External Invoices / External Budgets tables. External invoices feed AR aging,
AP & payment plan, the cash forecast and the sales-to-cash funnel exactly like
Odoo documents; external budgets replace om_account_budget in Controlling.

Supports non-calendar fiscal years and SAP-style posting periods, multi-company
currency translation at closing rate, period-lock awareness, and export of the
full statement pack to PDF (embedded Thai font) or Excel with real formulas.

Reads live accounting / sales / purchase / project data; ships input screens
(per-company finance settings, recurring cash-flow lines, pre-contract sales
deals with billing patterns, risk register, variation orders) for figures the
ERP does not hold yet.
""",
    "version": "17.0.12.0.1",
    "category": "Accounting",
    "license": "LGPL-3",
    "author": "BIZ",
    "depends": [
        "account",
        "sale_management",
        "purchase",
        "crm",
        "project",
    ],
    "external_dependencies": {"python": ["xlsxwriter", "openpyxl"]},
    "data": [
        "security/bsf_security.xml",
        "security/bsf_strategy_security.xml",
        "security/ir.model.access.csv",
        # template ต้องมาก่อน action ที่อ้างถึงมัน
        "report/bsf_statements_templates.xml",
        "report/bsf_statements_report.xml",
        "views/bsf_config_views.xml",
        "views/bsf_forecast_line_views.xml",
        "views/bsf_billing_pattern_views.xml",
        "views/bsf_deal_views.xml",
        "views/bsf_forecast_snapshot_views.xml",
        "views/bsf_risk_views.xml",
        "views/bsf_vo_views.xml",
        "views/res_partner_views.xml",
        "views/res_config_settings_views.xml",
        "views/bsf_dashboard_views.xml",
        "views/bsf_ai_report_views.xml",
        "views/bsf_sales_to_cash_views.xml",
        # เมนู ext fact / bank อ้าง menu_bsf_inputs — ต้องมาหลัง bsf_dashboard_views
        "views/bsf_bank_views.xml",
        "views/bsf_ext_fact_views.xml",
        "views/bsf_ext_invoice_views.xml",
        "views/bsf_ext_budget_views.xml",
        "views/bsf_fact_import_views.xml",
        "views/bsf_doc_import_views.xml",
        # Trial Balance ภายนอกรายเดือน + ทะเบียนงวด (Monthly Close Cockpit)
        "views/bsf_ext_account_views.xml",
        "views/bsf_ext_gl_views.xml",
        "views/bsf_period_views.xml",
        "views/bsf_tb_import_views.xml",
        "views/bsf_input_shortcuts_views.xml",
        "views/bsf_strategy_views.xml",
        "data/bsf_forecast_data.xml",
        "data/bsf_cron.xml",
    ],
    "assets": {
        "web.assets_backend": [
            # ลำดับสำคัญ: scss -> ฐานร่วม (widgets) -> แท็บ (xml คู่ js) -> root ท้ายสุด
            "biz_smart_finance/static/src/dashboard/bsf_dashboard.scss",
            "biz_smart_finance/static/src/dashboard/bsf_widgets.js",
            "biz_smart_finance/static/src/dashboard/bsf_ai_card.xml",
            "biz_smart_finance/static/src/dashboard/bsf_ai_card.js",
            "biz_smart_finance/static/src/dashboard/tab_overview.xml",
            "biz_smart_finance/static/src/dashboard/tab_overview.js",
            "biz_smart_finance/static/src/dashboard/tab_statements.xml",
            "biz_smart_finance/static/src/dashboard/tab_statements.js",
            "biz_smart_finance/static/src/dashboard/tab_close.xml",
            "biz_smart_finance/static/src/dashboard/tab_close.js",
            "biz_smart_finance/static/src/dashboard/tab_controlling.xml",
            "biz_smart_finance/static/src/dashboard/tab_controlling.js",
            "biz_smart_finance/static/src/dashboard/tab_cash.xml",
            "biz_smart_finance/static/src/dashboard/tab_cash.js",
            "biz_smart_finance/static/src/dashboard/tab_forecast.xml",
            "biz_smart_finance/static/src/dashboard/tab_forecast.js",
            "biz_smart_finance/static/src/dashboard/tab_sales.xml",
            "biz_smart_finance/static/src/dashboard/tab_sales.js",
            "biz_smart_finance/static/src/dashboard/tab_channel.xml",
            "biz_smart_finance/static/src/dashboard/tab_channel.js",
            "biz_smart_finance/static/src/dashboard/tab_margin.xml",
            "biz_smart_finance/static/src/dashboard/tab_margin.js",
            "biz_smart_finance/static/src/dashboard/tab_ap.xml",
            "biz_smart_finance/static/src/dashboard/tab_ap.js",
            "biz_smart_finance/static/src/dashboard/tab_ratios.xml",
            "biz_smart_finance/static/src/dashboard/tab_ratios.js",
            "biz_smart_finance/static/src/dashboard/tab_compare.xml",
            "biz_smart_finance/static/src/dashboard/tab_compare.js",
            "biz_smart_finance/static/src/dashboard/tab_inventory.xml",
            "biz_smart_finance/static/src/dashboard/tab_inventory.js",
            "biz_smart_finance/static/src/dashboard/tab_risk.xml",
            "biz_smart_finance/static/src/dashboard/tab_risk.js",
            "biz_smart_finance/static/src/dashboard/tab_ai.xml",
            "biz_smart_finance/static/src/dashboard/tab_ai.js",
            "biz_smart_finance/static/src/dashboard/tab_strategy.xml",
            "biz_smart_finance/static/src/dashboard/tab_strategy.js",
            "biz_smart_finance/static/src/dashboard/bsf_dashboard.xml",
            "biz_smart_finance/static/src/dashboard/bsf_dashboard.js",
            # Monthly Close — client action แยกระดับเมนู (ใช้ tab_close ซ้ำ)
            "biz_smart_finance/static/src/monthly_close/monthly_close.xml",
            "biz_smart_finance/static/src/monthly_close/monthly_close.js",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
