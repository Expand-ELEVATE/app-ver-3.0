"""Admin — Delete Data. National-only, full-platform destructive admin.

Mandatory flow: export a full backup .zip of EVERY table first, confirm
you have it, type DELETE, THEN the delete button becomes available.
Uses the service_role key — this is the only page in the merged app
that bypasses RLS to wipe data outright.
"""
import streamlit as st
import pandas as pd
from io import BytesIO
from zipfile import ZipFile
from common import require_role, get_admin_client, fetch_all

require_role(["national"])
sb = get_admin_client()
st.title("Admin — Delete Data")

st.error(
    "This deletes EVERY table's contents — all questionnaires, trainings, "
    "staff, test instances, responses, and translations, across EVERY "
    "state. This cannot be undone. You must download a full backup "
    "before this is allowed. States/admin logins are NOT affected."
)

TABLES = [
    "responses",
    "test_instances",
    "staff",
    "trainings",
    "state_questionnaire_translations",
    "questions",
    "questionnaire_meta",
]


def build_backup_zip() -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w") as zf:
        for t in TABLES:
            rows = fetch_all(lambda t=t: sb.table(t).select("*"))
            df = pd.DataFrame(rows) if rows else pd.DataFrame()
            zf.writestr(f"{t}.csv", df.to_csv(index=False))
    return buf.getvalue()


st.subheader("Step 1 — Download full backup")
backup_bytes = build_backup_zip()
st.download_button(
    "Download full backup (all tables, .zip of CSVs)",
    backup_bytes,
    file_name="expand_elevate_backup.zip",
    mime="application/zip",
)

st.subheader("Step 2 — Confirm and delete")
confirmed_download = st.checkbox("I have downloaded and safely stored the backup above.")
confirm_text = st.text_input("Type DELETE to confirm")

if confirmed_download and confirm_text == "DELETE":
    if st.button("Permanently delete ALL data in every table above", type="primary"):
        for t in TABLES:
            sb.table(t).delete().not_.is_("id", "null").execute()
        st.success("All data deleted. States and admin logins are untouched.")
else:
    st.info("Download the backup and type DELETE to enable the delete button.")
