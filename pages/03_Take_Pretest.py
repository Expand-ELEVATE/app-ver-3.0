"""PRE-TEST, public, no-login, phone-friendly.

v3 CHANGE from v2: because this is now ONE shared app for every state
(not a separate deployment per state with a fixed STATE_CODE secret),
a staff member must first pick which STATE's trainings they want to see
— there is no other way for this public, unauthenticated page to know
which state's open trainings to list.

This is a SEPARATE page/URL from the post-test page on purpose — a
staff member who already has an ID should never land on a screen where
accidentally tapping the wrong tab/button starts a brand-new pre-test
instead of their post-test. Share THIS page's link before a training
starts; share the post-test page's link (4_Take_Posttest) separately,
after it ends.

This page must NEVER call require_login() — staff never authenticate.
All access goes through SECURITY DEFINER RPCs in schema.sql, each doing
its own authorization check.
"""
import base64
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timezone
from common import get_client, render_question_markdown, escape_markdown

st.set_page_config(page_title="Pre-Test", layout="centered")
sb = get_client()

st.title("Expand ELEVATE — Pre-Test")

if "last_pretest_result" in st.session_state:
    result = st.session_state["last_pretest_result"]
    st.success("Pre-test submitted. Thank you!")
    st.balloons()
    st.metric("Your score", f"{result['score']} / {result['max_score']}")
    st.error(
        f"## Your ID: {result['staff_id']}\n\n"
        "**Write this down right now, or confirm the file below downloaded.** "
        "You MUST enter this exact ID to take your post-test later. Nobody — "
        "including your state data analyst — can look it up for you if "
        "you lose it; your results stay confidential."
    )

    txt_content = (
        f"Expand ELEVATE pre-test ID\n"
        f"State: {st.session_state.get('pretest_state_picked', '')}\n"
        f"Your ID: {result['staff_id']}\n"
        f"Score: {result['score']} / {result['max_score']}\n"
        f"Date: {datetime.now(timezone.utc).isoformat()}\n\n"
        f"Keep this ID safe — you need it for your post-test.\n"
    )
    csv_content = f"id,score,max_score\n{result['staff_id']},{result['score']},{result['max_score']}\n"

    if not st.session_state.get("pretest_auto_downloaded"):
        b64 = base64.b64encode(txt_content.encode()).decode()
        components.html(
            f"""
            <a id="autodl" href="data:text/plain;base64,{b64}"
               download="expand_elevate_staff_id.txt" style="display:none;"></a>
            <script>
                document.getElementById('autodl').click();
            </script>
            """,
            height=0,
        )
        st.session_state["pretest_auto_downloaded"] = True

    st.caption(
        "A download may have started automatically. If nothing appeared "
        "(common on iPhone/Safari), use these buttons instead:"
    )
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Download ID as .txt", txt_content, file_name="expand_elevate_staff_id.txt", mime="text/plain"
        )
    with c2:
        st.download_button(
            "Download ID as .csv", csv_content, file_name="expand_elevate_staff_id.csv", mime="text/csv"
        )
    if st.button("Done"):
        del st.session_state["last_pretest_result"]
        st.session_state.pop("pretest_auto_downloaded", None)
        st.session_state.pop("pretest_state_picked", None)
        st.rerun()
    st.stop()

if "pretest_state_picked" not in st.session_state:
    st.caption("First, select your state.")
    states_res = sb.table("states").select("code, name").order("name").execute()
    state_options = {s["name"]: s["code"] for s in (states_res.data or [])}
    if not state_options:
        st.error("No states are configured yet. Ask your trainer.")
        st.stop()
    state_pick = st.selectbox("Your state", list(state_options.keys()), key="pretest_state_selector")
    if st.button("Continue"):
        st.session_state["pretest_state_picked"] = state_options[state_pick]
        st.rerun()
    st.stop()

state_picked = st.session_state["pretest_state_picked"]

if "pretest_training_id" not in st.session_state:
    st.caption(f"State: **{state_picked}**. Select the training you are attending, then your own level.")
    trainings = sb.rpc("staff_list_open_trainings", {"p_state_code": state_picked}).execute().data or []
    if not trainings:
        st.info("No training is currently open for pre-tests in this state. Ask your trainer.")
    else:
        labels = {f"{t['training_name']} ({t['level']})": t for t in trainings}
        pick = st.selectbox("Training", list(labels.keys()), key="pre_training_pick")
        level = st.radio(
            "What is the level of your work engagement? Do you work at "
            "State level, District level or Sub-district level?",
            ["State", "District", "Sub-District"],
            index=None,
            format_func=lambda lvl: {
                "State": "1. State level staff",
                "District": "2. District level staff",
                "Sub-District": "3. Sub-district level staff",
            }[lvl],
            key="pre_level_pick",
        )
        if st.button("Start pre-test"):
            if level is None:
                st.error("Please select your level before starting.")
            else:
                t = labels[pick]
                st.session_state["pretest_training_id"] = t["training_id"]
                st.session_state["pretest_level"] = level
                st.rerun()
    st.stop()

training_id = st.session_state["pretest_training_id"]
st.info(f"State: **{state_picked}** — Stage: **PRE-TEST** — your level: **{st.session_state['pretest_level']}**")

q_res = sb.rpc("staff_get_pretest_questions", {"p_training_id": training_id}).execute()
questions = q_res.data or []
if not questions:
    st.error("No questions found for this training. Contact your state analyst.")
    st.stop()

answers = {}
with st.form("pretest_form"):
    for q in questions:
        st.markdown(f"Q{q['question_no']}. {render_question_markdown(q['question_text'])}")
        choice = st.radio(
            f"pre_q_{q['question_no']}",
            options=["A", "B", "C", "D"],
            index=None,
            format_func=lambda opt, q=q: f"{opt}. {escape_markdown(q[f'option_{opt.lower()}'])}",
            key=f"pre_q_{q['question_no']}",
            label_visibility="collapsed",
        )
        answers[q["question_no"]] = choice
        st.divider()
    submit = st.form_submit_button("Submit Pre-test")

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
        "staff_submit_pretest",
        {
            "p_training_id": training_id,
            "p_level": st.session_state["pretest_level"],
            "p_answers": payload,
        },
    ).execute()
    if result.data:
        st.session_state["last_pretest_result"] = result.data[0]
        del st.session_state["pretest_training_id"]
        del st.session_state["pretest_level"]
        st.rerun()
    else:
        st.error("Submission failed — please contact your state analyst.")
