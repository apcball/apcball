# Stock By Location - Odoo 17 Module

## Overview
This module extends Odoo's inventory management to track product stock and costs based on specific warehouse locations. It implements an "AVCO by Location" (Average Cost by Location) costing method.

## Features

### Core Functionality
- **Location-Based Costing**: Track product costs separately for each warehouse location
- **AVCO by Location**: New costing method that calculates average cost per location
- **Main Warehouse**: Designate a main warehouse for standard price calculations
- **Cost History**: Complete audit trail of cost changes per location
- **Sale Order Integration**: Select delivery location and see location-specific costs
- **Landed Cost Support**: Properly distribute landed costs across locations

### Key Components

#### 1. Costing Method: AVCO by Location
- New cost method added to Product Category: `avco_by_location`
- Maintains separate average cost for each internal location
- Tracks stock valuation layers with location information
- Updates costs only for the main warehouse's standard price

#### 2. Main Warehouse
- Mark one warehouse as the "Main Warehouse"
- Product's standard price reflects the main warehouse cost
- Other locations maintain independent costs

#### 3. Location Settings
- **Exclude from Product Cost**: Exclude location from cost calculations
- **Apply in Sale Order**: Make location available for sale order selection

#### 4. Sale Order Enhancements
- Select "Deliver From" location on sale orders
- View location-specific cost on order lines
- Automatic picking type selection based on location
- Location-aware stock availability

#### 5. Cost History
- Complete history of cost changes per location
- Track incoming quantity, cost, and resulting average
- Accessible via menu: Base > Product Cost History

## Installation

### Prerequisites
- Odoo 17.0
- Required modules:
  - `sale_management`
  - `stock_landed_costs`
  - `stock_account`
  - `sale`
  - `sale_stock`
  - `purchase`
  - `account_accountant`

### Installation Steps
1. Copy the module to your Odoo addons directory
2. Update the app list: `Settings > Apps > Update Apps List`
3. Search for "Stock By Location"
4. Click Install

## Configuration

### 1. Set Main Warehouse
1. Go to `Inventory > Configuration > Warehouses`
2. Open your main warehouse
3. Check the "Main Warehouse?" field
4. Save

### 2. Configure Product Category
1. Go to `Inventory > Configuration > Product Categories`
2. Open or create a category
3. Set Costing Method to "AVCO by Location"
4. Save

### 3. Configure Locations
1. Go to `Inventory > Configuration > Locations`
2. Open a location
3. Configure:
   - **Exclude from Product Cost**: If you want to exclude this location
   - **Apply in Sale Order**: If you want to use this location in sales
4. Save

### 4. Configure Products
1. Go to `Inventory > Products`
2. Open a product
3. Ensure the product category uses "AVCO by Location"
4. View location-specific costs in the "Product Cost" tab

## Usage

### Viewing Location Costs
1. Open any product with AVCO by Location costing
2. Go to the "Product Cost" tab
3. View current quantity and cost for each location

### Creating Sale Orders with Location
1. Create a new Sale Order
2. Select "Deliver From" location (required)
3. System automatically sets the correct picking type
4. View purchase price (cost) on order lines

### Tracking Cost History
1. Go to `Base > Product Cost History` menu
2. Filter by product, location, or date
3. View complete cost change history

### Internal Transfers
- When moving stock between locations, system:
  - Creates valuation layers for both source and destination
  - Uses source location cost for the move
  - Updates destination location average cost
  - Records cost history for destination

### Landed Costs
- System properly allocates landed costs to:
  - Main warehouse standard price (if applicable)
  - Location-specific cost history
  - Stock valuation layers with location tracking

## Technical Details

### New Models

#### `product.cost.location` (Transient)
- Temporary model for computing location costs
- Fields: `product_id`, `location_id`, `qty`, `standard_price`, `company_id`

#### `product.cost.location.history`
- Permanent record of all cost changes
- Tracks: former qty/cost, incoming qty/cost, resulting average
- Linked to stock moves for audit trail

### Enhanced Models

#### `product.product`
- New fields:
  - `product_cost_history_ids`: Cost history records
  - `product_cost_ids`: Computed current costs per location
  - `main_wh_cost`: Cost in main warehouse (replaces standard_price in views)
- New methods:
  - `get_last_cost_history()`: Get latest cost for a location
  - `_prepare_internal_in_svl_vals()`: Prepare valuation for internal receipts
  - `_prepare_internal_out_svl_vals()`: Prepare valuation for internal issues

