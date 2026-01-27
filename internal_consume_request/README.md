# Internal Consumable Request

## Overview
Odoo 17 module for internal consumable request system - ขอเบิกอุปกรณ์สิ้นเปลืองภายในบริษัท

## Features
- Employee can create internal consumable requests
- Approval workflow with mail activities
- Automatic delivery/internal transfer creation
- Stock level checking
- Multi-level security (User, Manager, Stock)

## Workflow
1. Employee creates request (Draft)
2. Submit for approval → sends mail activity to manager
3. Manager approves → creates Internal Transfer (Picking)
4. Stock validates picking
5. Request marked as Done

## Models
- `internal.consume.request` - Main request document
- `internal.consume.request.line` - Request line items

## Security Groups
- **User**: Create and view own requests
- **Manager**: Approve team requests
- **Stock User**: Process transfers and view all requests

## Configuration
Default warehouse: ST02
Default picking type: Internal Transfer
Sequence: ICR/00001

## Installation
1. Copy module to addons folder
2. Update apps list
3. Install "Internal Consumable Request" module
4. Assign security groups to users

## Usage
**Menu**: Inventory → Internal Consume → Requests

### For Employees:
1. Create new request
2. Add product lines
3. Submit for approval

### For Managers:
1. Review pending approvals
2. Approve or reject with reason

### For Stock Users:
1. View approved requests
2. Validate transfers
3. Mark requests as done

## Technical
- Odoo Version: 17.0
- License: LGPL-3
- Dependencies: base, hr, stock, mail

## Author
Your Company
