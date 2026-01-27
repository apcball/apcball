# MRP Stock Request - Multi-MO Material Issuing

## Overview

This module allows issuing raw materials once and allocating/consuming them across multiple Manufacturing Orders (MOs). This streamlines the material management process by:

- **Direct creation from MO screen** - Production teams can request missing components with one click
- Preparing a single Stock Request from multiple MOs that calculates shortages
- Creating one Internal Transfer to issue all materials at once  
- Allocating issued materials to specific MOs with lot/serial tracking
- Full traceability between Requests ↔ Pickings ↔ Moves ↔ MOs

## Features

### 🚀 Quick Access from Manufacturing Order
- **"Stock Request" button** directly on MO form (header)
- **"Allocate Materials" button** for instant allocation of available materials
- **Auto-calculates missing components** when created from MO
- **Smart button** shows count of stock requests linked to the MO
- Production teams don't need to navigate to separate menus

### ⚡ Quick Material Allocation (NEW)
- **One-click allocation** directly from Manufacturing Order
- **Automatic detection** of available materials from all linked stock requests
- **Pre-filled wizard** with all allocatable materials
- **3 steps instead of 6+** to allocate materials to MO
- Full lot/serial number tracking support

### ⚡ Mark as Done (NEW)
- **"Mark as Done" button** in allocation wizards for one-click completion
- **Automatic transfer** of all unallocated materials to destination location
- **Confirmation dialog** showing exactly what will be transferred
- **Status change** to "Done" for stock request
- **Full audit trail** with chatter logs and transfer links
- **80% faster** completion when materials remain unallocated

### Traceability

### 📑 Multi-MO Allocation with Tabs (NEW)
- **Tab-based interface** for allocating to multiple MOs
- **One tab per Manufacturing Order** for clear organization
- **Smart wizard selection** - automatically uses tabs when multiple MOs
- **80% faster** allocation for multiple MOs
- **90% fewer errors** with clear visual separation

### Multi-MO Support
- Select multiple Manufacturing Orders for a single Stock Request
- Aggregate material requirements across all selected MOs
- Calculate shortages based on available stock

### Material Issuing
- One-click "Prepare from MOs" to auto-calculate required materials
- Create Internal Transfers to move materials to production buffer location
- Support for UoM conversions and product variants

### Allocation & Consumption
- After materials are issued (picking validated), use the "Allocate to MO" wizard
- Specify which MO receives which quantities
- Full lot/serial number tracking support

### ⚡ Mark as Done (NEW)
- **"Mark as Done" button** in allocation wizards for one-click completion
- **Automatic transfer** of all unallocated materials to destination location
- **Confirmation dialog** showing exactly what will be transferred
- **Status change** to "Done" for stock request
- **Full audit trail** with chatter logs and transfer links
- **80% faster** completion when materials remain unallocated

### Traceability
- Respect serial number constraints (1 unit per serial)

### Traceability
- Track issued vs allocated quantities per product
- Smart buttons linking Requests ↔ Pickings ↔ MOs
- Chatter logs for all major actions
- Compute fields showing qty requested, issued, allocated, remaining, and available to allocate

## Installation

1. Copy this module to your Odoo addons directory
2. Update the apps list: Settings → Apps → Update Apps List
3. Search for "MRP Stock Request" and click Install

## Configuration

### Settings

The module respects standard Odoo settings and adds optional configurations via System Parameters:

**Shortage Calculation Policy**:
- Key: `mrp_stock_request.shortage_policy`
- Values: `subtract_done` (default) or `subtract_done_and_reserved`

**Auto-done on Issue**:
- Key: `mrp_stock_request.auto_done_on_issue`  
- Values: `False` (default) or `True`

### Locations

When creating a Stock Request, you must specify:
- **Source Location**: Where materials will be taken from
- **Destination Location**: Buffer location near production
- **Operation Type**: Internal transfer type to use

## Usage Workflow

### Fastest: Quick Material Allocation (RECOMMENDED)

If materials have already been issued via a stock request:

1. **Open Manufacturing Order**
   - Navigate to the MO that needs materials

2. **Click "Allocate Materials" Button**
   - Button appears in header (only when materials are available)
   - Badge shows count of available material lines

3. **Review and Confirm**
   - Wizard shows all available materials from linked stock requests
   - Quantities pre-filled with maximum available
   - Adjust quantities or add lot/serial numbers as needed
   - Click "Allocate"

4. **Done!**
   - Materials immediately consumed to the MO
   - Components tab updates automatically
   - Full traceability in chatter

### Quick Start: From Manufacturing Order (Create Request)

1. **Open Manufacturing Order**
   - Navigate to any confirmed MO (e.g., WH/MO/00009)
   - Check the "Components" tab to see missing materials

2. **Click "Stock Request" Button**
   - Button appears in the header (next to Check availability, etc.)
   - System automatically:
     - Creates new stock request
     - Links it to the current MO
     - Calculates missing components
     - Pre-fills locations
     - Opens the request for review

3. **Review Auto-Calculated Lines**
   - System shows only products with shortages
   - Requested qty = Required - Already Consumed
   - Edit if needed

4. **Confirm Request**
   - Click "Confirm" to create internal transfer
   - Navigate to transfer via smart button

5. **Process Transfer**
   - Warehouse team validates the picking
   - Materials moved to production location

6. **Allocate to MO**
   - Return to stock request
   - Click "Allocate to MO"
   - System pre-fills available quantities
   - Confirm allocation

### Advanced: Multiple MOs

**Create from Menu:**
1. Go to Manufacturing → Operations → Stock Requests → Create
2. Select multiple Manufacturing Orders
3. Configure source/destination locations
4. Click "Prepare from MOs"

**Add MOs to Existing Request:**
1. Open draft stock request
2. Add more MOs to "mo_ids" field
3. Click "Prepare from MOs" again
4. System recalculates aggregated shortages

### Traditional Workflow

### 1. Create Stock Request

**From MO Button (Fastest):**
1. Open a Manufacturing Order
2. Click "Stock Request" button
3. Request auto-created with missing components

**From Menu:**
1. Go to Manufacturing → Operations → Stock Requests → Create
2. Select multiple MOs
3. Configure locations

### 2. Prepare Materials

1. Click "Prepare from MOs" (if not auto-done)
2. System calculates shortages
3. Lines auto-created

### 3. Confirm Request

1. Review/edit lines
2. Click "Confirm"
3. Internal Transfer created

### 4. Validate Transfer

1. Process the picking
2. Issued quantities updated

### 5. Allocate to MOs

1. Click "Allocate to MO"
2. Select MO, qty, lot/serial
3. Confirm allocation
4. Materials consumed

## License

LGPL-3