#### `stock.move`
- New methods:
  - `_create_internal_svl()`: Create valuation for internal moves
  - `_get_internal_move_lines()`: Get move lines for internal moves
  - `_is_internal()`: Check if move is internal
  - `product_price_update_before_done()`: Update location costs
- Enhanced `_get_price_unit()`: Returns location-specific cost

#### `stock.valuation.layer`
- New field: `location_id`: Track which location this valuation applies to

#### `stock.warehouse`
- New field: `is_main_warehouse`: Mark as main warehouse

#### `stock.location`
- New fields:
  - `exclude_from_product_cost`: Exclude from cost calculations
  - `apply_in_sale`: Available for sale order selection

#### `sale.order`
- New fields:
  - `picking_location_id`: Selected delivery location
  - `picking_type_id`: Auto-selected picking type

#### `sale.order.line`
- Enhanced `purchase_price`: Location-aware cost calculation
- Enhanced `_compute_qty_at_date()`: Location-aware availability

## Odoo 17 Compatibility Changes

### Version Update
- Module version updated from 18.0.0.0.0 to 17.0.0.0.0

### View Updates
- Changed all `<list>` elements to `<tree>` (Odoo 17 standard)
- Updated XPath expressions from `list` to `tree`
- Fixed view mode from `list,form` to `tree,form`

### Field Updates
- Fixed typo: `check_compnay` → `check_company`
- Maintained all field attributes for Odoo 17 compatibility

### API Compatibility
- All decorators maintained: `@api.depends`, `@api.depends_context`, `@api.model_create_multi`
- Method signatures compatible with Odoo 17
- Proper use of `sudo()` and `with_context()`

## Data Flow

### Receipt to Main Warehouse
1. Create purchase order
2. Receive products into main warehouse
3. System:
   - Creates stock valuation layer with location
   - Updates main warehouse cost history
   - Updates product standard_price
   - Creates journal entries

### Internal Transfer
1. Create internal transfer between locations
2. Validate transfer
3. System:
   - Creates OUT valuation layer (source location, negative qty)
   - Creates IN valuation layer (dest location, positive qty)
   - Updates destination location average cost
   - Creates cost history record
   - If destination is main warehouse, updates standard_price

### Delivery from Location
1. Create sale order with delivery location
2. Confirm order
3. System:
   - Creates delivery from selected location
   - Uses location-specific cost for valuation
   - Creates stock valuation layer with location
   - Creates journal entries using location cost

## Security

### Access Rights
- `access_product_cost_location_user`: All users can CRUD transient cost records
- `access_product_cost_location_history_user`: All users can read/create history (no delete)

## Troubleshooting

### Standard Price Cannot Be Updated
**Issue**: Error when trying to update product cost directly

**Solution**: 
- Products with AVCO by Location cannot have standard_price updated directly
- Use stock moves or revaluation instead
- System automatically maintains costs per location

### Location Not Available in Sale Order
**Issue**: Location doesn't appear in "Deliver From" dropdown

**Solution**:
1. Go to location settings
2. Ensure "Apply in Sale Order" is checked
3. Ensure usage type is "Internal Location"

### Cost History Not Creating
**Issue**: No cost history records appearing

**Solution**:
- Ensure product uses AVCO by Location costing method
- Verify stock moves are validated (done state)
- Check that moves are to/from internal locations

### Landed Costs Not Affecting Location
**Issue**: Landed costs not updating location costs

**Solution**:
- Verify product costing method supports landed costs
- Ensure main warehouse is properly configured
- Check that picking/move has location information

## Limitations

1. **FIFO by Location**: Not implemented - only AVCO supported
2. **Lot Costing**: Lot-level location costing needs testing
3. **Serial Numbers**: Serial number tracking with location costs needs validation
4. **Revaluation**: No built-in wizard for manual location cost adjustment

## Support & Contribution

For issues, questions, or contributions:
- Module Author: Techultra Solutions Private Limited
- Website: https://www.techultrasolutions.com/

## License
OPL-1 (Odoo Proprietary License v1.0)

## Changelog

### Version 17.0.0.0.0 (Current)
- Ported to Odoo 17
- Fixed view syntax (list → tree)
- Fixed field typos (check_company)
- Maintained full backward compatibility
- Enhanced documentation

### Previous Versions
- 18.0.0.0.0: Initial version for Odoo 18
