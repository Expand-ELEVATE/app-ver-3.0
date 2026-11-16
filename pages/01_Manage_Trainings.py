"""Manage Trainings — state-role page, scoped to the session's locked state.

A training is NOT a staff record. The analyst specifies a training
name, its level, and which questionnaire (default or an uploaded
alternate) + language to use. Staff pick an OPEN training themselves on
the no-login Pretest page and self-generate their own ID at pre-test
submission.

v3 note: this page is the ONLY place a training's state is set, and it
is set automatically from the session's LOCKED picked_state (via
require_state_picked()) — there is deliberately no separate per-training
state dropdown, since the lock already fixes it for the whole session.
"""
import streamlit as st
import pandas as pd
from common import require_state_picked, get_client, fetch_all, LEVELS

picked_state = require_state_picked()
sb = get_client()
st.title("Manage Trainings")
st.caption(f"Working on state: **{st.session_state['picked_state_name']}** ({picked_state})")

questionnaires = fetch_all(lambda: sb.table("questionnaire_meta").select("*").order("is_default", desc=True))
if not questionnaires:
    st.error("No questionnaire exists yet. Ask the national admin to upload one first.")
    st.stop()

q_labels = {
    f"{q['title']}" + (" (default)" if q["is_default"] else ""): q["id"] for q in questionnaires
}

st.subheader(f"Create a new training for {picked_state}")
with st.form("new_training"):
    training_name = st.text_input("Training name (e.g. 'Q1 2026 Data Quality Refresher — District X')")
    level = st.selectbox("Level of this training", LEVELS)
    q_choice = st.selectbox("Questionnaire to use", list(q_labels.keys()))
    language = st.radio("Questionnaire language", ["default", "translated"], horizontal=True)
    submitted = st.form_submit_button("Create training")

if submitted:
    if not training_name.strip():
        st.error("Training name is required.")
    else:
        questionnaire_id = q_labels[q_choice]
        if language == "translated":
            trans = (
                sb.table("state_questionnaire_translations")
                .select("question_no")
                .eq("state_code", picked_state)
                .eq("questionnaire_id", questionnaire_id)
                .execute()
            )
            if not trans.data:
                st.warning(
                    "No translated version uploaded yet for this questionnaire "
                    f"for {picked_state}. Go to the Questionnaires page to "
                    "upload one, or pick 'default' here."
                )
        sb.table("trainings").insert(
            {
                "state_code": picked_state,
                "training_name": training_name.strip(),
                "level": level,
                "questionnaire_id": questionnaire_id,
                "language_used": language,
                "status": "open",
                "created_by": st.session_state["user_id"],
            }
        ).execute()
        st.success(f"Training '{training_name}' created for {picked_state} and OPEN for staff to self-enrol.")
        st.rerun()

st.divider()
st.subheader(f"Existing trainings — {picked_state}")

trainings = fetch_all(
    lambda: sb.table("trainings").select("*").eq("state_code", picked_state).order("created_at", desc=True)
)
if not trainings:
    st.info("No trainings created yet for this state.")
    st.stop()

q_title_by_id = {q["id"]: q["title"] for q in questionnaires}

rows = []
for t in trainings:
    staff_rows = fetch_all(lambda t=t: sb.table("staff").select("id").eq("training_id", t["id"]))
    staff_ids = [s["id"] for s in staff_rows]
    n_pretest = len(staff_ids)
    n_paired = 0
    if staff_ids:
        completed_post = fetch_all(
            lambda t=t: sb.table("test_instances")
            .select("staff_id")
            .eq("stage", "post")
            .eq("status", "completed")
            .in_("staff_id", staff_ids)
        )
        n_paired = len(completed_post)
    rows.append(
        {
            "training_name": t["training_name"],
            "level": t["level"],
            "questionnaire": q_title_by_id.get(t["questionnaire_id"], "(deleted)"),
            "language": t["language_used"],
            "status": t["status"],
            "pre-tests completed": n_pretest,
            "paired (pre+post)": n_paired,
            "created_at": t["created_at"],
            "_id": t["id"],
        }
    )
df = pd.DataFrame(rows)
st.dataframe(df.drop(columns=["_id"]), use_container_width=True)

st.divider()
st.subheader("Open / close a training")
st.caption(
    "Closing a training stops NEW staff from starting a pre-test under it "
    "(staff who already have a pending post-test can still submit it). "
    "Reopen it any time."
)
labels = {f"{r['training_name']} ({r['status']})": r["_id"] for r in rows}
pick = st.selectbox("Select a training", list(labels.keys()))
tid = labels[pick]
current_status = next(r["status"] for r in rows if r["_id"] == tid)
new_status = "closed" if current_status == "open" else "open"
if st.button(f"Set to '{new_status}'"):
    sb.table("trainings").update({"status": new_status}).eq("id", tid).execute()
    st.success(f"Training set to '{new_status}'.")
    st.rerun()
