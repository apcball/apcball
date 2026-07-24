# Mogen Smart S&OP Optimization

This addon provides deterministic inventory segmentation and policy recommendations for Smart S&amp;OP.

It calculates ABC/XYZ classifications, fixed, days-of-demand, and statistical safety stock, reorder points, and EOQ. Calculations persist the assumptions, input snapshot timestamp, formula version, previous policy values, and proposed values.

Optimization runs and the scheduled job only create recommendations. They never create or update Odoo reorder rules. An S&amp;OP manager must explicitly approve a proposal before it may be considered for a later, separately reviewed policy-application workflow.

Phase 3 foundation for deterministic optimization recommendations. It has no solver, policy update, or operational action in this scaffold.
