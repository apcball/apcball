# SLA Policy Redesign Diagram

## Current Structure

```mermaid
erDiagram
    IT_TICKET ||--o{ SLA_POLICY : has
    IT_TICKET {
        string name
        string category
        string priority "Low(0), Normal(1), High(2), Urgent(3)"
        many2one sla_policy_id
        datetime deadline_sla
    }
    SLA_POLICY {
        string name
        string category
        string priority "Low(0), Normal(1), High(2), Urgent(3)"
        float response_time_hours
        float resolve_time_hours
    }
```

## New Structure

```mermaid
erDiagram
    IT_TICKET ||--o{ SLA_POLICY : has
    IT_TICKET {
        string name
        string category
        string sla_level "Standard, Important, Urgent, Critical"
        many2one sla_policy_id
        datetime deadline_sla
    }
    SLA_POLICY {
        string name "User-friendly with Thai translations"
        string category
        string sla_level "Standard, Important, Urgent, Critical"
        float response_time_hours
        float resolve_time_hours
    }
```

## Mapping

| Old Priority | New SLA Level | Thai Translation |
|--------------|---------------|------------------|
| Low (0)      | Standard      | มาตรฐาน          |
| Normal (1)   | Important     | สำคัญ            |
| High (2)     | Urgent        | เร่งด่วน          |
| Urgent (3)   | Critical      | วิกฤต            |

## Example SLA Policy Names

| Category | Old Name | New Name |
|----------|----------|----------|
| Issue | Issue - Low Priority | Issue - Standard (มาตรฐาน) |
| Issue | Issue - Normal Priority | Issue - Important (สำคัญ) |
| Issue | Issue - High Priority | Issue - Urgent (เร่งด่วน) |
| Issue | Issue - Urgent Priority | Issue - Critical (วิกฤต) |
| Access | Access - Low Priority | Access - Standard (มาตรฐาน) |
| Access | Access - Normal Priority | Access - Important (สำคัญ) |
| Access | Access - High Priority | Access - Urgent (เร่งด่วน) |
| Access | Access - Urgent Priority | Access - Critical (วิกฤต) |
| Purchase | Purchase - Low Priority | Purchase - Standard (มาตรฐาน) |
| Purchase | Purchase - Normal Priority | Purchase - Important (สำคัญ) |
| Purchase | Purchase - High Priority | Purchase - Urgent (เร่งด่วน) |
| Purchase | Purchase - Urgent Priority | Purchase - Critical (วิกฤต) |