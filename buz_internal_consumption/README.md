# Internal Consumption Request Module

## Overview
This module enables users to request internal consumption of inventory items with multi-level approvals, automatic stock movements, and accounting entries.

## Features
- Create internal consumption requests with multiple lines
- Multi-level approval workflow (Draft → Submitted → Manager Approved → Store Done → Accounted)
- Automatic stock movement creation when items are issued
- Automatic accounting entry creation for expense recognition
- Support for analytic accounting (accounts and tags)
- Configurable expense policies (standard cost, FIFO, valuation-based)
- Comprehensive reporting

## Configuration
- Set default accounts, locations, and journals in company settings
- Configure user permissions through security groups
- Define expense accounts at product category level

## Usage
1. Create a new Internal Consumption Request
2. Add products to consume with quantities
3. Submit for approval
4. Manager approves the request
5. Store personnel issue the items (creates stock moves)
6. Accounting personnel create journal entries (or use automatic valuation)

## Security Groups
- IC User: Create and edit own requests
- IC Manager: Approve/reject requests
- IC Store: Issue items from stock
- IC Accountant: Create accounting entries

## Dependencies
This module depends on: stock, account, mail, analytic, hr