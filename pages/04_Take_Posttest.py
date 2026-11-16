"""POST-TEST, public, no-login, phone-friendly.

Unlike the Pre-Test page, no state picker is needed here — the staff
member's ID alone resolves their pending post-test instance regardless
of which state it belongs to (the ID is globally unique).

This is a SEPARATE page/URL from the pre-test page on purpose — someone
who already has an ID should land directly on an "enter your ID" screen,
never somewhere a mis-tap could start a brand-new pre-test instead.
Share THIS page's link only after a training ends.

This page must NEVER call require_login() — staff never authenticate.
All access goes through SECURITY DEFINER RPCs in schema.sql, each doing
its own authorization check, revealing nothing on a bad ID.
"""
import streamlit as st
from common import get_client, render_question_markdown, escape_markdown

st.set_page_config(page_title="Post-Test", layout="centered")
sb = get_client()

st.title("Expand ELEVATE — Post-Test")

if "last_posttest_result" in st.session_state:
    result = st.session_state["last_posttest_result"]
    st.success("Post-test submitted. Thank you — this completes your pair!")
    st.balloons()
    st.metric("Your score", f"{result['score']} / {result['max_score']}")
    if st.button("Finish"):
        del st.session_state["last_posttest_result"]
        st.rerun()
    st.stop()

if "posttest_instance_id" not in st.session_state:
    st.caption("Enter the ID you were shown/downloaded when you submitted your pre-test.")
    staff_id = st.text_input("Your ID", key="post_id_input").strip().upper()
    if st.button("Start post-test"):
        res = sb.rpc("staff_get_pending_posttest", {"p_staff_id": staff_id}).execute()
        if not res.data:
            st.error(
                "No pending post-test found for this ID. Double-check the ID, "
                "or contact your state analyst if you believe this is an error."
            )
        else:
            row = res.data[0]
            st.session_state["posttest_instance_id"] = row["test_instance_id"]
            st.session_state["posttest_training_name"] = row["training_name"]
            st.rerun()
    st.stop()

test_instance_id = st.session_state["posttest_instance_id"]
st.info(f"Stage: **POST-TEST** — Training: **{st.session_state['posttest_training_name']}**")

q_res = sb.rpc("staff_get_questions", {"p_test_instance_id": test_instance_id}).execute()
questions = q_res.data or []
if not questions:
    st.error("No questions found for this test. Contact your state analyst.")
    st.stop()

answers = {}
with st.form("posttest_form"):
    for q in questions:
        st.markdown(f"Q{q['question_no']}. {render_question_markdown(q['question_text'])}")
        choice = st.radio(
            f"post_q_{q['question_no']}",
            options=["A", "B", "C", "D"],
            index=None,
            format_func=lambda opt, q=q: f"{opt}. {escape_markdown(q[f'option_{opt.lower()}'])}",
            key=f"post_q_{q['question_no']}",
            label_visibility="collapsed",
        )
        answers[q["question_no"]] = choice
        st.divider()
    submit = st.form_submit_button("Submit Post-test")

if submit:
    unanswered = [qn for qn, opt in answers.items() if opt is None]
    if unanswered:
        st.error(
            f"Please answer all questions before submitting. "
            f"Missing: Q{', Q'.join(str(q) for q in sorted(unanswered))}"
        )
        st.stop()
    payload = [{"question_no": qn, "selected_option": opt} for qn, opt in answers.items()]
    result = sb.rpc(
        "staff_submit_test", {"p_test_instance_id": test_instance_id, "p_answers": payload}
    ).execute()
    if result.data:
        st.session_state["last_posttest_result"] = result.data[0]
        del st.session_state["posttest_instance_id"]
        del st.session_state["posttest_training_name"]
        st.rerun()
    else:
        st.error("Submission failed — please contact your state analyst.")
