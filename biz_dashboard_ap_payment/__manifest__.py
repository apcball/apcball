# -*- coding: utf-8 -*-
{
    'name': 'Budget & Payment Control Dashboard',
    'version': '17.0.1.1.0',
    'category': 'Accounting',
    'summary': 'Dashboard ควบคุมงบประมาณและยอดจ่าย (AP payment control)',
    'description': """
Budget & Payment Control Dashboard
==================================
OWL dashboard for accounts-payable control:

- ยอดจ่ายประจำเดือน แยกเงินสด / เครดิต / ชำระแล้ว / ค้างชำระ
- ยอดการใช้งบประมาณ (monthly budget plan)
- ยอดขออนุมัติงบประมาณเพิ่มเติม (budget approval requests)
- ประมาณการยอดจ่ายเดือนถัดไป (unpaid bills + unbilled POs)
- Weekly charts, vendor share donut, detail table by vendor / project / expense category
- Excel export
    """,
    'author': 'KYLD',
    'license': 'LGPL-3',
    'depends': [
        'web',
        'account',
        'purchase',
        'biz_monthly_analytic_budget',
        'job_costing_management',
    ],
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': [
        'views/ap_dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'biz_dashboard_ap_payment/static/src/scss/ap_payment_dashboard.scss',
            'biz_dashboard_ap_payment/static/src/js/ap_payment_dashboard.js',
            'biz_dashboard_ap_payment/static/src/xml/ap_payment_dashboard.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
