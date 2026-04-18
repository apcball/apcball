# Internal Consumable Request Module (`internal_consume_request`)

## Overview
This module (`internal_consume_request`) provides an internal material requisition system (ขอเบิกอุปกรณ์สิ้นเปลืองภายในบริษัท) for Odoo 17. It allows employees to request consumable or stockable products from the company's internal warehouses.

## Core Features
*   **Employee Requisition**: Employees can create request documents to consume items.
*   **Approval Workflow**: Manager (Head of Department) approval is required before processing.
*   **Stock Validation**: Automatically checks stock availability and prevents requests for items with insufficient stock.
*   **Automated Stock Operations**: Automatically creates a Delivery Order or Internal Transfer (`stock.picking`) upon manager approval.
*   **Cost Tracking**: Enforces the entry of analytic accounts/distribution for all requested items.

## Workflow & State Machine
The request document transitions through the following states:

1.  **Draft (`draft`)**:
    *   An employee creates a new request document.
    *   They select the warehouse, source/destination locations, and add items (`internal.consume.request.line`).
    *   Employees must fill in the **Analytic Distribution** for each item line.
2.  **To Approve (`to_approve`)**:
    *   The user clicks **Submit**.
    *   **Validation**: The system checks two conditions:
        1.  *Analytic Distribution*: All lines must have an analytic distribution set.
        2.  *Stock Availability*: The requested quantity must not exceed the available unreserved stock.
    *   If stock is insufficient, the system **auto-rejects** the document.
    *   If valid, a notification (mail activity) is sent to the Head of Department (Manager).
3.  **Approved (`approved`)**:
    *   The manager clicks **Approve**.
    *   The system performs a secondary stock availability check.
    *   If successful, it automatically triggers `action_create_picking()` to generate a Delivery Order (`stock.picking`) from the source warehouse to the destination location (typically the `Customers` virtual location for consumption).
    *   Notifies the assigned Warehouse Responsible user.
4.  **Done (`done`)**:
    *   The state automatically changes to `Done` when the warehouse staff validates (completes) the generated `stock.picking`. (Implemented via a `button_validate` override on `stock.picking`).
5.  **Rejected (`rejected`)**:
    *   A document can be rejected manually by the manager (via a wizard to input a rejection reason) or automatically by the system due to insufficient stock at the time of submission or approval.

## Technical Implementation Details
*   **Models**:
    *   `internal.consume.request`: The main document header. Tracks employee, manager, warehouse, locations, and overall state.
    *   `internal.consume.request.line`: The items being requested. Tracks product, requested quantity, available quantity, and analytic distribution.
    *   `stock.picking` (inherited): Overrides `button_validate` to back-reference the request and mark it as done.
*   **Stock Calculation**: `available_qty` on the line is computed directly from `stock.quant` in the source location (and its children) by calculating `quantity - reserved_quantity`. It ensures the requested items are genuinely available on hand.
*   **Analytic Integration**: Uses Odoo's standard `analytic_distribution` JSON field to distribute costs across analytic accounts. This ensures costs are properly allocated when the stock is consumed.
*   **Auto-Rejection Logic**: To prevent stock bottlenecks or phantom reservations, any discrepancy between the requested quantity and available quantity instantly forces the document into a rejected state with a detailed reason, preventing the creation of backorders or negative stock situations.
