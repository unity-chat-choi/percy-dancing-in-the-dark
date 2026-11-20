You are finishing a ticket for the uniscore-mobile React Native app on a CI runner. Work like a careful senior dev.

Inputs (outside the repo, read them first):
- ../ctx/context.md — the Jira ticket, parent story, sibling tickets ([API] etc.), all comments and the full Confluence specs. Read ALL of it, including Out of scope, open questions and the latest comments, before deciding anything.
- ../ctx/figma/*.png — the Figma frames linked in the ticket; open each one. ../ctx/figma/*.spec.txt — the same frames as exact numbers (size, auto-layout gap/padding, radius, fill/text colour, font family/weight/size/line height, texts). Build from these numbers, not from guessing the PNG.
- The current branch may already hold the developer's WIP: inspect `git log origin/app-develop..HEAD` and `git diff origin/app-develop...HEAD`. If it has none, implement the ticket from scratch.

Order of work (do not skip a step):
1. Read ALL of ../ctx/context.md: ticket, parent story, [API] sibling + its comments (the backend contract: route, params, response fields, enums), every Confluence page, QC subtasks. Write down the contract and every AC before coding.
2. Football precedent: find the same screen/tab in src/modules/football (and basketball if it is newer) and read it end to end. Clone its structure and behaviour (tabs, sub-tabs, filters, bottom sheets, persisted filter state, empty/loading, tracking, notification bell) into this sport's module — copy, never import another sport's module. UI pieces that already exist as shared components (UBoxView, TitleDate, UFilterBarButton, UBottomSheet, URenderItemModal, Empty, AppActivityIndicator, CustomTouchableOpacity) are reused, not copied.
3. Match Figma exactly: every size, padding, gap, radius, font and colour from the .spec.txt mapped to theme tokens / FONTS (docs/ai/design-tokens.md). Where Figma and football differ, Figma wins for the look, football for the behaviour.
4. API: when the contract is known and staging has it, call the real endpoint (you may GET https://opta-api.uniscore.vn with curl to check the real shape and edge data; nothing else). Not on staging → mock per the rule below.
5. QC test cases: go through every TC_ row of the "[QC] Test case & Testing" subtasks and every QC bug in comments; the code must satisfy each. Add jest tests for the logic (grouping, sorting, filters, default tab).

Rules:
- Follow the repo's AGENTS.md and CLAUDE.md (house components, theme tokens, i18n in all 33 translation files, no `any`, one export per file, English comments). Read docs/ai/pitfalls.md and grep docs/ai/bugs/ for the area you touch.
- If ../ctx/task.md has a "## Bug QC cần sửa" section, this is a fix round: fix exactly those bugs (scope ticket/blocking) first, minimal and safe, then re-verify. Bugs there come from QC on device with screenshots.
- Finish what the ticket and the WIP aim at. Do not start unrelated work. If the spec is unclear or the API is missing, do not guess: list it under "Cần confirm".
- Stay inside the app: never work around wrong or missing backend data in app code (no client-side renames/typo fixes of API values, no fake fields in prod). Note it as the backend's under "Cần confirm" and ask the backend.
- API not on staging yet (route 404, field missing) but its contract is known (TDD/Confluence/[API] ticket): do not stop. Build the feature on a mock as in docs/ai/mock-data.md, with the flag written EXACTLY like
  `const USE_MOCK = __DEV__; // MOCK(US-xxxx): replace with GET <endpoint> (US-yyyy) when the backend ships`
  (QC switches this line on, prod keeps calling the real API). The mock data follows the contract and covers every state the UI has (e.g. live / not live, several items, long names, empty). List the endpoint under "Cần confirm" and write an ask for the backend (asks.json). Contract unknown → do not invent one: list it and ask.
- Compare the UI code with every Figma frame: layout, spacing, sizes, colours (theme tokens), fonts, texts, empty/loading states. Fix real differences.
- Check the code also holds in dark mode (theme tokens, no hard-coded colours) and RTL (row direction, flipped arrows, text alignment).
- Read the QC test cases in "[QC] Test case & Testing" subtasks (TC_... tables) and any bugs QC reported in comments; make sure the code satisfies each one.
- Run `yarn verify` (base origin/app-develop) and the jest suites related to your files. Fix what your change broke. The repo has a pre-existing backlog; only new problems count.
- Commit with messages `US-XXXX fix: ...` / `US-XXXX feat: ...` in English. No Co-Authored-By. Never commit .md files. Do not push, call no external service except GET on the staging API above, never print secrets or tokens.

When done, write ../ctx/report.md in Vietnamese, short, for the developer reading on Telegram (no markdown tables):
## Đã làm
## So với Figma — each frame: khớp / lệch (what and why)
## Test — yarn verify result, jest suites run and results; QC test cases covered (TC_ID: ok / chưa) and old QC bugs (đã sửa / còn)
## Cần confirm — open questions for PO/BE, if any

For every open question, also write ../ctx/asks.json so Percy can send it with one tap (one entry per person, group the points):
[{"jira":"<Jira comment on this ticket in Percy's voice, Vietnamese, 2-4 sentences: starts with @alias of the PO (reporter of the parent story) for scope/requirement or the backend (assignee of the [API] ticket) for API; each question answerable yes/no, with the exact field/route/screen>","chat":"<1-2 sentence Google Chat reminder to the same person, ends with @alias>","why":"<1-2 sentences in Vietnamese telling Percy why this needs his OK before sending (who it pings, what it asks, why you could not decide it from the ticket/code/API)>"}]
Aliases and forms of address: ../ctx/people.md. No questions → do not write the file. Questions already answered in the Jira comments are not open.
## Test trên máy — screens/flows to check on iOS and Android
