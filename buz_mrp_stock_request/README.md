# MRP Stock Request (BUZ)

This module enables the creation of stock requests from manufacturing orders to request missing components, which automatically generates internal transfers to fulfill those requests.

## Features

- **Request Missing Components**: Create stock requests directly from Manufacturing Orders to cover missing raw materials or components.
- **Automatic Internal Transfers**: Stock requests automatically generate internal transfers assigned to warehouse teams, ensuring timely fulfillment.
- **Track Stock Request**: Monitor requests through stages for better control.
- **Integration with MO & Work Orders**: Fully integrated with Manufacturing Orders and Work Orders for a smooth production workflow.

## Key Functionality

### 1. Stock Request Creation
The Manufacturing Order now includes a new **Stock Request** button. With one click, production teams can request missing components directly from the MO screen.

### 2. Stock Request Form
The Stock Request form captures product details, quantities, and source/destination locations. It ensures warehouse teams have clear information to prepare the required materials.

### 3. Manufacturing Order and Stock Request Connection
A smart button in the Manufacturing Order links directly to related Stock Requests. This allows production managers to quickly review and track material requests.

### 4. Stock Request and Internal Transfer Connection
The Stock Request form includes a smart button linking to its generated Internal Transfer. This ensures full traceability between the request and its warehouse fulfillment.

### 5. Internal Transfer
Internal Transfers are automatically created for requested items. The warehouse team can validate them to deliver materials to production lines.

## Usage

### Creating a Stock Request
1. Go to a Manufacturing Order that is in "Confirmed" or "In Progress" state
2. Click on the "Create Stock Request" button in the header
3. Fill in the request details (source/destination locations are pre-filled)
4. Optionally click "Prepare from MO" to auto-populate the request lines with components from the MO
5. Save and confirm the request to create the internal transfer

### Processing Stock Requests
1. Navigate to Inventory > MRP Stock Request > Stock Requests
2. Review and process requests as needed
3. Confirm requests to create internal transfers
4. Warehouse teams can then process the internal transfers from the stock operations

## Configuration
- Go to Settings > Manufacturing > Stock Requests to configure default locations
- Set up security groups for access control

## Technical Details
- The module extends the `mrp.production` model with a computed field for counting related stock requests
- Stock requests are linked to both manufacturing orders and internal transfers for traceability
- Multi-company support is implemented with proper record rules