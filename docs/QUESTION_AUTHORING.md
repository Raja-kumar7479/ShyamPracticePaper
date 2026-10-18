# Question Authoring — Developer Guide

How questions are stored, authored, and rendered across the two exam platforms.
Read this before touching anything under `admin_app/admin/manage_mock_test/` or
`user_app/routes/exam_platform/`.

## The one rule that everything routes on

There are two parallel table families with identical mirror columns:

| Purpose | Competitive (mock test) | Communication (placement) |
|---|---|---|
| Test paper metadata | `test_description` | `comm_description` |
| Questions | `test_questions` | `comm_questions` |
| Sections | (per-question `section_id/name` only) | `comm_sections` (title, instruction, duration, order) |
| Attempt answers | `test_attempt_details` | `comm_attempt_details` |
| Session log | `user_test_log` | `comm_user_log` |
| Results | `test_result` | `comm_result` |
| Feedback | `test_feedback` | `comm_feedback` |
| Round category | — | `assessment_rounds` (`round_type` ENUM COMM/CODING/APTITUDE/APTITUDE_CODING) |

**Routing rule:** `comm_description` and `comm_questions` AUTO_INCREMENT start at
**1,000,000** (`COMM_ID_OFFSET` in `admin_app/admin/manage_mock_test/test_details_db.py`).
Any id-based admin API decides the table family by `id >= COMM_ID_OFFSET`.
Test-id–based calls decide by the course's group: `courses.name == 'PLACEMENT'` → comm.
Never insert into a comm table without respecting the offset.

## Question types

- **Competitive** (`test_questions.question_type`): `MCQ`, `MSQ`, `NAT` — plus
  *image questions*: `question_text` empty, `question_image` = uploaded file URL,
  `option_regions` = JSON `{a:{x,y,w,h}, ...}` in percent of the image.
- **Communication** (`comm_questions.question_type` ENUM): `MCQ`, `SPEAK`,
  `THINK_SPEAK`, `WRITING`, `COMPREHENSION` (+ `LISTEN_SPEAK`, `FILL_BLANK`).
  The student test window (`user_app/templates/.../communication_portal/test_window.html`)
  branches its UI on these exact values. COMPREHENSION audio: `media_url` on the
  **first** question of the section only.

## Authoring flows (admin)

All on `/manage-tests` (`test_details_insert.html` + `test_details_insert.js`):

1. **Manual (mock)** — Add New Question modal, Quill editors → `POST /api/test-questions/add`.
2. **Sheet (mock)** — CSV/XLSX template → `POST /api/test-questions/upload-csv` (all-or-nothing bulk insert).
3. **Image question (mock)** — `image_question.js`: client-side canvas editor
   (crop / hide / rotate / auto-trim burn edits INTO the uploaded PNG — server never
   knows), region marking, queue for multiple files, edit-in-place
   (`PUT /api/test-questions/update-image/<id>`). Upload endpoint:
   `POST /api/question-image/upload` → saves under `admin_app/uploads/images/` and writes the file to the database for the student app,
   served by both apps at `/static/uploads/...`.
4. **Bulk image page** — `/manage-tests/image-batch` (`image_batch.html/js`):
   Excel row-per-question + all images at once, matched by filename, marked
   one-by-one, then saved through the same two endpoints as (3). Sheet parsing is
   client-side (SheetJS CDN); there is no batch backend.
5. **Communication** — loading a placement description swaps the panel to
   `comm_question.js` (`commManagementContainer`): sections CRUD
   (`/api/comm-sections/...`), typed manual add (`/api/comm-questions/add/<desc_id>`),
   comm sheet upload (`/api/comm-questions/upload-csv/<desc_id>`), all in
   `comm_question_insert.py`. Image questions are intentionally not available here.
6. **Coding (placement Coding round)** — a description whose content section is
   `coding_test` swaps the panel to `coding_question.js`, backed by
   `/api/coding-panel/...` in `coding_question_panel.py` and the `cp_*` writes in
   `manage_coding/coding_db.py`: sections, questions, per-language templates,
   test cases, web assertions and the SQL sandbox DDL. The `cp_tests` row behind
   a description is created on demand — admins never manage it directly.

   The user app has **no** coding authoring. It shipped a full second authoring
   UI (`coding_portal/routes/admin.py` + `templates/.../coding_portal/admin/`)
   inherited from the standalone CodeJudge compiler, which was dead — every route
   was blocked — and it has been removed. The coding portal only reads `cp_*`.

   Editing a SQL question's `sandbox_schema_sql` here is picked up automatically:
   the student's sandbox database is fingerprinted in `cp_sql_sandboxes` and
   rebuilt on the next run when the DDL no longer matches.

## Rendering (user app)

- Competitive window: `static/js/.../competitive_exam_platform/test_window.js`
  (`_renderQuestion`) — image questions render the image with a **left gutter of
  clickable circles** driven by hidden radio/checkbox inputs, so save/clear/submit
  logic is identical to text questions. Data comes from `/fetch-questions/...`
  which parses `option_regions`.
- Communication window: sections come from `comm_sections`
  (`proctor_db.get_assessment_sections`, falls back to deriving from questions),
  total duration = sum of section durations.

## Tooling

- `python scripts/smoke_check.py` — verifies every table/column the code needs
  exists in the live DB and that both blueprints import. Run after pulling.
- `python user_app/migrations/run.py` — applies pending `NNN_*.sql` migrations,
  tracked in `schema_migrations` (`--list`, `--dry-run`, `--baseline`).
- `python db_bootstrap.py --seed` (run inside `user_app/`) — loads the demo TCS NQT exam. The catalog
  (groups, codes, sections) is created by the migrations at startup; only this
  demo exam is opt-in.
- `python admin_app/admin/manage_mock_test/seed_comm_sample.py` — (re)creates the
  SET_A demo communication test: 5 sections, 20 questions, every type.
- `python admin_app/admin/manage_practice_coding/seed_practice_content.py` —
  loads the starter practice bank (6 coding problems, 10 quiz questions,
  6 companies). Idempotent; the user app no longer seeds this on boot.

## Conventions

- Migrations are idempotent (information_schema guards) — always safe to re-run.
- New columns needed by code ⇒ add a migration **and** a line in
  `scripts/smoke_check.py` REQUIRED map **and** `user_app/database/schema.sql`.
- Admin JS globals (`activeTestDescriptionId` etc.) live inside
  `$(document).ready` in `test_details_insert.js` — handlers referencing them
  must be defined inside that closure.
