# RFQ Job Costing Integration

## Overview
This implementation adds Job Cost Center and Job Cost Line fields to the Purchase Order (RFQ) form, allowing users to directly link purchase order lines to specific job cost items.

## Features Added

### 1. New Fields in Purchase Order Lines
- **Job Cost Center**: Select the approved job cost sheet that this purchase relates to
- **Job Cost Line**: Select the specific cost line item within the job cost sheet

### 2. Automatic Linking
- When selecting a Job Cost Center, the system automatically filters available Job Cost Lines
- When selecting a Job Cost Line, the system automatically populates:
  - Product (if specified in the cost line)
  - Quantity (planned quantity from cost line)
  - Unit Price (unit cost from cost line)
  - Analytic Account (from the job cost sheet)

### 3. Smart Domains
- Job Cost Center field shows only approved cost sheets
- Job Cost Line field shows only material and overhead cost types
- Both fields prevent creation of new records from the interface

## Usage Instructions

### For RFQ/Purchase Orders:
1. Open a new RFQ or Purchase Order
2. In the order lines, you'll see two new fields:
   - **Job Cost Center**: Select the relevant job cost sheet
   - **Job Cost Line**: Select the specific cost line item

### Workflow:
1. Select **Job Cost Center** first
2. The **Job Cost Line** dropdown will be filtered to show only relevant cost lines
3. Upon selecting a Job Cost Line, the product, quantity, and price will be auto-populated
4. Review and adjust as needed
5. Confirm the purchase order

### Integration Points:
- Purchase Order Lines ↔ Job Cost Lines
- Actual costs from confirmed purchase orders update the job cost sheet
- Analytic accounting is automatically handled

## Technical Implementation

### Models Extended:
- `purchase.order.line`: Added `job_cost_sheet_id` and enhanced `job_cost_line_id`
- Enhanced onchange methods for automatic field population

### Views Modified:
- Purchase Order form view (including RFQ)
- Purchase Order Line tree and form views
- Added proper domains and options for field controls

### Automatic Cost Tracking:
- When purchase orders are confirmed, actual costs are automatically updated in the linked job cost lines
- Real-time variance calculation between planned and actual costs

## Benefits:
1. **Streamlined Workflow**: Direct linking from RFQ to job cost items
2. **Accurate Cost Tracking**: Automatic update of actual costs
3. **Better Project Control**: Real-time visibility of cost variances
4. **Integrated Planning**: Links purchasing decisions to project budgets

## Field Descriptions:
- **Job Cost Center**: The main job cost sheet (project-level costing document)
- **Job Cost Line**: Specific line item within the cost sheet (material, labour, or overhead)

This implementation follows Odoo best practices and provides seamless integration with existing job costing workflows.
