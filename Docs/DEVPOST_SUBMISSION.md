# Devpost draft — Agents for Humans / Professional Agents

Use this text only after the live CALL-E and Bedrock/Strands demonstration has
been recorded. Replace the bracketed items with the public links before
submitting.

## Project name

AcreVoice — evidence-first support for agricultural advisers

## Tagline

Turn one consented callback into human-reviewable evidence, not another portal
for farmers to manage.

## Description

Agricultural advisers often lose time in a familiar loop: find the right
guidance, chase one missing fact, turn a phone conversation into something safe
to use, and prepare the case for a human decision. The farmer usually has the
answer; neither person should have to carry all that coordination burden alone.

AcreVoice is a Professional Agent for Bavarian agricultural-support teams. It
starts with dated public programme guidance, requests a callback only with the
farmer’s consent, collects only the missing facts, reads each answer back for
confirmation, and creates a structured evidence record for an adviser.

The Strands agent does bounded, tool-backed work: it normalises spoken values
and identifies hedged, approximate, or implausible answers. It does not decide
eligibility, subsidy amounts, or approval. Those cases, and every final export,
remain with a human adviser.

The flow demonstrated in the video is:

`official guidance → consented CALL-E callback → structured call outcome → Strands normalisation → append-only evidence → human review → CSV/JSON hand-off`

This is not a generic voice bot. AcreVoice works on one evidence-backed support
case at a time and stops at the right place: a human decision. Farmers get a
focused, bilingual interaction; advisers receive traceable evidence instead of
another unverified note.

## Built with

- Strands Agents SDK
- Amazon Bedrock `[verify model/runtime shown in video]`
- CALL-E
- FastAPI
- SQLite append-only audit store

## Links to supply before submitting

- Public repository: `https://github.com/dj-DeepakJadhav/acrevoice-farmer-support`
- Demo video: `[public URL, maximum five minutes]`
- Architecture diagram: `[upload/link Docs/architecture/acrevoice-current-architecture.html or exported image]`
- Live demo: `[public URL, only if genuinely deployed]`
- AWS Builder story: `[public URL, optional bonus]`
