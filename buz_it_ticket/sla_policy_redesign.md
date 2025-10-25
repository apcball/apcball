# SLA Policy Redesign Plan

## Current Implementation
- SLA Policies are defined per category and priority combination
- Priority field exists in tickets with values: Low (0), Normal (1), High (2), Urgent (3)
- SLA Policy has a priority field that matches the ticket priority
- Multiple places reference priority field throughout the system

## New Design
We will remove the Priority field completely and use only SLA Policy with user-friendly names.

### Changes to SLA Policy Model
1. Remove the `priority` field from `it.sla.policy` model
2. Add a `sla_level` field with user-friendly names:
   - 'standard' → 'Standard (มาตรฐาน)'
   - 'important' → 'Important (สำคัญ)'
   - 'urgent' → 'Urgent (เร่งด่วน)'
   - 'critical' → 'Critical (วิกฤต)'

3. Update the unique constraint to use `sla_level` instead of `priority`
4. Update the `get_sla_policy` method to use `sla_level`

### Changes to IT Ticket Model
1. Remove the `priority` field from `it.ticket` model
2. Add a `sla_level` field that references the SLA Policy
3. Update the `_set_sla_policy` method to use the new `sla_level`

### User-Friendly Names
The SLA Policies will have names that are more descriptive and user-friendly:
- Issue - Standard Response (8h response, 72h resolve)
- Issue - Important Response (4h response, 24h resolve)
- Issue - Urgent Response (2h response, 8h resolve)
- Issue - Critical Response (0.5h response, 4h resolve)

Similar patterns for Access and Purchase categories.

### Benefits
1. Users will have a clearer understanding of what each SLA level means
2. The system will be simpler with only one concept (SLA Policy) instead of two (Priority + SLA Policy)
3. The Thai translations will help local users understand the urgency levels

## Implementation Steps
1. Update the SLA Policy model
2. Update the SLA Policy data with new names and levels
3. Update the IT Ticket model
4. Update all views to use SLA Policy instead of Priority
5. Update search filters and groupings
6. Update reports and mail templates
7. Update demo data and wizards
8. Test all changes

## Migration Strategy
1. Create a migration script to:
   - Convert existing priority values to new sla_level values
   - Update existing tickets to use the new sla_level field
   - Remove the old priority field