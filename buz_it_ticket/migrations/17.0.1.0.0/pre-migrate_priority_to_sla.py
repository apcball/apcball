# -*- coding: utf-8 -*-
"""
Migration script to convert Priority field to SLA Level field
This script converts existing priority values to new sla_level values
"""

def migrate(cr, version):
    """
    Convert priority values to sla_level values
    Mapping:
    - priority '0' (Low) → sla_level 'standard'
    - priority '1' (Normal) → sla_level 'important'
    - priority '2' (High) → sla_level 'urgent'
    - priority '3' (Urgent) → sla_level 'critical'
    """
    
    # Update SLA Policy records
    cr.execute("""
        UPDATE it_sla_policy 
        SET sla_level = CASE priority
            WHEN '0' THEN 'standard'
            WHEN '1' THEN 'important'
            WHEN '2' THEN 'urgent'
            WHEN '3' THEN 'critical'
            ELSE 'important'
        END
        WHERE sla_level IS NULL
    """)
    
    # Update IT Ticket records
    cr.execute("""
        UPDATE it_ticket 
        SET sla_level = CASE priority
            WHEN '0' THEN 'standard'
            WHEN '1' THEN 'important'
            WHEN '2' THEN 'urgent'
            WHEN '3' THEN 'critical'
            ELSE 'important'
        END
        WHERE sla_level IS NULL
    """)
    
    # Update SLA Policy references in tickets
    cr.execute("""
        UPDATE it_ticket t
        SET sla_policy_id = p.id
        FROM it_sla_policy p
        WHERE t.category = p.category 
        AND t.sla_level = p.sla_level
        AND t.sla_policy_id IS NULL
    """)