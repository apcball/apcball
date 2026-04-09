# Objective
Add export UX for stock picking

---

## Button

Location:
stock.picking form

Button:
"Export Excel"

---

## Wizard (optional for batch)

Fields:
- date_from
- date_to
- picking_type (incoming/outgoing/internal)
- multi-select picking_ids

Buttons:
- Export

---

## UX Behavior

Single record:
→ download immediately

Multiple records:
→ use wizard

---

## Enhancement

- progress bar (if large data)
- preview summary before export