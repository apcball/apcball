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
* Per-component cost share (%), required: split the unbuilt product's
  actual (FIFO) consumed value across returned components instead of
  valuing each one at its own standard cost. Confirmation is blocked
  until the cost share of all received components adds up to 100%
* New BOM Type "Unbuild Only": author a BOM dedicated to disassembly,
  separate from the manufacturing BOM. Excluded from Manufacturing
  Orders (core BOM selection stays "normal"/"phantom" only)
* Cost Share (%) can be defined once on the BOM line as the template
  default; it prefills the Unbuild Order component line automatically
  (still editable per order). Required to sum to 100% across BOM lines
  when the BOM Type is "Unbuild Only"
* Smart buttons: Returned Moves / Scrap / Components
* "MRP Unbuild Manager" security group controls who can edit
  quantities, locations and scrap quantities
""",
    'version': '17.0.1.1.0',
    'category': 'Manufacturing',
    'author': 'Mogen Co.',
    'license': 'LGPL-3',
    'depends': ['mrp', 'stock', 'stock_account'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/mrp_bom_views.xml',
        'views/mrp_unbuild_views.xml',
        'report/unbuild_overview_report.xml',
    ],
    'installable': True,
    'application': False,
}
