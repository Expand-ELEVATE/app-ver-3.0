"""Export — role-aware. State-role sessions are auto-filtered to their
session's locked state (no user-facing state filter, since it's already
locked). National sessions get the full multi-state/training/level
filter set, same as v2's national Export.
"""
import streamlit as st
import pandas as pd
from io import BytesIO
from zipfile import ZipFile
from common import require_role, get_client, fetch_all, LEVELS

require_role(["state", "national"])
sb = get_client()
st.title("Export")

role = st.session_state["role"]

if role == "state":
    from common import require_state_picked

    picked_state = require_state_picked()
    st.caption(f"Exporting data for your locked state: **{picked_state}**")
    pick_states = [picked_state]
else:
    states = fetch_all(lambda: sb.table("states").select("*").order("name"))
    state_codes = [s["code"] for s in states] if states else []
    pick_states = st.multiselect("Limit to state(s) — leave empty for ALL states", state_codes)

trainings = fetch_all(lambda: sb.table("trainings").select("*"))
scope_trainings = [t for t in trainings if not pick_states or t["state_code"] in pick_states]
training_names = sorted({t["training_name"] for t in scope_trainings})
pick_trainings = st.multiselect("Limit to training(s) — leave empty for ALL in scope", training_names)
pick_levels = st.multiselect("Limit to staff level(s) — leave empty for ALL levels", LEVELS)

staff = fetch_all(lambda: sb.table("staff").select("*"))
staff_df = pd.DataFrame(staff) if staff else pd.DataFrame()
training_by_id = {t["id"]: t for t in trainings}

if not staff_df.empty:
    staff_df["training_name"] = staff_df["training_id"].map(lambda tid: training_by_id.get(tid, {}).get("training_name"))
    if pick_states:
        staff_df = staff_df[staff_df["state_code"].isin(pick_states)]
    if pick_trainings:
        staff_df = staff_df[staff_df["training_name"].isin(pick_trainings)]
    if pick_levels:
        staff_df = staff_df[staff_df["level"].isin(pick_levels)]

staff_ids = staff_df["id"].tolist() if not staff_df.empty else []

instances = fetch_all(lambda: sb.table("test_instances").select("*").in_("staff_id", staff_ids)) if staff_ids else []
completed = [i for i in instances if i["status"] == "completed"]

rows = []
if completed:
    all_ids = [i["id"] for i in completed]
    responses = fetch_all(lambda: sb.table("responses").select("*").in_("test_instance_id", all_ids))
    resp_by_instance: dict = {}
    for r in responses:
        resp_by_instance.setdefault(r["test_instance_id"], []).append(r)
    max_q = max((r["question_no"] for r in responses), default=0)
    staff_by_id = {s["id"]: s for s in staff}

    for inst in completed:
        s = staff_by_id.get(inst["staff_id"], {})
        t = training_by_id.get(s.get("training_id"), {})
        row = {
            "staff_id": inst["staff_id"],
            "state_code": s.get("state_code"),
            "level": s.get("level"),
            "training_name": t.get("training_name"),
            "training_level": t.get("level"),
            "stage": inst["stage"],
            "total_score": inst["score"],
            "max_score": inst["max_score"],
            "submitted_at": inst["submitted_at"],
        }
        by_q = {r["question_no"]: int(r["is_correct"]) for r in resp_by_instance.get(inst["id"], [])}
        for q in range(1, max_q + 1):
            row[f"Q{q}_correct"] = by_q.get(q)
        rows.append(row)

export_df = pd.DataFrame(rows) if rows else pd.DataFrame()
st.subheader("Staff (self-enrolled)")
st.dataframe(staff_df, use_container_width=True)
st.subheader("Per-question score export (completed tests)")
st.dataframe(export_df, use_container_width=True)

buf = BytesIO()
with ZipFile(buf, "w") as zf:
    zf.writestr("staff.csv", staff_df.to_csv(index=False) if not staff_df.empty else "")
    zf.writestr("per_question_scores.csv", export_df.to_csv(index=False) if not export_df.empty else "")

label_parts = []
if pick_states:
    label_parts.append("_".join(pick_states))
if pick_trainings:
    label_parts.append("filtered_trainings")
if pick_levels:
    label_parts.append("_".join(pick_levels))
label = "_".join(label_parts) if label_parts else "all"

st.download_button(
    f"Download CSV export ({label}) as .zip",
    buf.getvalue(),
    file_name=f"expand_elevate_export_{label}.zip",
    mime="application/zip",
)
