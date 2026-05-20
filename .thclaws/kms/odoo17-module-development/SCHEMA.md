# Schema

Describe the shape of pages in this KMS — required sections, naming
conventions, cross-link style.

## Canonical page shape

Write frontmatter + body. `title:`, `topic:`, and `sources:` are
the three keys every page should carry. `KmsWrite` auto-injects
the `# {title}` / `Description: {topic}` / `---` header block
between the frontmatter and the body when the body doesn't
already start with a `# heading`.

```
---
title: Human-readable title
topic: One-line description of what this page covers
sources: ["https://…", "session-XYZ", "memory"]   # required: provenance
category: optional grouping for the index
tags: [optional, free-form]
---

(body content)
```

`sources:` values: external URLs for web-sourced facts,
`session-<id>` for facts learned in a chat session, `memory`
for stable user-supplied context, or `[]` for opinion /
convention pages that genuinely have no external source
(still write the empty list — it's an explicit ack, not an
omission).

Pages with no `verified:` frontmatter pick up a soft warning
when read; pages with `verified:` older than 90 days get a
staleness banner. The research pipeline stamps `verified:` on
every page it writes — manual `KmsWrite` callers can stamp it
too when they've checked the source against current reality.
