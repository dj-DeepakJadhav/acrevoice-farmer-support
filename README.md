# AcreVoice

**Turn one farmer phone call into evidence an adviser can safely act on.**

AcreVoice helps agricultural advisers resolve missing information in a farmer's
area-aid application (GAP / Sammelantrag). Instead of repeated calls, letters, or asking
someone to navigate another portal, the farmer answers a few focused questions by phone.
The adviser receives a reviewable correction package — not an automatic submission.

For farmers, it means no app, account, or portal login: just a short call in their
language. For advisory teams, it means less phone tag and a clear record of what was
asked, what was said, and what was confirmed before a value is entered elsewhere.

## The problem

An agricultural adviser works with detailed area-aid records. When information is missing or
inconsistent, the adviser's options today are a letter, a game of phone tag, or asking
the farmer to log into a portal they have never used. Missing information delays review and creates avoidable follow-up. AcreVoice does not claim a blank field automatically causes a lost payment.

## The customer journey

1. **Find the problem.** Import a partially completed application and see exactly what is
   blocking review.
2. **Ask by phone.** With consent, call the farmer in German or English and ask only the
   missing questions.
3. **Create evidence.** Read each answer back, distinguish exact from uncertain language,
   and retain the question, spoken answer, confirmation, and timestamp.
4. **Keep a human accountable.** The adviser reviews each proposed correction and may
   approve only exact, confirmed values.
5. **Export the hand-off.** Download a CSV/JSON correction package with the evidence needed
   to enter the change into the official portal or case file.

It does **not** decide eligibility, approve a subsidy, or submit anything to a
government system. A human does that, with the evidence in front of them.

## Why a phone-first workflow matters

The farmer often has the missing fact but not the time, device, confidence, or desire to
use another online system. The adviser needs more than a note saying “farmer called”: they
need a defensible answer they can review later. AcreVoice protects both sides — it makes
the call easier for the farmer and the resulting record more useful for the adviser.

## Next product iteration: AcreVoice Förderlotse

The current application demonstrates the first operational slice: completing a known,
incomplete case by phone. The next iteration turns that slice into a **farmer-support goal**:

`understand the request → show dated official sources → collect missing facts by consented callback → create evidence → human review or expert routing → export a hand-off`

The product will begin with one Land and a small, curated catalogue of official sources. It
will say *“possible fit — verify with an adviser”*, never *“you are eligible.”* It will not
replace Länder portals or make legal, payment, or eligibility decisions.

## Why this needs an agent

Farmers speak; they do not fill in forms.

| The farmer says | AcreVoice records |
|---|---|
| „zweiundvierzig Komma fünf Hektar" | `42.5` — exact |
| „so knapp 43 Hektar ungefähr" | `43` — **flagged approximate** |
| „vielleicht, ich glaube schon" | `unknown` — **refused, needs follow-up** |
| „keine Ahnung" | `unknown` — refused |

Strands handles language interpretation; deterministic guards also reject obvious hedges
and prevent approximate values from being approved. The offline demo uses a limited
deterministic policy, not a live model. Putting an unverified number on a subsidy application is precisely the failure
this product exists to prevent.

## Quick start

No credentials needed — the local demo is fully deterministic.

```bash
python3.14 -m venv .venv
./.venv/bin/pip install -e . -r requirements.txt
PYTHONPATH=src ./.venv/bin/python -m acrevoice
```

Adviser console at <http://127.0.0.1:8080>:

```bash
PYTHONPATH=src ./.venv/bin/python -m acrevoice web
```

