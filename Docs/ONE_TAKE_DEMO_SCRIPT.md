# AcreVoice — one-take demo script

**Target length:** about four minutes  
**Tone:** calm, warm and practical. Speak as if you are showing a useful tool to a colleague—not pitching an AI spectacle.

## Before you press Recordly’s record button

1. Open AcreVoice at `http://127.0.0.1:8080` and refresh the page.
2. In Recordly, capture only the AcreVoice browser window and turn on your microphone.
3. Put the test phone on speaker close enough for the call to be heard clearly.
4. Select **English** in the console. Close terminals, notifications, credentials, personal numbers, and unrelated tabs.
5. Confirm the test participant has agreed to both receive and record the call.

Keep these tabs ready, but do not leave them all on screen: AcreVoice, the public GitHub README, and the architecture map. The product is the story; the other two are short proof points.

## Read this and follow the actions in brackets

### 0:00–0:20 — Start with the real problem

**Say:**

> “When one small detail is missing, an adviser and a farmer can end up playing phone tag for days. AcreVoice keeps that follow-up simple: it asks a focused question with consent, keeps the answer clear, and leaves the decision with the adviser.”

**Do:** Show the AcreVoice home page. Hover over **How it works** and select **Open workspace**.

### 0:20–0:32 — Show that the work is inspectable

**Say:**

> “Everything you are seeing is in the public repository: the application, the setup notes, the tests, and the architecture behind this flow.”

**Do:** Show the GitHub README for about ten seconds. Return to AcreVoice—do not scroll through code.

### 0:32–0:52 — Set the boundary clearly

**Say:**

> “This is not here to decide whether someone is eligible or to submit an application. It starts with public guidance, works out what is missing, and gathers only that information with the farmer’s permission.”

**Do:** Choose **Eco-schemes**, select **Start support goal**, and let the source cards sit on screen briefly.

### 0:52–1:07 — Set up the call

**Say:**

> “For this test, I have a consented callback ready. The farmer can stop at any time. AcreVoice will ask two short questions, repeat each answer back, and only keep it when the farmer confirms it.”

**Do:** Set the call language to English. Check that live calling is enabled. Select **Start consented callback**.

### 1:07–2:17 — Let the call speak for itself

Do not narrate while the call runs. Let the consent, questions, read-backs and confirmations be audible.

| AcreVoice asks | Test participant says |
| --- | --- |
| “May I ask you two short questions?” | “Yes.” |
| “Which main crop types did you grow …?” | “Winter wheat, barley, maize, potatoes, and peas.” |
| “Is that correct? Please confirm with yes or no.” | “Yes.” |
| “What percentage of your arable land was legumes …?” | “Six percent.” |
| “Is that correct? Please confirm with yes or no.” | “Yes.” |

### 2:17–2:57 — Show what comes back

**Say:**

> “Now the adviser has something much better than a loose phone note. The Evidence Passport keeps the source, the question, the farmer’s own words, the confirmation, and the next step in one place.”

**Do:** Open the completed case and scroll to **Evidence Passport**. Pause long enough for both confirmed answers to be read.

### 2:57–3:22 — Explain the human role

**Say:**

> “AcreVoice does the follow-up work. It does not make the eligibility call, approve anything, or submit anything. A person reviews the evidence and decides what happens next.”

**Do:** Point to a confirmation row and the human-next-step row.

### 3:22–3:45 — Make the system easy to understand

**Say:**

> “This is the whole flow: public guidance, a consented callback, structured evidence, and a human hand-off. The automation helps with the coordination; the adviser stays responsible for the decision.”

**Do:** Show the architecture map for five to eight seconds, then return to the completed case.

### 3:45–4:05 — Finish with the safety behaviour

**Say:**

> “And when an answer is unsure, AcreVoice does not try to fill in the blanks. It holds that answer for the adviser to review.”

**Do:** Optionally show **Prepare uncertainty route**. Keep its label visible: this is a local safety rehearsal, not a live call. Finish with:

> “Less phone tag. Clearer evidence. Human decisions.”

## After the take

Trim only ringing, loading, or accidental pauses. Do not cut the consent, question, answer, or confirmation so tightly that the meaning changes. Add the opening title `AcreVoice — live consented test callback`; label the uncertainty route `Local safety rehearsal — not a live call`; then export an MP4 at 1080p and watch it through once with sound.

## Stop and fix setup first if

- the app says simulated instead of live;
- the participant has not agreed to the recorded test call;
- a secret, personal number, or unrelated customer data is visible; or
- the video would claim a connected cloud agent that has not been verified.
