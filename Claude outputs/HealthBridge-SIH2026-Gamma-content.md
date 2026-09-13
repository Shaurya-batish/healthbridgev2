# HealthBridge — SIH 2026 IDEA Presentation (6 slides)
> Paste into Gamma → "Paste in text" → set to **6 cards**. Keep the six headings exactly; SIH judges score against these fixed sections.

---

## Slide 1 — Idea / Problem Statement

**Problem Statement ID:** [FILL]
**Problem Statement Title:** Accessibility and quality of public healthcare services, particularly in rural and underserved areas
**Theme:** MedTech / HealthTech  |  **PS Category:** Software
**Team Name:** [FILL]  |  **Team ID:** [FILL]

**Idea title:** **HealthBridge** — an offline-capable, ASHA-operated, ABDM/FHIR-linked patient record with explainable AI triage.

**One-line pitch:** A longitudinal digital record that follows a rural patient across sub-centre → PHC → district hospital, with danger-sign triage that reorders the queue and auto-escalates emergencies — strengthening the public system, not replacing it.

---

## Slide 2 — Proposed Solution

**What it is:** Two connected surfaces on one backend — an offline-first field app for the ASHA/frontline worker, and a facility dashboard for doctors and admins.

**How it solves the problem:**
- **Longitudinal record, keyed to ABHA number** — one patient, one thread, visible at every facility level. No repeated history-taking, no lost referrals.
- **Explainable digital triage** — ASHA enters a free-text complaint in the local language; the system flags Red / Yellow / Green *and shows why* ("Red: danger sign — unable to drink/feed").
- **Severity-based queue** — triage reorders tokens automatically; Red cases jump the queue and fire an emergency escalation.
- **Works without internet** — patient registration, triage, and token creation run offline and sync when signal returns.
- **ABDM/FHIR interoperable** — records stored as FHIR resources, so data is portable across the public health stack.

**Innovation & uniqueness:**
- **LLM extracts, rules decide.** The AI only pulls structured facts (symptoms, duration, age); a versioned IMNCI danger-sign rule table assigns severity. Safety is auditable, not a black box.
- **Offline triage engine** runs on-device — rural connectivity never disables the safety-critical path.
- **Adapter architecture** — ABDM, teleconsult, and scheme checks sit behind swappable interfaces, so today's demo becomes tomorrow's production with no rewrite.

---

## Slide 3 — Technical Approach

**Technology stack:**
- **Frontend:** Next.js + TypeScript + Tailwind CSS; ASHA app ships as an installable **offline-first PWA**.
- **Backend:** FastAPI (Python) + REST APIs.
- **Databases:** PostgreSQL (FHIR-shaped records + queue/users) + Redis (queue/cache).
- **AI layer:** LangGraph orchestration, Whisper (local) for voice, and a local/open-weight LLM (**Phi-4-mini via Ollama**) for symptom extraction — chosen for a small footprint on modest PHC hardware and for health-data privacy. Cloud LLM only as an optional online upgrade, never on the triage path.
- **Data model:** FHIR Patient / Encounter / Observation, everything keyed to ABHA number.

**Methodology / process flow (triage):**
Free-text complaint (local language) → **LLM** extracts structured facts only → **IMNCI rule table** assigns Red/Yellow/Green + records which rule fired → queue reorders; Red → auto-escalation → every decision written to an **audit log**. If the LLM is offline, ASHA fills a structured checklist and the *same* rules run.

**Offline sync flow:** Local write queue (IndexedDB) → syncs on reconnect → append-only encounters, server-timestamp-wins conflict rule.

*(Gamma tip: turn the two flows above into a left-to-right diagram.)*

---

## Slide 4 — Feasibility and Viability

**Why it's feasible:**
- Entirely open-source / free-tier stack; local LLM removes per-call API cost and keeps data on-premise.
- Runs on modest hardware already present at PHCs; PWA installs on any Android phone the ASHA already owns.
- Built on approved national rails (ABDM/FHIR) — integration is a defined standard, not an invention.

**Challenges & risks:**
- Intermittent rural connectivity.
- Clinical trust in AI-assisted triage.
- ABDM sandbox onboarding is slow/bureaucratic.
- Low digital literacy among some frontline users.

**Strategies to overcome:**
- **Offline-first by design** — core flows never require a live connection.
- **Explainable + audit-logged triage** with LLM-extracts-only + versioned rules → defensible to a clinician.
- **Mock ABDM adapter from day one** — real gateway swaps in later without blocking deployment.
- **Local-language, voice-assisted, low-text UI** for the ASHA app.

---

## Slide 5 — Impact and Benefits

**Target beneficiaries:** Rural and underserved patients, ASHAs/frontline workers, PHC/CHC doctors, and district health administrators.

**Social impact:**
- Faster care for emergencies — danger-sign cases are surfaced and escalated in minutes, not missed.
- Continuity of care — a patient's history follows them, cutting repeated tests and diagnostic errors.
- Equitable access regardless of connectivity.

**Health-system impact:**
- Accountability & quality monitoring via a live 4-tile facility dashboard (triaged-by-severity, queue length, teleconsults, red cases escalated).
- Interoperable, ABDM-compliant data feeding the national health record.
- Reduced load on higher facilities through better triage and referral at the source.

**Economic benefit:** Lower out-of-pocket cost via fewer avoidable trips and duplicate tests; a scheme-status badge (PMJAY/state) flags entitlements at point of care. Near-zero marginal software cost per additional PHC.

---

## Slide 6 — Research and References

**Supporting rationale:**
- Rural India faces persistent shortfalls in sub-centres, PHCs, and specialist availability (Rural Health Statistics, MoHFW) — access and continuity, not just capacity, are the gap HealthBridge targets.
- IMNCI danger-sign protocols are the established, field-proven basis for frontline triage — the source for the rule table.
- ABDM/FHIR is the Government of India's approved standard for interoperable health records, making the longitudinal-record approach nationally aligned.

**References:**
- Ayushman Bharat Digital Mission (ABDM) — abdm.gov.in
- HL7 FHIR interoperability standard — hl7.org/fhir
- WHO/UNICEF IMNCI guidelines (Integrated Management of Neonatal & Childhood Illness)
- National Health Mission — ASHA programme, MoHFW — nhm.gov.in
- Rural Health Statistics, Ministry of Health & Family Welfare, Government of India
