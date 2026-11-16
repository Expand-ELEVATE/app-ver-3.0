"""Questionnaire Manager — national-only. Manage MULTIPLE questionnaires
(default + alternates). Any number can exist at once; exactly one is
flagged `is_default` (enforced by a partial unique index) — states
choose it, or any alternate, per training.
"""
import streamlit as st
import pandas as pd
from io import BytesIO
from zipfile import ZipFile
from common import require_role, get_admin_client, fetch_all

require_role(["national"])
sb = get_admin_client()
st.title("Questionnaire Manager")

existing = fetch_all(lambda: sb.table("questionnaire_meta").select("*").order("created_at", desc=True))

st.subheader("Existing questionnaires")
if existing:
    st.dataframe(pd.DataFrame(existing)[["title", "is_default", "created_at", "id"]], use_container_width=True)
else:
    st.info("No questionnaires uploaded yet.")

st.divider()
st.subheader("Upload a new questionnaire")
st.markdown(
    """
    Upload a CSV with exactly these columns:
    `question_no, question_text, option_a, option_b, option_c, option_d, correct_option`

    - `correct_option` must be one of `A`, `B`, `C`, `D`.
    - Wrap words in `**double asterisks**` in `question_text` for bold —
      everything else renders as plain literal text (safe for `$`, `_`,
      `#`, formula-style text like `$A$2`).
    - See `docs/questionnaire_template.csv` in the repo for a template.
    """
)

title = st.text_input("Questionnaire title")
set_default = st.checkbox("Set this as the DEFAULT questionnaire (replaces the current default)")
uploaded = st.file_uploader("Upload questions CSV", type="csv")

if uploaded and title:
    df = pd.read_csv(uploaded)
    required_cols = {
        "question_no", "question_text", "option_a", "option_b",
        "option_c", "option_d", "correct_option",
    }
    if not required_cols.issubset(df.columns):
        st.error(f"Missing required columns: {required_cols - set(df.columns)}")
    elif not df["correct_option"].isin(["A", "B", "C", "D"]).all():
        st.error("correct_option must be A, B, C, or D for every row.")
    else:
        st.dataframe(df, use_container_width=True)
        if st.button("Create this questionnaire"):
            if set_default:
                sb.table("questionnaire_meta").update({"is_default": False}).eq("is_default", True).execute()
            meta = sb.table("questionnaire_meta").insert(
                {"title": title, "is_default": set_default, "created_by": st.session_state["user_id"]}
            ).execute()
            qid = meta.data[0]["id"]
            records = [
                {
                    "questionnaire_id": qid,
                    "question_no": int(row["question_no"]),
                    "question_text": row["question_text"],
                    "option_a": row["option_a"],
                    "option_b": row["option_b"],
                    "option_c": row["option_c"],
                    "option_d": row["option_d"],
                    "correct_option": row["correct_option"],
                }
                for _, row in df.iterrows()
            ]
            sb.table("questions").insert(records).execute()
            st.success(f"Questionnaire '{title}' created with {len(records)} questions.")
            st.rerun()

st.divider()
st.subheader("Set an existing questionnaire as default")
if existing:
    labels = {q["title"]: q["id"] for q in existing if not q["is_default"]}
    if labels:
        pick = st.selectbox("Select a questionnaire", list(labels.keys()))
        if st.button("Make this the default"):
            sb.table("questionnaire_meta").update({"is_default": False}).eq("is_default", True).execute()
            sb.table("questionnaire_meta").update({"is_default": True}).eq("id", labels[pick]).execute()
            st.success(f"'{pick}' is now the default questionnaire.")
            st.rerun()
    else:
        st.info("Every questionnaire is already the default, or none exist.")

st.divider()
st.subheader("Delete a questionnaire")
st.warning(
    "Blocked if any training (open or closed, in any state) still uses "
    "this questionnaire — close/retire those trainings' use first, or "
    "accept the error, which protects historical results from being "
    "orphaned. A backup is downloaded here before any delete."
)
if existing:
    del_labels = {q["title"]: q["id"] for q in existing}
    del_pick = st.selectbox("Select a questionnaire to delete", list(del_labels.keys()), key="del_pick")
    qid = del_labels[del_pick]

    in_use = fetch_all(lambda: sb.table("trainings").select("id, training_name").eq("questionnaire_id", qid))
    if in_use:
        st.error(
            f"Cannot delete — {len(in_use)} training(s) still reference this "
            f"questionnaire: {', '.join(t['training_name'] for t in in_use)}"
        )
    else:
        questions = fetch_all(lambda: sb.table("questions").select("*").eq("questionnaire_id", qid))
        translations = fetch_all(
            lambda: sb.table("state_questionnaire_translations").select("*").eq("questionnaire_id", qid)
        )
        buf = BytesIO()
        with ZipFile(buf, "w") as zf:
            zf.writestr("questionnaire_meta.csv", pd.DataFrame([q for q in existing if q["id"] == qid]).to_csv(index=False))
            zf.writestr("questions.csv", pd.DataFrame(questions).to_csv(index=False))
            zf.writestr("translations.csv", pd.DataFrame(translations).to_csv(index=False))
        st.download_button(
            "Step 1 — Download backup of this questionnaire",
            buf.getvalue(),
            file_name=f"questionnaire_backup_{del_pick}.zip",
            mime="application/zip",
        )
        confirm = st.checkbox("I have downloaded the backup above.", key="del_confirm_cb")
        confirm_text = st.text_input("Type DELETE to confirm", key="del_confirm_text")
        if confirm and confirm_text == "DELETE":
            if st.button(f"Permanently delete '{del_pick}'", type="primary"):
                sb.table("questionnaire_meta").delete().eq("id", qid).execute()
                st.success(f"Deleted questionnaire '{del_pick}'.")
                st.rerun()
