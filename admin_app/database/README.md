# Admin App - Database

The admin app is deployed on its own. It shares one thing with the student app: the MySQL database.

This folder and `migrations/` hold everything needed to build that database from nothing:

| File | What it creates |
|---|---|
| `student_schema.sql` | core tables (auth, courses, course_content, test_description, purchase, ...) |
| `coding_schema.sql` | coding tables (`cp_*`) |
| `schema.sql` | admin tables (`auth_admin`, admin login attempts, ...) |
| `../migrations/student/*.sql` | changes to the core and coding tables |
| `../migrations/*.sql` | changes made for the admin panel |

`db_bootstrap.py` loads them in that order every time the app starts and records what it has applied in the `schema_migrations` table, so a second start (or the student app starting later) changes nothing.

The student app carries the same files. When a table or migration is added, add it to both apps.

To run it by hand:

```bash
cd admin_app
python db_bootstrap.py          # bring the database up to date
python db_bootstrap.py --list   # show what is applied and what is pending
```
