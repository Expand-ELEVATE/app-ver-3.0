"""Supabase client + auth/role helpers shared by every v3 page.

v3 merges national_app and state_app into ONE application. There are
two login types:
  - 'national' — full cross-state access (same scope as v2's national app).
  - 'state' — ONE single shared account/password used by EVERY state's
    data analyst, across all 11+ states. This is a deliberate, explicit
    trade-off Dr Aswath chose knowingly: there is NO per-state database
    isolation and NO individual audit trail on the state side any more.
    The only boundary is the application itself: a state-role session
    must pick one state at the start of its session (locked until
    logout — see require_state_picked() below) and every state-scoped
    page then filters its own queries to that choice. A bug that skips
    a filter, or a user editing a URL/query param, is NOT stopped by
    the database here — see docs/ARCHITECTURE.md section 9.

Because ONE running process now holds BOTH the anon key (used for every
RLS-governed read/write once a user is logged in) and the service_role
key (needed ONLY for Admin API calls — create/revoke/reset logins, and
the full-platform backup+wipe), every privileged branch MUST call
require_role() with an explicit allow-list before doing anything else.
There is no longer a separate deployment to fall back on as a physical
boundary between state and national — see the module docstring above
and the "Security note" in docs/ARCHITECTURE.md.
"""
import streamlit as st
from supabase import create_client, Client

LEVELS = ["State", "District", "Sub-District"]  # staff's own self-reported level — unchanged by the National-training addition

# Training's own Level field (separate dimension from staff's self-report
# above) now has a 4th value, 'National', reserved for cross-state
# trainings the national team creates — see require_state_context() and
# the 'NAT' pseudo-state row in the `states` table.
TRAINING_LEVELS = ["National", "State", "District", "Sub-District"]

NATIONAL_PSEUDO_STATE_CODE = "NAT"


@st.cache_resource
def get_client() -> Client:
    """Anon key + the logged-in user's own session. ALL RLS-governed ops
    for both state-role and national-role pages should go through this
    client, not the admin client — access is granted by RLS policy
    (is_admin() / auth_role() = 'national'), not by holding service_role."""
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])


@st.cache_resource
def get_admin_client() -> Client:
    """service_role key — bypasses RLS entirely. ONLY call this from a
    page that has already called require_role(["national"]) at the top,
    and ONLY for: (a) Admin API user management (create/revoke/reset
    logins — there is no anon-key equivalent for this), and (b) the
    full-platform backup+wipe on Admin Delete Data."""
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_ROLE_KEY"])


def login_screen():
    st.title("Expand ELEVATE — Login")

    if "role" in st.session_state:
        return True

    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        sb = get_client()
        try:
            res = sb.auth.sign_in_with_password({"email": email, "password": password})
        except Exception as e:
            st.error(f"Login failed: {e}")
            return False

        profile = (
            sb.table("admin_profiles")
            .select("role")
            .eq("user_id", res.user.id)
            .maybe_single()
            .execute()
        )
        prof = profile.data if profile else None
        if not prof or prof["role"] not in ("national", "state"):
            st.error("This account does not have a recognised role.")
            sb.auth.sign_out()
            return False

        st.session_state["role"] = prof["role"]
        st.session_state["user_id"] = res.user.id
        st.session_state["email"] = email
        st.rerun()

    return False


def require_login():
    if not login_screen():
        st.stop()


def require_role(allowed: list[str]):
    """Call at the TOP of every page, before any data access. Stops
    execution with a clear error if the logged-in role is not in
    `allowed`. This is the ONLY boundary separating state-role sessions
    from national-only pages in v3 — see the module docstring."""
    require_login()
    if st.session_state["role"] not in allowed:
        st.error(
            f"This page requires role {allowed}. Your logged-in role is "
            f"'{st.session_state['role']}' — you do not have access."
        )
        st.stop()


