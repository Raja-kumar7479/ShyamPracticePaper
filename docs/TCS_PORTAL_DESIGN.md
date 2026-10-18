# TCS Portal - System Design

A TCS NQT style placement exam: several aptitude sections (Quantitative,
Reasoning, Verbal, ...) sat in the competitive mock-test window, followed by a
coding section sat in the placement coding editor (problem on the left, editor
on the right), ending in one combined result.

## Principle: no new test engine

The platform already has two proven engines:

| Part | Engine | Storage | Student UI |
| --- | --- | --- | --- |
| Aptitude | Competitive mock test | `test_description` + `test_questions` (one `section_name` per aptitude section) | Competitive test window: section tabs, question palette, timer, proctoring |
| Coding | Coding portal | `cp_tests` + `cp_sections` + `cp_questions` + `cp_testcases` | Split-pane coding page with editor, run/submit, judge |

A TCS exam is an **orchestrator** over those two, not a third engine. It owns
only the link between them and the student's progress through the two parts.

```
tcs_exams        one row per exam:  section_id (course block) + aptitude_test_key + coding_test_id
tcs_attempts     one row per student per exam:  stage = aptitude -> coding -> completed
```

## How the admin stores questions (unchanged tools)

1. **Course Content**: create a content block whose section is **TCS NQT Exam**
   (`tcs_test`). Its Free/Paid label and price control student access, exactly
   like every other block.
2. **Mock Tests**: write the aptitude paper as a normal mock test. Each
   aptitude section is just a `section_name` on the questions (Quantitative
   Aptitude, Logical Reasoning, Verbal Ability, ...). The competitive window
   renders them as section tabs automatically.
3. **Mock Tests (coding block)**: write the coding paper with the coding
   question editor - statement, starter templates per language, sample and
   hidden test cases, marks.
4. **TCS Exams** (new admin page): pick the content block, the aptitude test,
   the coding test, then publish. That is the whole admin surface for TCS.

Nothing about question authoring changed; the two editors that already exist
are the two ways to store questions.

## Student flow

```
Course dashboard  --Open Resource-->  /tcs/<course>/<code>/<section_id>   (list of published TCS exams)
        |
   Start Exam  -->  /tcs/exam/<id>/start   creates tcs_attempts row (stage=aptitude)
        |           registers a mock attempt (store_user_test_start) and the two
        |           session flags the competitive window requires, then shows a
        |           launch page whose button opens the proctored exam window.
        v
   [exam window]  competitive instruction -> paper instruction -> readiness -> test window
        |
   Submit  -->  competitive submit endpoint sees session['tcs_flow'] for this test_key
        |       and returns redirect_url = /tcs/exam/<id>/after-aptitude   (instead of feedback)
        v
   after-aptitude  records the mock attempt number, stage=coding, shows "Start Coding Part"
        |
   /tcs/exam/<id>/coding  -->  redirect(coding_test.start, slug)   (coding portal creates its attempt)
        |
   Finish / timer-up  -->  coding portal's finish paths call _after_finish_url(), which sees
        |                  session['tcs_flow'] for this coding test and sends the student to
        |                  /tcs/exam/<id>/after-coding   (instead of the coding dashboard)
        v
   after-coding  stage=completed, clears the flow flag  -->  /tcs/exam/<id>/result
```

The whole exam stays inside the one dedicated window the competitive engine
opened, so its window guard, full-screen guard, and away-termination keep
protecting both parts.

## Integration points (all small, all guarded by the session flag)

- `competitive_exam_platform/test_window/start_submit_test.py` - after a
  successful save, if `session['tcs_flow']['aptitude_test_key'] == test_key`,
  the JSON `redirect_url` points at `tcs.after_aptitude`.
- `coding_portal/routes/test.py` - `_after_finish_url(attempt)` replaces the
  four hard-coded "back to dashboard" targets (finish, timer expiry, done
  attempt, finish summary). Without the flag it returns the old dashboard URL,
  so plain coding tests behave exactly as before.
- `routes/taxonomy.py` - portal `tcs` routes to `tcs.dashboard`, counts as a
  test section, and opens in a new window like the other proctored exams.
- `admin/manage_catalog/catalog_db.py` - `tcs` added to the live portals so the
  catalog editor offers it.

## Result

`/tcs/exam/<id>/result` combines:

- Aptitude: `ResultHandler.get_test_summary_details(test_key, email)` -
  net score, total marks, accuracy, and a per-section table computed from the
  attempt details grouped by `section_name`.
- Coding: `result_stats.question_rows` + `summary` for the coding attempt -
  per-question verdict, cases passed, score out of marks.
- Total = aptitude net score + coding score, over the summed maximum.

Links to the detailed aptitude analysis page and the coding report page are
kept, so nothing the two engines already show is lost.

## Access and safety

- Login required on every TCS page; course access checked with the same
  `secure_access_required` the competitive portal uses.
- Paid blocks: purchase of the block or an active platform subscription.
- The active-test lock prevents starting Part 1 while another proctored test
  is live.
- One attempt per student per exam (`UNIQUE (tcs_exam_id, email)`); an admin
  can delete an exam's attempts by deleting and recreating the exam
  (owner-only when attempts exist).

## Deploy

1. Apply `user_app/migrations/030_tcs_portal.sql` (creates the two tables and
   the `tcs_test` catalog section under PLACEMENT).
2. Restart both apps.
3. Admin: Course Content -> new block with section "TCS NQT Exam"; Mock Tests ->
   aptitude paper and coding paper; TCS Exams -> link and publish.

## Languages and calculator (admin controlled)

- **Languages**: the coding editor's language dropdown shows only what the
  admin allows. Two levels, both set in Mock Tests -> coding block:
  - per test: "Languages allowed in this test" (new, `cp_tests.allowed_languages`,
    migration 031) - tick Java, Python, C++ for a TCS exam;
  - per question: the existing "Allowed languages" chips, now limited to the
    test's set. The student editor lists the intersection and the run/submit
    API rejects anything else.
- **Calculator**: the mock-test description's "Visible in the test window"
  switch (`test_description.show_calculator`) decides whether the calculator
  icon appears in the aptitude window. Off by default in the sample exam, as
  in the real NQT.

## Sample exam (migration 032)

`user_app/database/seed_sample_data.sql` (loaded with `python db_bootstrap.py --seed` inside `user_app/`, never automatically) seeds a complete, published exam under course PLA:
content block `TCS_NQT_MOCK_1` (section TCS NQT Exam, Free), aptitude test
`TCS_NQT_MOCK_1_APT` with 15 MCQs across Numerical Ability, Verbal Ability and
Reasoning Ability (45 min, no calculator), coding test `tcs-nqt-mock-1-coding`
with two problems (Second Largest Element, Balanced Brackets; Java/Python/C++
templates, sample + hidden test cases, 30 min), and the `tcs_exams` link. It is
idempotent - safe to re-run - and everything in it is editable afterwards from
the admin Mock Tests page, which uses the competitive editor for the TCS block.
