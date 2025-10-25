# IT Ticket Management System

A comprehensive IT ticketing system for Odoo that handles three main workflows:

1. **Issue/Repair**: Report problems → Work in progress → Request more info (if needed) → Resolved → Closed
2. **Access Request**: Requester → Manager approval → IT implementation → Closed
3. **Purchase Request**: Requester → Manager approval → IT verification → PO creation → Receive items → Closed

## Features

* Separate workflows for different ticket categories
* SLA tracking and breach notifications
* ISO-compliant reporting
* Dashboard with graphs and pivots
* Multi-company support
* Security groups with proper access rights
* Demo data for testing

## Installation

1. Copy the module to your Odoo addons directory
2. Update the module list in Odoo
3. Install the "IT Ticket Management System" module

## Configuration

### Security Groups

The module creates the following security groups:

* **IT Requester**: Employees who can create IT tickets
* **IT User**: IT staff who handle tickets
* **IT Manager**: IT managers with full access
* **IT Approver**: Managers/HR/Finance who can approve requests
* **IT ISO Auditor**: Users who can read and print ISO reports

### SLA Policies

Configure SLA policies in Settings → Configuration → SLA Policies. Define response and resolution times for different categories and priorities.

### Access Templates

Create access templates in Settings → Configuration → Access Templates to speed up access request creation.

## Usage

### Creating Tickets

1. Go to IT Tickets → Tickets → Create
2. Select the category (Issue/Repair, Access Request, or Purchase Request)
3. Fill in the required information
4. Submit the ticket

### Managing Tickets

* **Issue/Repair**: IT staff can start work, request more info, resolve, and close tickets
* **Access Request**: Managers approve/reject, IT staff implement access
* **Purchase Request**: Managers approve, IT staff create PO, mark items as received

### Reports

Generate ISO-compliant reports from the Reports menu:
* Issue Report
* Access Request Report
* Purchase Request Report
* Ticket Summary Report

### Dashboard

View statistics and trends from the Dashboard menu:
* Ticket counts by category and status
* SLA breach statistics
* Response and resolution time metrics
* Department-wise ticket distribution

## Technical Details

### Models

* `it.ticket`: Main ticket model with state machines for three workflows
* `it.ticket.line`: Line items for access and purchase tickets
* `it.sla.policy`: SLA policies for different categories and priorities
* `it.access.template`: Templates for common access requests

### Workflows

#### Issue/Repair
draft → submitted → in_progress → pending_info → resolved → closed (or cancel)

#### Access Request
draft → submitted → waiting_manager → approved → implementing → closed (or rejected/cancel)

#### Purchase Request
draft → submitted → waiting_manager → waiting_it → po_created → received → closed (or rejected/cancel)

## License

This module is licensed under LGPL-3.

## Support

For support and customization, please contact BUZ.