def require_state_picked() -> str:
    """For state-role sessions ONLY. Forces an inline 'pick your state'
    step before any state-scoped content loads, then LOCKS that choice
    for the rest of the session — there is deliberately no 'switch
    state' button anywhere. The only way to work on a different state
    is to log out and log back in (per Dr Aswath's explicit decision).
    Excludes the 'NAT' pseudo-state (National-level trainings are the
    national team's responsibility, not a state analyst's) — see
    require_state_context() for the role-dispatching wrapper used by
    pages now shared between state and national roles."""
    require_role(["state"])
    if "picked_state" not in st.session_state:
        st.info("Select the state you are working on for this login session.")
        states_res = get_client().table("states").select("code, name").order("name").execute()
        options = {
            s["name"]: s["code"] for s in (states_res.data or []) if s["code"] != NATIONAL_PSEUDO_STATE_CODE
        }
        if not options:
            st.error("No states exist yet. Ask the national admin to add one.")
            st.stop()
        pick = st.selectbox("State", list(options.keys()), key="state_pick_selector")
        if st.button("Confirm state for this session"):
            st.session_state["picked_state"] = options[pick]
            st.session_state["picked_state_name"] = pick
            st.rerun()
        st.stop()
    return st.session_state["picked_state"]


def require_state_context() -> str:
    """Role-dispatching wrapper for pages now shared between state-role
    and national-role sessions (Manage Trainings, Questionnaires).

    - 'state' role: delegates to require_state_picked() — LOCKED for the
      whole session, as before, 'NAT' excluded.
    - 'national' role: a freely re-pickable selector (no lock, no
      confirm step, re-rendered every page load) that INCLUDES the
      'NAT' pseudo-state, since the national team needs to select it
      specifically to view/manage National-level trainings. National
      admins already have full cross-state access via RLS/service_role
      on their other pages, so locking them to one state here would be
      pure friction with no security benefit.

    Returns the active state code for this page view either way."""
    require_role(["state", "national"])
    if st.session_state["role"] == "state":
        return require_state_picked()

    states_res = get_client().table("states").select("code, name").order("name").execute()
    options = {s["name"]: s["code"] for s in (states_res.data or [])}
    if not options:
        st.error("No states exist yet. Ask the national admin to add one.")
        st.stop()
    names = list(options.keys())
    default_name = st.session_state.get("national_state_pick_name", names[0])
    default_idx = names.index(default_name) if default_name in names else 0
    pick = st.selectbox(
        "Working state (you can change this anytime — this is NOT locked for national admins)",
        names,
        index=default_idx,
        key="national_state_pick_selector",
    )
    st.session_state["national_state_pick_name"] = pick
    return options[pick]


def fetch_all(build_query, page_size: int = 1000) -> list[dict]:
    """Page through a Supabase/PostgREST query until all rows are
    fetched. PostgREST silently caps any query at 1000 rows by default.
    `build_query` must be a zero-arg callable returning a FRESH query
    builder each call, since supabase-py query objects are consumed
    once .execute()'d."""
    rows: list[dict] = []
    offset = 0
    while True:
        res = build_query().range(offset, offset + page_size - 1).execute()
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def escape_markdown(text) -> str:
    """Escape markdown/LaTeX-special characters so plain data renders as
    literal text in st.markdown / widget labels (handles Excel-formula
    style question/option text like "$A$2")."""
    if text is None:
        return ""
    s = str(text)
    for ch in ["\\", "$", "_", "`", "#", "~"]:
        s = s.replace(ch, "\\" + ch)
    return s


def render_question_markdown(text) -> str:
    """Render question text allowing authored **bold** on specific
    words, escaping everything else so it renders as literal plain text."""
    if text is None:
        return ""
    import re

    parts = re.split(r"(\*\*.+?\*\*)", str(text))
    rendered = []
    for part in parts:
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            rendered.append(f"**{escape_markdown(part[2:-2])}**")
        else:
            rendered.append(escape_markdown(part))
    return "".join(rendered)
