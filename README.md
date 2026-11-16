# Expand ELEVATE — v3 (merged app)

ONE Streamlit app, ONE deployment, serving both state analysts and
national admins. See `docs/ARCHITECTURE.md` for the full design and the
explicit security trade-off this accepts (no per-state database
isolation — see section 0 and section 9).

## Setup (one-time, by whoever deploys this)

1. Create a **fresh** Supabase project (do not reuse v1's or v2's — the
   privilege model changed). Run `supabase/schema.sql` in the SQL editor.
2. Deploy this repo on Streamlit Community Cloud, pointing at `app.py`.
3. In **Settings → Secrets**, paste (see `.streamlit/secrets.toml.example`):
   ```
   SUPABASE_URL = "..."
   SUPABASE_ANON_KEY = "..."
   SUPABASE_SERVICE_ROLE_KEY = "..."
   ```
4. Create the first **National admin** account directly in Supabase
   (Auth → Users → Add user), then insert a matching row in
   `admin_profiles` with `role='national'`.
5. Log in as that national admin, go to **Manage State Login**, and
   create the ONE shared State login — this is the single email+password
   every state analyst anywhere will use.
6. Distribute that one email+password to every state's analyst, over a
   secure channel (not plain chat/email where avoidable).

## Local development

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # fill in real values
streamlit run app.py
```

## Pages

National-only (gated by `require_role(["national"])`):
- **Dashboard** — paired pre/post counts and paired t-tests, filterable
  by state, training, and staff Level.
- **Questionnaire Manager** — upload/manage multiple questionnaires.
- **Admin — Delete Data** — full-platform backup + destructive wipe.
- **Manage States** — add new participating states.
- **Manage National Logins** — individually-named national admin accounts.
- **Manage State Login** — the ONE shared state credential: create it
  once, reset/rotate its password, or revoke it for everyone.

State-role (shared login, gated by `require_role(["state"])` +
`require_state_picked()`):
- **Pick your state** (forced automatically) — locks for the session.
- **Manage Trainings** — create/open/close trainings for the picked state.
- **Questionnaires** — view available questionnaires, upload a
  translation for the picked state.
- **Export** — download the picked state's own data as CSV.

Public, no login, two SEPARATE pages/links on purpose:
- **Take Pretest** — staff pick their state, then an open training,
  then their level, then take the test. ID is auto-generated on submit.
- **Take Posttest** — staff enter their ID only; the app resolves their
  pending post-test automatically.

## Security notes — read this before deploying

- `SUPABASE_SERVICE_ROLE_KEY` bypasses Row-Level Security entirely. It
  lives in this one app's secrets and is used ONLY inside pages that
  call `require_role(["national"])` at the very top, before anything
  else. Audit every new page you add against this rule.
- There is **no database-level isolation between states** in v3 — see
  `docs/ARCHITECTURE.md` section 9. The only boundary is the app's own
  `require_state_picked()` session lock. This was a deliberate,
  explicit choice, not an oversight.
- The shared State password is known by every analyst in every state.
  Rotate it (**Manage State Login → reset**) whenever anyone who knew
  it no longer should have access — treat it like a shared building key.
