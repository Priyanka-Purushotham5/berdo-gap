# How I used Kiro to build BERDO Gap

I built BERDO Gap solo in one afternoon. My strategy was simple: let **spec-driven development** own everything where correctness matters (the emissions and payment calculator), use **vibe coding** for fast UI iteration, and let **steering, property-based tests and real-data regression tests** keep Kiro honest about the numbers.

## Kiro tools I used

I used the **Kiro IDE** for the whole project: Spec mode for the calculator, Vibe mode for UI polish and debugging, and the Kiro panel for steering. Working solo with only a few hours, I focused on going deep with the IDE rather than trying the CLI, Web or Crew.

## Spec-driven development

I started Kiro in **Spec mode** and chose the **requirements-first** path. I gave it a brief describing the users (condo boards and property managers in Boston), the data (the City's 2026 BERDO disclosure and the official limits table), the exact formulas, and nine correctness properties. Kiro turned that into EARS-style requirements ("WHEN … THE SYSTEM SHALL …"), then a design and a task plan.

I treated each stage as a review gate, and that's where the spec approach paid off:

- **I cut scope on purpose before any code existed.** I removed the blended-standard toggle, the green-power scenario and its property (P8), and added a requirement to show the City's own official compliance status next to my estimate, so users can compare the two.
- **I caught two design bugs on paper.** In design.md, the memo validator would have rejected any Claude memo that mentioned a year or the $234 rate, so the AI memo would silently never appear. I also noticed some buildings only have a parcel address, so I added a fallback. Both were one-line fixes in the design instead of debugging sessions later.
- **I overruled Kiro on testing.** The task plan marked my property-based tests as optional. I made them required and marked the less important unit tests optional instead, because the property tests were my main guarantee that the money math is right.

Then I ran the required tasks. Kiro built the whole calculator package (load, limits, exposure, scenarios, memo) and the first version of the app in about 25 minutes, with **27 tests passing**.

**Spec vs. vibe coding:** I used both, deliberately. The spec-driven calculator came out right on the first run, and every function traced back to a requirement and a test. The vibe-coded UI was much faster to iterate on, but bugs only showed up when I looked at the screen. ZIP codes rendered as "2134.0", a payment drop showed as a red up-arrow, and a table appeared twice. My takeaway: spec where being wrong is expensive, vibe where looking at it is the test.

## Steering docs

I wrote four workspace steering files before generating the spec:

- **product.md**: who the users are and what the app must never claim. It never says a building "is in violation" or "will be fined"; every number is an estimate.
- **tech.md**: the stack, strict separation of UI and calculation, and how to handle the Claude API key.
- **structure.md**: the folder layout.
- **data-rules.md**: scoped with `fileMatch` to `berdo/**/*.py`, so it loads only when Kiro touches calculation code.

**The rule that made the biggest difference** was in data-rules.md. The City's file has a column labeled "Site EUI" that actually contains emissions intensity in 1,788 of 1,809 rows. Because the steering told Kiro never to use it and to compute EUI itself, Kiro's design explicitly excluded that column and left a comment explaining why. Without that rule, a plausible-looking but wrong column would have gone straight into the app.

One practical lesson: my steering files didn't show up at first because the folder was open in **Restricted Mode**. Trusting the folder made Kiro load them.

## Property-based testing

I enabled Hypothesis property-based tests for the calculator's core requirements:

- P1: excess tons and payments are never negative
- P2: payment never decreases when emissions increase
- P3: payment never increases when the limit is looser
- P4: payment never decreases across later periods, because limits only tighten
- P5: a scenario with no changes returns the original emissions exactly
- P6: more efficiency never increases emissions
- P7: heat-pump conversion never produces negative emissions, and never increases emissions when electricity is carbon-free
- P9: at 2050, when the limit is zero, the payment equals all emissions in tons × $234

Alongside them I had **golden and regression tests on real data**: four real buildings with hand-checked results, plus citywide totals computed independently from the City's disclosure. Kiro's calculator reproduced them exactly:
- 1,809 buildings with reported emissions
- 63 buildings over the 2025–2029 limit ($2,880,426.65 a year)
- 963 over the 2030–2034 limit ($27,406,457.43 a year)
- every per-building-type total
- 40 sampled buildings, to within 5 cents

It also agreed with the City's own status for every covered test building, including "Action Needed" for 1047 Commonwealth Ave.

Hypothesis found no counterexamples on these runs. The value for me was confidence: the properties hold across thousands of generated buildings, not just the four I checked by hand. Kiro's own testing did catch a real bug elsewhere. When I reorganized the Building page into tabs, Kiro's AppTest run found that the same chart rendered in two tabs with identical element IDs, which Streamlit rejects, and fixed it with explicit keys before I ever saw the error.

## Debugging with Kiro

The Claude-drafted board memo kept falling back to the template. I confirmed my API key worked with a one-line test, then had Kiro surface the real exception instead of a generic error. The traceback showed the API rejected the request: forcing a specific tool (`tool_choice` type "tool") isn't supported for the model I was using. I had Kiro switch to automatic tool choice with an instruction to always call the memo tool, and to parse the result defensively.


## Timeline

| Time | What happened |
| --- | --- |
| 3:40 PM | Repo set up; steering docs and verified data files committed |
| 4:20 PM | Spec mode: requirements generated from my brief; scope cut (blended standard, green power, P8) |
| 4:57 PM | Design reviewed; caught the memo-validation and address bugs before coding |
| 5:06 PM | Tasks updated: property tests made required, low-value tests made optional |
| 5:10–5:36 PM | Ran required tasks; calculator, tests and first app built; 27 tests passing |
| 5:37 PM | Verified golden and regression tests against independently computed City totals |
| 5:45–6:25 PM | Vibe-mode UI polish: ZIP bug, delta sign, City chart, "The gap" chart, tabs; AppTest caught duplicate chart IDs |
| 6:15–6:35 PM | Debugged the Claude memo: traceback showed unsupported forced tool choice |
| 6:35 PM | Landing page and multi-page navigation |
