"""Expand ELEVATE v3 — single merged app entry point.

v3 collapses v2's two separate apps (national_app, state_app) into ONE
Streamlit application with ONE deployment, gated by two login types:
'national' (full cross-state access) and 'state' (ONE single shared
password used by every state's analyst — see common.py's module
docstring for the explicit security trade-off this accepts).
"""
import streamlit as st
from common import require_login

st.set_page_config(page_title="Expand ELEVATE", layout="wide")

require_login()

role = st.session_state["role"]
st.title("Expand ELEVATE")
st.caption(f"Logged in as: {st.session_state['email']} (role: {role})")

if role == "national":
    st.markdown(
        """
        You are logged in as a **National admin**. Use the sidebar for:
        - **Dashboard** — paired pre/post counts and paired t-tests,
          filterable by state, by training, and by any combination of
          staff Levels.
        - **Questionnaire Manager** — upload questionnaires, set the
          default, delete one (with a mandatory backup first).
        - **Admin — Delete Data** — full-platform backup and destructive
          wipe, gated behind a mandatory backup + typed confirmation.
        - **Export** — download all data, or filtered to selected
          state(s) / training(s) / level(s), as CSV with per-question
          score breakdowns.
        - **Manage States** — add new participating states.
        - **Manage State Login** — reset the ONE shared state password
          (there is only ever one — see note below).
        - **Manage National Logins** — create/revoke/reset national
          admin logins (these ARE individually named, unlike state).
        """
    )
else:
    st.markdown(
        """
        You are logged in with the **shared State login**. Use the
        sidebar for:
        - **Pick your state** (forced automatically the first time you
          visit a state page this session) — this choice is **locked
          for the rest of your session**. To work on a different state,
          log out and log back in.
        - **Manage Trainings** — create a training (name, level,
          questionnaire choice) for your picked state; staff self-enrol
          — you never create staff records or IDs.
        - **Questionnaires** — view available questionnaires, upload a
          translated CSV version for your picked state.
        - **Export** — download your picked state's data as CSV.

        **Remember:** this login is shared by every state's analyst.
        There is no database-level wall between states — only the state
        you picked at the start of this session, consistently applied
        by this app. Always double-check you picked the right state
        before creating a training.
        """
    )
    if "picked_state_name" in st.session_state:
        st.success(f"This session is locked to: **{st.session_state['picked_state_name']}**")

if st.button("Log out"):
    from common import get_client

    get_client().auth.sign_out()
    st.session_state.clear()
    st.rerun()
