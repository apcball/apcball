# Sales Margin Approval

This module allows setting up margin approval rules for sales orders. When a sales order's margin falls below certain thresholds, it requires approval from designated users before the order can be confirmed.

## Features

- Define margin threshold rules with minimum and maximum margin percentages
- Assign specific users as approvers for each margin range
- Automatically calculate margin percentage on sales orders
- Prevent confirmation of sales orders with low margins until approval
- Track approval states (pending, approved, rejected) in the sales order
- Approval/rejection workflow with optional notes

## Configuration

1. Go to **Sales > Configuration > Margin Approval Rules**
2. Create rules with different margin ranges and assign approvers
3. Make sure your users are added to the "Sales Margin Approvers" security group if needed

## Usage

1. Create a sales order as usual
2. When you try to confirm an order with a margin below defined thresholds, the system will:
   - Block direct confirmation
   - Display a "Request Margin Approval" button
3. Click "Request Margin Approval" to send the request to approvers
4. Authorized approvers can either approve or reject the margin
5. After approval, the order can be confirmed normally

## Technical Information

The module implements:

- Margin validation when confirming sales orders
- Security groups and access rights for approvers
- Custom workflow for the approval process

## Requirements

- Depends on `sale_management` and `sale_margin` modules
