# Mogen Smart S&OP AI

Auditable AI gateway integration for Smart S&amp;OP. This addon queues analyses for cron-based background processing and sends structured requests only through a configurable AI gateway client.

Provider records never store API keys. Configure `api_key_reference` as `env:VARIABLE_NAME` or `config:mogen_sop_ai.parameter_name`; the credential is resolved only at execution time.

All responses must be structured JSON. Product, warehouse, scenario, quantity, date, access, and allowed-action validation occurs before AI recommendations are stored. Approved AI recommendations can create only draft core S&amp;OP recommendations; this addon cannot confirm or post purchase, manufacturing, transfer, invoice, or accounting documents.

Phase 3 foundation for an auditable external AI gateway and Smart S&amp;OP Copilot. The OWL source layout is reserved without registering a client action or calling an AI provider.
