# Clinical translation resources

Severity headings, triage instructions, IMNCI rule explanations and checklist
danger-sign labels are **clinical text**. They are never machine translated at
runtime and never shown in a non-English language unless the corresponding
file here is marked `"review_status": "reviewed"` with a named reviewer.

As of 2026-09-15 **no reviewed translations exist**. Every non-English file is
`not_available`, so the ASHA app shows the canonical English text (from
`rules/imnci-rules.v1.json` and `TriageCaptureForm.tsx`) with a visible notice.
Rule ids and severities are never translated or altered.

To add a reviewed translation: fill `messages` using the keys below, have a
qualified clinician fluent in the language review every string against the
English source, then set `review_status` to `reviewed` and `reviewed_by` to the
reviewer and date. `lib/i18n/core.test.ts` refuses a `reviewed` file with no
reviewer.

Keys: `severity.<RED|YELLOW|GREEN>.<header|subtext|action>`, `rule.<RULE-ID>`
(e.g. `rule.GDS-03`, `rule.DEFAULT-01`).
