# Stock Request from MO - Quick Guide

## Feature: Direct Stock Request from Manufacturing Order

### What's New
Production teams can now **create stock requests directly from the Manufacturing Order screen** without navigating to the Stock Requests menu.

### How to Use

#### 1. From Manufacturing Order Form
1. Open any confirmed Manufacturing Order
2. Click the **"Stock Request"** button in the header (next to other action buttons)
3. The system will:
   - Create a new stock request
   - Link it to the current MO
   - **Automatically calculate missing components**
   - Pre-fill source and destination locations
   - Open the stock request form for review

#### 2. Review and Adjust
- Review the auto-calculated missing components
- The system shows:
  - **To Consume**: Total required quantity
  - **Consumed**: Already consumed quantity
  - **Calculated shortage**: What needs to be requested
- Adjust quantities if needed
- Add or remove lines manually

#### 3. Confirm and Process
- Click **"Confirm"** to create the internal transfer
- Navigate to the transfer to validate and issue materials
- Return to stock request to **"Allocate to MO"** after materials are issued

### Smart Button
- When stock requests exist for an MO, a **smart button** shows the count
- Click to view all stock requests linked to that MO

### What Gets Auto-Calculated

The system analyzes each raw material component and calculates:

```
Shortage = Required Qty - Already Consumed - (Optional: Reserved Qty)
```

**Configurable via System Parameters:**
- `mrp_stock_request.shortage_policy`:
  - `subtract_done` (default): Only subtracts consumed quantities
  - `subtract_done_and_reserved`: Also subtracts reserved quantities

### Example Workflow

**Scenario**: MO needs 30 units of Stool Top, but only 20 are available

1. Production team opens MO WH/MO/00009
2. Sees "To Consume: 30.00" but only 20.00 in stock
3. Clicks **"Stock Request"** button
4. System creates request with line:
   - Product: Stool Top
   - Requested: 10.00 (the shortage)
5. Production team confirms request
6. Warehouse team fulfills the transfer
7. Production team allocates materials to MO

### Benefits

✅ **Faster**: No need to navigate multiple menus  
✅ **Automatic**: Missing components calculated automatically  
✅ **Accurate**: Based on real-time consumption data  
✅ **Integrated**: Direct link between MO and stock requests  
✅ **Traceable**: Full audit trail via smart buttons  

### Button Visibility

The **"Stock Request"** button appears when:
- MO state is: Confirmed, In Progress, or To Close
- Hidden for: Draft, Done, or Cancelled MOs

### Technical Details

**Location Setup:**
- Source Location: From MO's `location_src_id`
- Destination Location: From MO's `location_dest_id`
- Picking Type: Auto-selected internal transfer type

**Shortage Calculation:**
- Considers UoM conversions
- Aggregates across all components
- Respects product rounding
- Only includes storable products (type='product')

### Multi-MO Support

While this feature creates a request for one MO, users can:
1. Create request from MO #1
2. Edit request to add more MOs via `mo_ids` field
3. Click "Prepare from MOs" again to recalculate
4. System aggregates shortages across all selected MOs

---

**Module**: `buz_mrp_stock_request`  
**Version**: 17.0.1.0.0  
**Feature Added**: Direct MO → Stock Request integration
