{
    'name': 'buz Auto Analytic Sync',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Sales/Purchase',
    'summary': 'Auto sync analytic distribution from first line to other lines',
    'description': """
        This module allows users to input Analytic information only on the first order line, 
        and the system will automatically copy (sync) the same analytic values to all other 
        lines in the same document.
        
        Supported Documents:
        - Sale Order / Quotation
        - Purchase Order / RFQ
        - Customer Invoice / Vendor Bill
        - Purchase Requisition (if available)
    """,
    'depends': [
        'sale', 
        'purchase', 
        'account', 
        'analytic',
        'employee_purchase_requisition',
    ],
    'data': [
        'views/sale_order_view.xml',
        'views/purchase_order_view.xml',
        'views/account_move_view.xml',
        'views/requisition_order_view.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}