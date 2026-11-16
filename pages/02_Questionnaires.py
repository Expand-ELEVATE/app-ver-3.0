"""Questionnaires — state-role page, view available questionnaires and
upload a translated CSV for the session's locked state.

Multiple questionnaires can exist at once (one national default plus
any number of alternates). A state picks which one to use per-training
on the Manage Trainings page; here they upload a translated version of
whichever questionnaire they plan to use.
"""
import streamlit as st
import pandas as pd
from common import require_state_picked, get_client, fetch_all

picked_state = require_state_picked()
sb = get_client()
st.title("Questionnaires")
st.caption(f"Working on state: **{st.session_state['picked_state_name']}** ({picked_state})")

questionnaires = fetch_all(lambda: sb.table("questionnaire_meta").select("*").order("is_default", desc=True))
if not questionnaires:
    st.error("No questionnaire exists yet. Ask the national admin to upload one first.")
    st.stop()

st.subheader("Available questionnaires (uploaded by national admin)")
st.dataframe(
    pd.DataFrame(questionnaires)[["title", "is_default", "created_at"]],
    use_container_width=True,
)

q_labels = {f"{q['title']}" + (" (default)" if q["is_default"] else ""): q["id"] for q in questionnaires}
pick = st.selectbox("Select a questionnaire to view / translate", list(q_labels.keys()))
questionnaire_id = q_labels[pick]

base_qs = (
    sb.table("questions")
    .select("question_no, question_text, option_a, option_b, option_c, option_d")
    .eq("questionnaire_id", questionnaire_id)
    .order("question_no")
    .execute()
)
st.dataframe(pd.DataFrame(base_qs.data), use_container_width=True)

st.divider()
st.subheader(f"Upload a translated version of '{pick}' for {picked_state}")
st.markdown(
    """
    The CSV **must** have exactly these columns, one row per question, and
    must map 1:1 to the base questionnaire above by `question_no`:

    `question_no, question_text, option_a, option_b, option_c, option_d, language_name`

    - Question and option wording may be translated freely.
    - Do **not** change the number of questions or their `question_no` values.
    - The correct answer always stays inherited from the national base
      questionnaire — translation can never change which option is correct.
    - Once uploaded, pick **"translated"** for this questionnaire when
      creating a training for this state on the Manage Trainings page.
    """
)

existing_trans = (
    sb.table("state_questionnaire_translations")
    .select("question_no, language_name")
    .eq("state_code", picked_state)
    .eq("questionnaire_id", questionnaire_id)
    .execute()
)
if existing_trans.data:
    st.info(
        f"A translated version already exists for {picked_state} on this "
        f"questionnaire ({existing_trans.data[0]['language_name']}, "
        f"{len(existing_trans.data)} questions). Uploading again replaces it."
    )

uploaded = st.file_uploader("Upload translated questionnaire CSV", type="csv")
if uploaded:
    df = pd.read_csv(uploaded)
    required_cols = {
        "question_no", "question_text", "option_a", "option_b",
        "option_c", "option_d", "language_name",
    }
    if not required_cols.issubset(df.columns):
        st.error(f"CSV is missing required columns: {required_cols - set(df.columns)}")
    else:
        base_nos = {r["question_no"] for r in base_qs.data}
        upload_nos = set(df["question_no"])
        if upload_nos != base_nos:
            st.error(
                f"question_no values must exactly match the base questionnaire. "
                f"Missing: {base_nos - upload_nos}, Extra: {upload_nos - base_nos}"
            )
        else:
            st.dataframe(df, use_container_width=True)
            if st.button("Confirm and save translated questionnaire"):
                records = [
                    {
                        "questionnaire_id": questionnaire_id,
                        "state_code": picked_state,
                        "question_no": int(row["question_no"]),
                        "question_text": row["question_text"],
                        "option_a": row["option_a"],
                        "option_b": row["option_b"],
                        "option_c": row["option_c"],
                        "option_d": row["option_d"],
                        "language_name": row["language_name"],
                    }
                    for _, row in df.iterrows()
                ]
                sb.table("state_questionnaire_translations").upsert(
                    records, on_conflict="questionnaire_id,state_code,question_no"
                ).execute()
                st.success(f"Translated questionnaire saved for {picked_state}. Select 'translated' when creating a training.")
