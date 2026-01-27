# Installation and Usage Guide - RFQ Job Costing Integration

## Installation Instructions

### 1. Prerequisites
Ensure the following Odoo modules are installed:
- `project` - Project Management
- `purchase` - Purchase Management
- `stock` - Inventory Management
- `hr_timesheet` - Timesheets
- `account` - Accounting
- `analytic` - Analytic Accounting

### 2. Module Installation
1. Place the `job_costing_management` module in your Odoo addons directory
2. Update the addons list in Odoo
3. Install the module from Apps menu

### 3. Post-Installation Setup
1. Go to **Settings > Users & Companies > Groups**
2. Assign users to appropriate job costing groups:
   - `Job Costing User` - Can view and create job cost sheets
   - `Job Costing Manager` - Full access to job costing features

## Quick Start Guide

### Step 1: Create a Job Cost Sheet
1. Navigate to **Job Costing > Job Cost Sheets**
2. Click **Create**
3. Fill in the required information:
   - Name (auto-generated)
   - Project/Contract
   - Job Order (optional)
   - Analytic Account
4. Add cost lines in three categories:
   - **Material Costs**: Products and materials needed
   - **Labour Costs**: Human resources requirements
   - **Overhead Costs**: Equipment, utilities, and other indirect costs
5. **Approve** the cost sheet when ready

### Step 2: Create RFQ from Job Cost Sheet
There are two ways to create RFQs linked to job cost sheets:

#### Method A: Using the Wizard (Recommended)
1. Open an approved Job Cost Sheet
2. Click the **Create RFQ** button in the top-right corner
3. In the wizard:
   - Select the **Vendor**
   - Choose which **Cost Lines** to include
   - Click **Create RFQ**
4. The system will create a new RFQ with all selected items

#### Method B: Manual Linking in RFQ
1. Go to **Purchase > Requests for Quotation**
2. Create a new RFQ
3. In each order line:
   - Select **Job Cost Center** (the job cost sheet)
   - Select **Job Cost Line** (specific cost item)
   - Product, quantity, and price will auto-populate
4. Review and confirm the RFQ

### Step 3: Purchase Order Confirmation
1. When you confirm a purchase order that's linked to job cost lines:
   - Actual costs are automatically updated in the job cost sheet
   - Cost variances are calculated in real-time
   - Analytic accounts are properly updated

## Features Overview

### RFQ/Purchase Order Enhancements
- **Job Cost Center field**: Links to the main job cost sheet
- **Job Cost Line field**: Links to specific cost line items
- **Automatic field population**: When selecting a job cost line, product, quantity, and price are auto-filled
- **Smart filtering**: Job Cost Line dropdown shows only relevant items based on selected Job Cost Center

### Job Cost Sheet Features
- **Three-tab structure**: Materials, Labour, Overheads
- **Real-time cost tracking**: Planned vs Actual costs
- **Variance analysis**: Automatic calculation of cost differences
- **Purchase order integration**: Smart button to view related purchase orders
- **Create RFQ wizard**: Quick creation of RFQs from cost lines

### Reporting and Analytics
- **Cost variance reports**: Track budget vs actual spending
- **Purchase order traceability**: See which POs relate to which cost lines
- **Project cost overview**: Comprehensive cost tracking per project

## Best Practices

### 1. Job Cost Sheet Setup
- Create detailed cost lines with accurate estimates
- Include all expected materials and overhead costs
- Approve cost sheets before creating purchase orders
- Regularly review and update estimates

### 2. Purchase Order Management
- Always link PO lines to job cost lines when possible
- Use the RFQ wizard for bulk purchasing from cost sheets
- Review cost variances regularly
- Ensure proper vendor selection

### 3. Cost Control
- Monitor actual vs planned costs weekly
- Investigate significant variances immediately
- Update job cost sheets when scope changes
- Use analytic reports for project profitability analysis

## Troubleshooting

### Common Issues

#### RFQ Fields Not Showing
- Verify the module is properly installed
- Check user permissions (Job Costing User group required)
- Refresh the page or clear browser cache

#### Job Cost Lines Not Filtering
- Ensure Job Cost Sheet is approved
- Check that cost lines have the correct cost type (material/overhead for purchase orders)
- Verify the job cost sheet has cost lines defined

#### Actual Costs Not Updating
- Confirm purchase orders are in 'Purchase' or 'Done' state
- Check that PO lines are properly linked to job cost lines
- Verify products are received (for material costs)

### Support
For technical support or feature requests, contact the module developer or your system administrator.

## Advanced Configuration

### Custom Cost Types
You can extend the system to include custom cost types by:
1. Modifying the `cost_type` selection field in `job.cost.line`
2. Updating the purchase order domain filters accordingly
3. Adjusting reports and views as needed

### Integration with Other Modules
This module is designed to work with:
- Project Management (project tasks, milestones)
- Inventory Management (stock moves, receipts)
- Accounting (journal entries, analytic lines)
- HR Timesheets (labour cost tracking)

The module provides a comprehensive solution for construction project cost management within the Odoo ecosystem.
