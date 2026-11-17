"""Manage Trainings — shared between state-role and national-role
sessions. A state-role session is scoped to its session-locked state, as
before. A national-role session gets a freely switchable state picker
AND the extra 'National' training Level, for cross-state trainings the
national team itself creates (e.g. a single refresher for all states).

A training is NOT a staff record. The analyst/national-admin specifies
a training name, its level, and which questionnaire (default or an
uploaded alternate) + language to use. Staff pick an OPEN training
themselves on the no-login Pretest page and self-generate their own ID
at pre-test submission.

v3 note: for State/District/Sub-District level trainings, the state is
set automatically from require_state_context()'s active state — there
is no separate per-training state dropdown for those. The ONE exception
is Level='National' (national role only): that always writes
state_code='NAT' (a reserved pseudo-state row), regardless of whatever
state is currently picked in the context selector above — a National
training is inherently cross-state, not tied to whichever state the
admin happened to be looking at a moment ago.
"""
import streamlit as st
import pandas as pd
from common import require_state_context, get_client, fetch_all, LEVELS, TRAINING_LEVELS, NATIONAL_PSEUDO_STATE_CODE

picked_state = require_state_context()
role = st.session_state["role"]
sb = get_client()
st.title("Manage Trainings")

if picked_state == NATIONAL_PSEUDO_STATE_CODE:
    st.caption("Working context: **National (all states)**")
else:
    display_name = st.session_state.get("picked_state_name") or st.session_state.get("national_state_pick_name") or picked_state
    st.caption(f"Working on state: **{display_name}** ({picked_state})")

questionnaires = fetch_all(lambda: sb.table("questionnaire_meta").select("*").order("is_default", desc=True))
if not questionnaires:
    st.error("No questionnaire exists yet. Ask the national admin to upload one first.")
    st.stop()

q_labels = {
    f"{q['title']}" + (" (default)" if q["is_default"] else ""): q["id"] for q in questionnaires
}

level_options = TRAINING_LEVELS if role == "national" else LEVELS

st.subheader("Create a new training")
with st.form("new_training"):
    training_name = st.text_input("Training name (e.g. 'Q1 2026 Data Quality Refresher — District X')")
    level = st.selectbox("Level of this training", level_options)
    if role == "national":
        st.caption(
            "Picking 'National' creates a cross-state training (state_code = "
            f"'{NATIONAL_PSEUDO_STATE_CODE}') regardless of the working state "
            "selected above. Any other level uses the working state above."
        )
    q_choice = st.selectbox("Questionnaire to use", list(q_labels.keys()))
    language = st.radio("Questionnaire language", ["default", "translated"], horizontal=True)
    submitted = st.form_submit_button("Create training")

if submitted:
    if not training_name.strip():
        st.error("Training name is required.")
    elif level != "National" and picked_state == NATIONAL_PSEUDO_STATE_CODE:
        st.error(
            "Your working context is 'National (all states)', but you picked a "
            "non-National level. Switch the working-state selector above to a "
            "real state first, or change the Level to 'National'."
        )
    else:
        effective_state_code = NATIONAL_PSEUDO_STATE_CODE if level == "National" else picked_state
        questionnaire_id = q_labels[q_choice]
        if language == "translated":
            trans = (
                sb.table("state_questionnaire_translations")
                .select("question_no")
                .eq("state_code", effective_state_code)
                .eq("questionnaire_id", questionnaire_id)
                .execute()
            )
            if not trans.data:
                st.warning(
                    "No translated version uploaded yet for this questionnaire "
                    f"for {effective_state_code}. Go to the Questionnaires page to "
                    "upload one, or pick 'default' here."
                )
        sb.table("trainings").insert(
            {
                "state_code": effective_state_code,
                "training_name": training_name.strip(),
                "level": level,
                "questionnaire_id": questionnaire_id,
                "language_used": language,
                "status": "open",
                "created_by": st.session_state["user_id"],
            }
        ).execute()
        st.success(f"Training '{training_name}' created ({effective_state_code}) and OPEN for staff to self-enrol.")
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
