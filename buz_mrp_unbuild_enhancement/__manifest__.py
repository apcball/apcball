# Part of buz addons for Mogen Co. See LICENSE file.
{
    'name': 'MRP Unbuild Enhancement',
    'summary': 'Editable component lines, per-line destination, scrap and '
               'partial return on Unbuild Orders',
    'description': """
MRP Unbuild Enhancement
=======================
Enhance Manufacturing Unbuild Orders for real manufacturing environments:

* Preview BOM components as editable lines before confirming
* Edit returned quantity per component
* Per-component destination location (multi-warehouse return)
* Skip damaged components (Receive checkbox)
* Scrap part of a returned quantity (real Stock Scrap records)
* Default return location per BOM line
* Per-component cost share (%): split the unbuilt product's actual
  (FIFO) consumed value across returned components instead of
  valuing each one at its own standard cost
* Smart buttons: Returned Moves / Scrap / Components
* "MRP Unbuild Manager" security group controls who can edit
  quantities, locations and scrap quantities
""",
    'version': '17.0.1.0.0',
    'category': 'Manufacturing',
    'author': 'Mogen Co.',
    'license': 'LGPL-3',
    'depends': ['mrp', 'stock', 'stock_account'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/mrp_bom_views.xml',
        'views/mrp_unbuild_views.xml',
    ],
    'installable': True,
    'application': False,
}
