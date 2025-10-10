# MRP Stock Request (BUZ)

This module enables the creation of stock requests from manufacturing orders to request missing components, which automatically generates internal transfers to fulfill those requests.

## Features

- **Request Missing Components**: Create stock requests directly from Manufacturing Orders to cover missing raw materials or components.
- **Automatic Internal Transfers**: Stock requests automatically generate internal transfers assigned to warehouse teams, ensuring timely fulfillment.
- **Track Stock Request**: Monitor requests through stages for better control.
- **Integration with MO**: Fully integrated with Manufacturing Orders for a smooth production workflow.
- **Auto-population from MO**: One-click functionality to populate request lines with components from the manufacturing order.
- **Multi-company Support**: Properly implemented record rules for multi-company environments.
- **Real-time Status Tracking**: Automatic synchronization of stock request status with related internal transfers.
- **Traceability**: Full linkage between Manufacturing Orders, Stock Requests, and Internal Transfers.
- **Approval Stage**: Optional approval stage for stock requests before fulfillment.
- **Prevention of Deletion**: Prevents deletion of stock requests that already have internal transfers created.

## Key Functionality

### 1. Stock Request Creation
The Manufacturing Order now includes a new **Create Stock Request** button in the header. With one click, production teams can create a new stock request directly from the MO screen when the order is in "Confirmed" or "In Progress" state.

### 2. Manufacturing Order Integration
- Smart button in Manufacturing Order displays the count of related stock requests
- Direct access to view all stock requests associated with a specific Manufacturing Order
- Pre-filled location fields based on the Manufacturing Order's source and destination locations

### 3. Stock Request Form
The Stock Request form captures:
- Product details and quantities
- Source and destination locations
- Requested by user
- Notes and descriptions
- Automatic reference numbering (SRQ/YYYY/XXXX format)

### 4. Auto-population Feature
The "Prepare from MO" button automatically analyzes the manufacturing order's components and suggests:
- Components that have insufficient stock at the destination location
- Required quantities to fulfill the production needs
- Proper unit of measure for each component

### 5. Internal Transfer Generation
- Creates internal transfers automatically when the stock request is confirmed
- Links back from internal transfer to the original stock request
- Maintains source and destination locations from the stock request
- Synchronizes status between stock request and internal transfer

### 6. Status Management
Comprehensive state management:
- **Draft**: Initial state, request can be modified
- **To Approve**: Optional approval stage (can be enabled)
- **Requested**: Confirmed and internal transfer created
- **Done**: Transfer completed and stock request fulfilled
- **Cancelled**: Request cancelled

### 7. Traceability Features
- Links between Manufacturing Order → Stock Request → Internal Transfer
- Chatter messages showing the relationship and status updates
- Easy navigation between related records

## Usage

### Creating a Stock Request
1. Go to a Manufacturing Order that is in "Confirmed" or "In Progress" state
2. Click on the "Create Stock Request" button in the header
3. Fill in the request details (source/destination locations are pre-filled from the MO)
4. Add request lines with products and quantities needed
5. Optionally click "Prepare from MO" to auto-populate the request lines with components from the MO, including those that may be short in stock
6. Save and click "Confirm" to create the internal transfer

### Processing Stock Requests
1. Navigate to Inventory > MRP Stock Request > Stock Requests
2. Review and process requests as needed
3. Check the status of related internal transfers
4. Confirm requests to create internal transfers
5. Warehouse teams can then process the internal transfers from the stock operations

### Using the Auto-population Feature
1. Create or edit a Stock Request
2. Ensure it's linked to a Manufacturing Order
3. Click "Prepare from MO" button
4. The system will analyze MO components and suggest items to request
5. Review and adjust quantities as needed
6. Confirm the request to create the internal transfer

## Configuration

### General Configuration
1. Go to Settings > Manufacturing
2. Under "Stock Requests" section, enable the feature by checking "MRP Stock Request"
3. Set default source and destination locations for stock requests (optional)

### Security Settings
- **MRP Stock Request User**: Basic access to view and create stock requests
- **MRP Stock Request Manager**: Full access including deletion capabilities
- Both groups have proper multi-company access controls

### Sequence Configuration
The module creates a sequence for stock request references with format "SRQ/YYYY/XXXX" that auto-increments.

## Technical Details

### Models
- **mrp.stock.request**: Main model for stock requests with status management, MO linkage, and transfer linkage
- **mrp.stock.request.line**: One2many lines for requested products with quantities and descriptions
- **mrp.production** (inherited): Added computed field for stock request count and action methods
- **stock.picking** (inherited): Added field to link back to originating stock request

### Views
- Tree, form, and kanban views for stock requests
- Integrated buttons in Manufacturing Order view
- Smart buttons for quick access between related records

### Security
- Multi-company record rules implemented for proper data isolation
- Group-based access controls with two-tier user/manager permissions
- Proper domain constraints for locations based on company

### Business Logic
- Validates that only storable products can be requested
- Ensures positive quantities and required fields are filled
- Prevents deletion of requests with completed transfers
- Synchronizes status between stock requests and their internal transfers
- Auto-generates internal transfers with proper picking type determination

### Integration Points
- Extends core Manufacturing (mrp) and Inventory (stock) modules
- Integrates with mail system for chatter functionality
- Connects to configuration settings for default values