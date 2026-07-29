# Helpdesk Plan

## โครงสร้างเมนู

```text
IT Management
└── Helpdesk
    ├── My Tickets
    ├── Tickets
    └── Configuration
        ├── Categories
        ├── Teams
        └── Stages
```

## ขอบเขต Phase 1

- ใช้ dependency เฉพาะ `base`
- สร้าง root menu `IT Management` และเมนู `Helpdesk` ภายในโมดูลเอง
- มีเฉพาะ `My Tickets`, `Tickets` และ `Configuration`
- ยังไม่รวม Dashboard
- ยังไม่รวม My Assigned Tickets
- ยังไม่รวม Knowledge Base
- ยังไม่รวม Reporting
- ยังไม่รวม SLA Policies
- ใช้ XML ID, actions, models และ security groups ภายในโมดูลเท่านั้น
- ไม่อ้างอิงเมนูหรือ model จากโมดูลอื่น
