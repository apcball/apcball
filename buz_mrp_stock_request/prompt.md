You are an expert Odoo 17 Community developer. Generate a COMPLETE, production-ready Odoo addon named **buz_mrp_stock_request** that implements an MRP → Stock Request → Internal Transfer flow, inspired by the Odoo 18 app "MRP Stock Request", but 100% compatible with Odoo 17 Community (no Enterprise dependencies).
implement module 
Key Features
1.Request Missing Components
Create stock requests directly from Manufacturing Orders to cover missing raw materials or components.
2.Automatic Internal Transfers
Stock requests automatically generate internal transfers assigned to warehouse teams, ensuring timely fulfillment.
3.Track Stock Request
Monitor requests through stages for better control.
4.Integration with MO & Work Orders
Fully integrated with Manufacturing Orders and Work Orders for a smooth production workflow.

- Stock Request Creation
The Manufacturing Order now includes a new Stock Request button. With one click, production teams can request missing components directly from the MO screen.
- Stock Request Form
The Stock Request form captures product details, quantities, and source/destination locations. It ensures warehouse teams have clear information to prepare the required materials.
- Manufacturing Order and Stock Request connection
A smart button in the Manufacturing Order links directly to related Stock Requests. This allows production managers to quickly review and track material requests.
- Stock Request and Internal Transfer connection
The Stock Request form includes a smart button linking to its generated Internal Transfer. This ensures full traceability between the request and its warehouse fulfillment.
- Internal Transfer
Internal Transfers are automatically created for requested items. The warehouse team can validate them to deliver materials to production lines.