Tests:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests -q
```

### Optional: real phone calls and a live model

Copy `.env.example` to `.env` and fill in what you have. Every key is optional — without
them the demo runs on the deterministic provider and a deterministic policy.

```bash
cp .env.example .env
./.venv/bin/python scripts/check_credentials.py   # verifies keys, consumes no calls
```

| Variable | Purpose |
|---|---|
| `CALLE_API_KEY` | Real outbound calls via CALL-E |
| `DEMO_PHONE_NUMBER` | Number to call, E.164 (e.g. `+4915112345678`) |
| `AWS_BEARER_TOKEN_BEDROCK` | Bedrock Projects key for the Strands agent |
| `MANTLE_MODEL_ID` | Default `google.gemma-4-31b` |

Then:

```bash
PYTHONPATH=src ./.venv/bin/python -m acrevoice --live
```

## How to demo

1. Start the server:
   ```bash
   PYTHONPATH=src ./.venv/bin/python -m acrevoice web
   ```
2. Open <http://localhost:8080> — you'll see a case queue (Fallliste).
3. Click any case to view details:
   - See the scheme (e.g. ÖR2) and what's at stake.
   - For each missing field, see why it matters.
4. Click "Call farmer" to place a demo call (uses a simulated farmer).
5. After the call, review the evidence:
   - See original value → proposed value.
   - Confirmation status (✓ confirmed, ✗ not confirmed).
6. Select exact, confirmed values and click "Approve selected and export".
7. Download CSV or JSON, or print the package. Downloads survive reloads.
8. On another open case choose "Approximate / hedged answers". Run the simulated
   call and verify that uncertain values cannot be approved.
9. Try "Consent declined" and "Account problem" to see their different next actions.

To use your own data, upload a CSV file (import button in the header) — see
`data/sample_import.csv` for the expected shape.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for diagrams and the case state machine.

| Component | File |
|---|---|
| Adviser console | `server.py`, `static/index.html` |
| Case workflow | `workflow.py` | Current correction-case state machine; target support-goal state machine |
| Strands agent | `agent.py` | Current answer normalisation; target case-goal orchestration |
| CALL-E adapter | `call_adapter.py` | Call prompt, result schema, outcome mapping; target consented callback tool |
| Locale layer (DE/EN) | `locale.py` |
| Append-only audit store | `store.py` |

**Stack:** Python 3.14 · Strands Agents SDK · Amazon Bedrock · CALL-E · FastAPI · SQLite ·
no build step, no framework on the front end.

## Guarantees the code enforces

These are tested, not merely claimed:

- **An unconfirmed answer is never applied.** "The farmer said it" and "the farmer
  confirmed the read-back" are different states.
- **The source record is never overwritten.** Corrections live beside the original.
- **The audit log is append-only** — SQLite triggers reject `UPDATE` and `DELETE`.
- **Refused, unreachable, partial, hedged or approximate answers require follow-up.**
  An adviser may approve a confirmed subset, but cannot apply uncertain values.
- **Account failures are not farmer failures.** A billing or region error never becomes a
  follow-up case against a farmer.
- **No endpoint manufactures its own evidence.** Review refuses a case with no recorded
  call.

## Languages

German and English are both first-class, with two independent settings:

- **Console language** — what the adviser reads, switchable at any time.
- **Call language** — what the farmer hears, set per case.

For the hackathon walkthrough, the console defaults to English and a newly created
Förderlotse support case uses an English demo callback. German remains selectable before
calling a German-speaking farmer. In the English console, German programme codes such as
`ÖR2` and `GLÖZ 8` are shown with their English meaning in parentheses.

An evaluator who speaks no German can follow an entirely German phone call from an
English console. Scheme explanations and field labels follow the console language. The question the farmer was asked is stored in the language it was
asked in and is never re-translated — it is evidence.

## Scope and safety

- Consent is requested before any question, and refusal ends the call politely.
- **Public programme data, synthetic farm data.** Source cards are dated official Bavarian programme and application guidance. Holdings, application fields, transcripts and call answers are synthetic so the demo never represents a real farm applicant.
- This is a local hackathon prototype, with no measured pilot outcomes. A production pilot requires recorded consent, encryption, retention and deletion
  rules, access control, a German GDPR review, and a processor agreement with the phone
  provider.

## Licence

MIT — see [LICENSE](LICENSE).

## Verified readiness

See [the readiness report](docs/READINESS_REPORT.md) for test evidence, the live
Strands smoke check, limitations, and the remaining submission gates.
[The submission plan](docs/SUBMISSION_PLAN.md) uses the official judging rubrics.

The scheme cards are source-linked context, not an eligibility rules engine or
a live source-retrieval system. Flower-strip examples use **ÖR1b**, not ÖR3
(agroforestry). The former GLÖZ 8 fallow minimum is not presented as current law.

The web server binds to localhost. Do not expose a credentialed instance as a
public judge demo: it has no authentication or tenant isolation.
