# BERDO Gap — start here (Priyanka, solo, 4:00–8:00 PM)

**Track:** Energy & climate tech (portal challenge C2, "Cleaner, more affordable buildings")
**One line:** For any large Boston building, BERDO Gap shows what it will owe each year under Boston's emissions law, and which retrofit brings that to zero — written up as a one-page memo for the owner's board.

**Pitch number (from the City's own 2026 disclosure; estimate, per building):** of 1,809 buildings with reported 2025 emissions, 63 already exceed their limit (~$2.9M/yr). At today's emissions, **963 exceed the 2030 limits (~$27.4M/yr), and 900 of them owe nothing today** (either under the limit or not covered until 2030). Caveats to say out loud: buildings that comply as a portfolio or campus may net out; the grid getting cleaner lowers future emissions.

---

## Before you leave (5 minutes)

- [ ] **Pick up your paper Kiro code** at the front desk if you haven't. You can't get it later off-site.
- [ ] You can hack from anywhere after check-in (event FAQ). Submission deadline is 8:00 PM sharp.

## Rules that can disqualify you

1. Build with **Kiro**. All app code comes from Kiro (spec tasks or chat). Do not paste code from elsewhere.
2. `/.kiro` must be in the repo root and committed. Never gitignore it.
3. Public GitHub repo with run steps, video under 3:00 on public YouTube, text description, Kiro write-up, track = Energy & climate.
4. In the write-up, say plainly that planning notes, the limits table check and test values were prepared with Claude's help. That is honest and costs nothing; the code is Kiro's.

## What's in this kit

| File | What it is | When you use it |
| --- | --- | --- |
| `KIRO_SPEC_BRIEF.md` | Paste into Kiro Spec mode; Kiro generates requirements, design and tasks | 4:05 |
| `.kiro/steering/*.md` | Steering drafts: product, tech, structure, data rules. Skim and edit in your words | 4:00 |
| `HOOKS.md` | 3 hooks to create in Kiro's Hooks panel | 4:20 |
| `data/berdo_limits.csv` | Official emissions limits, 13 uses × 6 periods, from boston.gov | Kiro loads it |
| `data/property_type_map.csv` | Portfolio Manager type → BERDO use (66 types, 57 derived from City data) | Kiro loads it |
| `data/golden_buildings.csv` + `GOLDEN_TESTS.md` | 4 real buildings with hand-checked expected outputs | Unit tests |
| `data/expected_by_use.csv`, `data/expected_sample_40.csv` | Independent expected totals for all 1,809 buildings + 40 sampled buildings | Regression tests: proves Kiro's calculator is right |
| `DATA_NOTES.md` | Where the data is, exact column names, and the traps | Read once at 4:00 |
| `CLAUDE_MEMO_PROMPT.md` | The prompt for the board-memo feature | 6:00 |
| `SUBMISSION_AND_VIDEO.md` | Video script, description text, Kiro write-up outline | 6:20 |
| `KIRO_USAGE.md` | Running log that becomes the Kiro write-up | All day |
| `RUNBOOK.md` | **Step-by-step instructions from 3:00 PM to submission** | Start here |

## The 4:00–8:00 plan

| Clock | Do | Done when |
| --- | --- | --- |
| 4:00–4:10 | New **public** GitHub repo `berdo-gap`; open in Kiro; unzip this kit into the repo root; commit "kickoff: steering, data, brief". Put your Anthropic key in `.streamlit/secrets.toml` (gitignored). | Repo pushed with `.kiro/` |
| 4:10–4:25 | Kiro **Spec** mode → paste `KIRO_SPEC_BRIEF.md`. Review `requirements.md`, edit one thing, approve design and tasks. Screenshot each. | `.kiro/specs/berdo-gap/` has 3 files |
| 4:25–4:30 | Create the 3 hooks from `HOOKS.md`. Screenshot. | Hooks listed |
| 4:30–5:25 | Execute tasks in order: data loader → limits + mapping → calculator → property-based tests → golden tests → retrofit scenarios | `pytest` green |
| 5:25–5:55 | Tasks: Streamlit UI (search, limits chart, sliders, ZIP ranking) | Runs locally |
| 5:55–6:15 | Task: Claude memo (use `CLAUDE_MEMO_PROMPT.md`) | Memo renders |
| 6:15–6:30 | Deploy to Streamlit Community Cloud from GitHub; add the key as a secret; set a spend limit on your Anthropic key | Public link works |
| 6:30–7:00 | Record video (script in `SUBMISSION_AND_VIDEO.md`); upload public to YouTube | Link works logged out |
| 7:00–7:25 | Finish `KIRO_USAGE.md` → paste as Kiro write-up; README run steps; submit on SundAI | Submitted |
| 7:25–8:00 | Buffer. No new features. Don't push after submitting. |  |

## If you fall behind, cut in this order

1. ZIP ranking view (keep the single-building page)
2. Blended-standard toggle
3. "Green power purchase" scenario (keep heat pumps + efficiency)
4. Live Claude memo (fall back to a templated memo; keep Claude in the video only if it works)

Never cut: the calculator, the property tests, the golden tests, the video.

## Stack (decided so you don't have to)

Python 3.11, pandas + openpyxl, Streamlit, plotly, anthropic, pytest + hypothesis. One repo, no separate frontend. Deploy on Streamlit Community Cloud (free, deploys from GitHub in ~3 minutes). Fallback: run locally and record the video; judges may judge from the video.
