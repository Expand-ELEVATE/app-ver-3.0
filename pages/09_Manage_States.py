"""Manage States — national-only. Master lookup table every training
and staff record references by state_code. Only the national admin can
add, rename, or remove entries.
"""
import streamlit as st
import pandas as pd
from common import require_role, get_admin_client

require_role(["national"])
sb = get_admin_client()
st.title("Manage States")

st.markdown(
    """
    This is the master list of participating states/UTs. In v3, every
    state-role analyst picks a state from this list at the start of
    their session (not a fixed per-deployment secret) — add a state
    here before telling anyone to pick it.

    To onboard a new state as the project expands: just add it here.
    There is no per-state login to create any more — the single shared
    State login already works for every state listed below.
    """
)

existing = sb.table("states").select("*").order("name").execute()
st.subheader("Current states")
st.dataframe(pd.DataFrame(existing.data), use_container_width=True)

st.divider()
st.subheader("Add a new state")

with st.form("add_state"):
    code = st.text_input("Code (short, unique, e.g. 'MH', 'KA', 'DL')").strip().upper()
    name = st.text_input("Full name (e.g. 'Maharashtra')").strip()
    submitted = st.form_submit_button("Add state")

if submitted:
    if not code or not name:
        st.error("Both code and name are required.")
    else:
        existing_codes = {s["code"] for s in existing.data} if existing.data else set()
        if code in existing_codes:
            st.error(f"Code '{code}' already exists.")
        else:
            sb.table("states").insert({"code": code, "name": name}).execute()
            st.success(f"Added state: {code} — {name}. It now appears in the shared State login's state picker.")
            st.rerun()

st.divider()
st.subheader("Remove a state")
st.warning(
    "Only remove a state if it has NO staff, trainings, or translations "
    "yet — those reference the state code via foreign keys and removal "
    "will fail (safely) if any exist. Delete the dependent records first "
    "via 'Admin — Delete Data' if you really need to retire a state with "
    "existing data."
)
state_codes = [s["code"] for s in existing.data] if existing.data else []
if state_codes:
    to_remove = st.selectbox("Select a state code to remove", [""] + state_codes)
    if to_remove and st.button(f"Remove {to_remove}", type="primary"):
        try:
            sb.table("states").delete().eq("code", to_remove).execute()
            st.success(f"Removed state {to_remove}.")
            st.rerun()
        except Exception as e:
            st.error(f"Could not remove — likely has existing data referencing it: {e}")
