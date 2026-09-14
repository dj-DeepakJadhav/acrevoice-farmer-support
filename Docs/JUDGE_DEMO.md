# AcreVoice judge demo — recording runbook

Treat this as a short product story, not a presentation. Use one fictional
farm case to protect privacy. If the live setup is ready, use a real,
consented test call; if it is not, fix the setup before recording rather than
trying to explain around it.

## Non-negotiable truth standard

- Say **fictional farm case** once at the start. Do not call the phone
  conversation, provider result, or Bedrock runtime live unless it is visibly
  live in this recording.
- Do not show the local rehearsal path (`demo` provider) as evidence of a
  CALL-E or Bedrock integration.
- If the live call or model configuration fails, stop the recording. Fix it,
  re-run the checks, and record a clean take. Do not narrate around a failure.

## Five-minute sequence

| Time | Screen and action | What the judge must see | Say only this |
| --- | --- | --- | --- |
| 0:00–0:25 | Home | The target user and the bounded problem | “A small missing detail can create days of phone tag. AcreVoice helps the farmer answer one focused question without giving the adviser another untraceable note to manage.” |
| 0:25–0:45 | Sources & trust | Dated official guidance and no eligibility claim | “We begin with public guidance. AcreVoice does not decide eligibility, payments, or submissions.” |
| 0:45–1:10 | Create a support goal | A fictional case and the consent-first boundary | “This fictional case is missing two details. We only ask for a callback when the farmer has agreed to it.” |
| 1:10–2:10 | Live CALL-E callback | One real, English, consented call; question, read-back, confirmation | “The call stays focused: two missing facts, a read-back, and a clear confirmation before anything is recorded.” |
| 2:10–2:55 | Returned case evidence | Provider call ID, transcript/result, question, spoken response, confirmation, and the Evidence Passport | “The adviser can see what was asked, what the farmer said, and what was confirmed—without having to trust a loose summary.” |
| 2:55–3:35 | Strands / Bedrock proof | Running configuration and a tool-backed normalisation result | “The agent helps turn spoken answers into structured evidence. If an answer is vague or uncertain, it is passed to a person instead of being guessed.” |
| 3:35–4:15 | Human review and export | Only confirmed fields can be approved; then CSV/JSON package | “The adviser still makes the call. Only exact, confirmed evidence can move into a hand-off package.” |
| 4:15–4:40 | Architecture map | The complete path and trust boundary | “The map makes the division of responsibility clear: the system coordinates the work; the human makes the decision.” |
| 4:40–5:00 | Closing screen | Specific impact and originality | “AcreVoice turns a consented conversation into clear, reviewable evidence—so advisers can spend less time chasing details and more time using their judgment.” |

## Memorable safety proof

Before the final connected take, use **Prepare uncertainty route** once in the
local rehearsal path. Select the approximate/hedged scenario and start the
practice call. The Evidence Passport should show the exact spoken wording,
`unknown` as the recorded value, **Not confirmed — cannot be applied**, and the
callout **AcreVoice does not guess: this answer is held for human review.**
Label this rehearsal clearly as synthetic; it is a product-safety demonstration,
not evidence of a real phone provider call.

## Required proof before recording

1. Run the full test suite from the project virtual environment.
2. Run `scripts/check_credentials.py`; it must confirm the CALL-E and Bedrock configuration without consuming a call.
3. Start the service with the connected runtime and confirm that the interface says **live calls ready**.
4. Use a test participant who has explicitly agreed to the callback and recording.
5. Save the completed case and export package. Check that the case records the provider call ID and that only confirmed fields are selectable.
6. Record one complete take. The video must be under five minutes and show the whole path without edits that hide the provider result.

## Architecture asset

Use [the interactive architecture map](architecture/acrevoice-current-architecture.html)
for the 4:15 segment. It is evidence-linked to the repository revision and
shows the intended product flow and human-accountability boundary. It is an
explanation of the system, not proof that external services have run.
