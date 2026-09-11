# Job Costing Management (buz Project Job Costing)

This module provides comprehensive job costing and project management capabilities specifically designed for the construction and contracting industry. It tracks budgets (planned costs) versus actual costs in real-time across Materials, Labour, and Overheads.

## Core Architecture & Workflow

The module revolves around the **Job Cost Sheet** which aggregates all costs for a specific Project. The workflow integrates natively with Odoo's core apps (Purchase, Inventory, Timesheets, Accounting).

### 1. Job Cost Sheet (`job.cost.sheet`)
The central document for financial control of a project. It is divided into three main cost categories:
* **Materials (Material Cost Line)**: Estimated materials needed.
* **Labour (Labour Cost Line)**: Estimated human resources and working hours.
* **Overhead (Overhead Cost Line)**: Indirect expenses (equipment rental, administrative costs, subcontracts, etc.).
It tracks **Planned Cost**, **Active Cost**, and **Actual Cost** to provide real-time margin analysis.

### 2. Bill of Quantities - BOQ (`boq.boq`)
A detailed document listing all the specific materials, items, and their exact quantities required for the project. It acts as the granular material budget.
* Integrates with the Job Cost Sheet to feed planned material costs.
* Tracks how much has been requisitioned vs total allowed quantity to prevent over-ordering.
* Includes "Waste %" and adjusted quantities.

### 3. Material Requisition (`material.requisition`)
The bridge between project planning and procurement/inventory. Site managers or engineers create MRs to request items from the BOQ.
* **Internal Action**: Generates an **Internal Transfer** (`stock.picking`) to move goods from the main warehouse to the project site.
* **Purchase Action**: Generates a **Purchase Order** (`purchase.order`) to buy materials directly from a vendor for the project.
* Verifies remaining quantities from the BOQ before allowing the request.

### 4. Job Orders / Work Orders (`job.order`)
Represents the actual operational tasks on the ground. Linked to the project, these are used to assign work to teams or subcontractors, track completion stages (`job.stage`), and log timesheets.

### 5. Actual Cost Tracking (Native Odoo Integrations)
To compute the "Actual Cost" on the Job Cost Sheet, the module hooks into standard Odoo models:
* **Purchase Orders (`purchase.order`) & Vendor Bills (`account.move`)**: When POs are received and billed, the system updates the *Actual Material* and *Actual Overhead* costs on the linked Job Cost Sheet.
* **Timesheets (`account.analytic.line`)**: When workers log time against the project/job order, the system calculates the cost (Hours × Hourly Rate) and updates the *Actual Labour* cost.
* **Subcontractor Management (`subcontractor.py`)**: Dedicated tracking for third-party contractor costs and retentions.

## Summary for AI / Developers
If you are extending this module:
1. **Always ensure Analytic Accounts match**: Every cost-bearing transaction (PO, Bill, Timesheet) must be tagged with the Project's Analytic Account to correctly map costs and for standard Odoo reporting.
2. **Link via `job_cost_sheet_id` and `job_cost_line_id`**: For accurate actual cost rollup, transactions (like PO lines or Invoice lines) are often directly linked to a specific Job Cost Line.
3. **Data Flow**: `BOQ` -> `Material Requisition` -> `Purchase Order` -> `Vendor Bill`. Every step in this chain carries forward the project references and analytic distribution.
4. **UI Extensions**: This module extends standard views (e.g., adding `job_cost_sheet_id` to `purchase.order.form` and `account.move.form`). Check the `views/` folder when modifying standard Odoo objects.
