# BERDO Gap — step-by-step runbook (start 3:00 PM, submit by 7:30 PM)

Follow in order. Each phase ends with a **checkpoint**; if you miss its clock time, apply the cut listed there and move on. Keep `KIRO_USAGE.md` open and add a line + screenshot whenever Kiro does something useful (save screenshots in `docs/screens/`).

Hard deadline 8:00 PM. Target submit 7:30.

---

## Phase 0 — Setup (3:00–3:15)

1. Plug in your laptop. Download **berdo-gap-kit.zip** from the chat.
2. GitHub → New repository → name `berdo-gap` → **Public** → no README → Create. Copy the URL.
3. Open **Kiro** and sign in. If you haven't redeemed the paper code, do it now (account / plan settings).
4. In **PowerShell** (move the zip to your Desktop first):
   ```powershell
   cd $HOME\Desktop
   git clone <your repo URL> berdo-gap
   Expand-Archive .\berdo-gap-kit.zip -DestinationPath . -Force
   robocopy .\berdo-kit .\berdo-gap /E      # copies .kiro and .gitignore too
   cd berdo-gap; Get-ChildItem -Force        # you must see .kiro and .gitignore
   ```
   (Robocopy prints a summary table; that's normal.)
5. Python environment:
   ```powershell
   py -3.11 -m venv .venv
   Set-ExecutionPolicy -Scope Process Bypass   # only if activation is blocked
   .\.venv\Scripts\Activate.ps1
   pip install pandas openpyxl pyarrow streamlit plotly anthropic pytest hypothesis
   ```
   If `py -3.11` isn't found, use `python -m venv .venv` (any Python 3.10+ is fine).
6. API key (never commit it): in Kiro, create the file `.streamlit\secrets.toml` with these two lines:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   CLAUDE_MODEL = "claude-sonnet-5-5"
   ```
   In the Anthropic Console, set a monthly spend limit on the key (the live link is public).
7. First commit:
   ```powershell
   git add -A; git commit -m "Kickoff: steering docs, verified data, spec brief"; git push
   ```
   Open the repo on GitHub and confirm `.kiro/steering/` is there and `.streamlit/secrets.toml` is **not**.
8. Open the `berdo-gap` folder in Kiro (File → Open Folder).

**Checkpoint 3:15:** repo on GitHub with `.kiro/`, Kiro open on the folder.

---

## Phase 1 — Spec, steering, hooks, MCP (3:15–3:40)

9. In Kiro's panel, find **Steering**: you should see product, tech, structure and data-rules. Skim each; reword one sentence per file in your own words. Screenshot.
10. Start a new **Spec** (Kiro chat → choose Spec, not Vibe). Paste everything below the line in `KIRO_SPEC_BRIEF.md`.
11. Review the generated **requirements.md**:
    - All 9 properties (P1–P9) appear as acceptance criteria.
    - The golden test and regression test requirements are there.
    - Add one requirement yourself: "WHEN a building is shown THE SYSTEM SHALL display the City's own Emissions Compliance Status next to the estimate."
    - Approve. Screenshot before/after.
12. Review **design.md**: modules should match `structure.md` (load, limits, exposure, scenarios, memo, app). Approve. Screenshot.
13. Review **tasks.md**: order should be load → limits → exposure → scenarios → tests → app → memo. Approve. Screenshot.
14. Create the 3 hooks from `HOOKS.md` (Agent Hooks panel → new hook → describe it). Screenshot the list.
15. MCP: add the `fetch` server (MCP panel; command `uvx`, args `mcp-server-fetch`; run `pip install uv` first if needed). In Kiro chat ask: *"Use the fetch tool to read https://www.boston.gov/departments/environment/building-emissions-reduction-and-disclosure and check it against data/berdo_limits.csv."* Screenshot the answer.
16. Commit: `git add -A; git commit -m "Spec, hooks, MCP"; git push`.

**Checkpoint 3:40:** spec approved, hooks listed. If MCP fails to start, skip it and move on.

---

## Phase 2 — Calculator and tests (3:40–4:55)

Run tasks one at a time from `tasks.md` (click the task's run/start action). After each, run `pytest -q` (the hook should do it on save).

17. **Load task.** Then check:
    ```bash
    python -c "from berdo.load import load_buildings as f; df=f(); print(len(df))"
    ```
    Expect **1809** (use whatever function name Kiro created). If the download is slow, open the Excel URL from `DATA_NOTES.md` in a browser, save it in `data/cache/`, and tell Kiro to load from there.
18. **Limits task** (limits table, type mapping, blended limit). Tests green.
19. **Exposure task** + property tests P1–P4, P9. If Hypothesis prints a counterexample: **copy it into `KIRO_USAGE.md` before fixing.** That is the strongest line in your write-up.
20. **Golden + regression tests.** Must pass:
    - 4 golden buildings (e.g. 1047 Commonwealth Ave: $3,666.73 now, $43,764.97 in 2030).
    - Totals: 1,809 buildings, 63 over in 2025–2029 ($2,880,426.65), 963 over in 2030–2034 ($27,406,457.43).
    - If totals differ, read "usual causes" in `GOLDEN_TESTS.md`, then tell Kiro which test fails and the cause.
21. **Scenarios task** + property tests P5–P7. Check the heat-pump table in `GOLDEN_TESTS.md` (1047 Commonwealth at 100% → $0 in 2030).
22. Commit after each green step.

**Checkpoint 4:55:** `pytest -q` all green. **If late:** cut the blended limit and green-power scenario (tell Kiro to mark those tasks out of scope).

---

## Phase 3 — App and memo (4:55–6:00)

23. **App task** (Streamlit). Run `streamlit run app.py` and check:
    - Search "1047 Commonwealth": shows ~$3,667/yr now, ~$43,765/yr from 2030, and the City status "Action Needed".
    - Heat-pump slider to 100% → 2030 drops to $0.
    - Assumptions (0.85, 2.5) visible and editable; "Estimate, not a compliance determination" visible; sources page.
    - City view: bar chart by ZIP; 02128 at the top.
24. **Memo task**: tell Kiro to implement it from `CLAUDE_MEMO_PROMPT.md`. Click "Draft board memo" and read it: every number must match the screen. Then temporarily break the key to confirm the fallback memo appears.
25. Save `app.py` once so hook 3 checks for hard-coded numbers. Fix anything it flags.
26. Commit and push.

**Checkpoint 6:00.** **If late:** cut the City view; keep the single-building page and memo.

---

## Phase 4 — Deploy (6:00–6:20)

27. Ask Kiro: "Create requirements.txt for Streamlit Community Cloud." Commit and push.
28. Go to share.streamlit.io → sign in with GitHub → **Create app** → repo `berdo-gap`, branch `main`, file `app.py` → **Advanced settings**: Python 3.11, paste the two lines of `secrets.toml` into Secrets → **Deploy**.
29. Open the link in a private window; search 1047 Commonwealth; draft a memo.
30. **If deploy fails by 6:20:** stop trying. Record the video locally and put "Run locally" steps in the README.

---

## Phase 5 — Video (6:20–7:00)

31. Open `SUBMISSION_AND_VIDEO.md`; rehearse once out loud (target 2:40).
32. Record your screen with your voice: Windows 11 **Snipping Tool** → Record (or `Win+Shift+R`), or OBS / a Zoom recording. Xbox Game Bar records only one window, so avoid it when switching between the app and Kiro. Show Kiro's spec, a hook firing, the Hypothesis counterexample and the steering files in the 1:40–2:20 part.
33. Trim if over 3:00. Upload to YouTube → visibility **Public** → copy the link → open it in a private window to confirm.

---

## Phase 6 — Write-up and submit (7:00–7:30)

34. Ask Kiro: "Write README.md with what the app does, run steps, data sources and licenses, assumptions, and how tests verify the numbers." Read it and fix anything wrong.
35. Finish `KIRO_USAGE.md` (every heading filled; keep the line disclosing Claude-prepared planning notes).
36. Final push: `git add -A; git commit -m "Submission"; git push`. On GitHub confirm `.kiro/` is at the root.
37. Submit on the SundAI event portal (sundai.club → Hackachusetts → create project card):
    - Track: **Energy & climate tech**
    - Text description: from `SUBMISSION_AND_VIDEO.md`
    - Video: YouTube link
    - GitHub: repo link
    - Live demo: Streamlit link (or "see README to run locally")
    - Kiro write-up: contents of `KIRO_USAGE.md`
    - Team: just you
38. Re-open the submitted card and check every link. **Then stop.** Don't push after submitting.

**7:30–8:00:** buffer. If something is broken, fix only the submission card, not the code.

---

## If you get stuck

- Message this chat with the error text or a screenshot. I can review outputs, check numbers, and explain errors; Kiro writes the code.
- Tests failing and you can't see why within 10 minutes → skip that feature, keep the tests that pass, and move on.
