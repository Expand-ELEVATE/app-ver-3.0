"""Dashboard — national-only. Paired pre/post dashboard with filterable
paired t-tests. Filters: state (one or all), training (one/many/all
within scope), and any combination of staff Levels. Pairing is always
defined as one staff_id having BOTH a 'pre' and a 'post' test_instance
with status='completed'.
"""
import streamlit as st
import pandas as pd
from scipy import stats
from common import require_role, get_client, fetch_all, LEVELS

require_role(["national"])
sb = get_client()
st.title("Dashboard — Paired Pre/Post Results")

states = fetch_all(lambda: sb.table("states").select("*").order("name"))
trainings = fetch_all(lambda: sb.table("trainings").select("*"))
staff = fetch_all(lambda: sb.table("staff").select("*"))
instances = fetch_all(
    lambda: sb.table("test_instances").select("*").eq("status", "completed")
)

if not staff or not instances:
    st.info("No completed test instances yet.")
    st.stop()

staff_df = pd.DataFrame(staff)
instances_df = pd.DataFrame(instances)
trainings_df = pd.DataFrame(trainings)

merged = instances_df.merge(staff_df, left_on="staff_id", right_on="id", suffixes=("", "_staff"))
merged = merged.merge(
    trainings_df[["id", "training_name", "level", "state_code"]].rename(
        columns={"id": "training_id", "level": "training_level", "state_code": "training_state_code"}
    ),
    on="training_id",
    how="left",
)

st.subheader("National overview")
total_staff = len(staff_df)
total_pre = (instances_df["stage"] == "pre").sum()
total_post = (instances_df["stage"] == "post").sum()
c1, c2, c3 = st.columns(3)
c1.metric("Staff who started a pre-test", total_staff)
c2.metric("Completed pre-tests", int(total_pre))
c3.metric("Completed post-tests", int(total_post))

st.divider()
st.subheader("Filter for paired t-test")

col1, col2, col3 = st.columns(3)
with col1:
    state_options = ["All"] + sorted(merged["state_code"].dropna().unique().tolist())
    pick_state = st.selectbox("State", state_options)
with col2:
    scope_df = merged if pick_state == "All" else merged[merged["state_code"] == pick_state]
    training_options = sorted(scope_df["training_name"].dropna().unique().tolist())
    pick_trainings = st.multiselect("Training(s) — leave empty for ALL trainings in scope", training_options)
with col3:
    pick_levels = st.multiselect("Staff Level(s) — leave empty for ALL levels", LEVELS)

filtered = merged.copy()
if pick_state != "All":
    filtered = filtered[filtered["state_code"] == pick_state]
if pick_trainings:
    filtered = filtered[filtered["training_name"].isin(pick_trainings)]
if pick_levels:
    filtered = filtered[filtered["level"].isin(pick_levels)]

pre = filtered[filtered["stage"] == "pre"][["staff_id", "score"]].rename(columns={"score": "pre_score"})
post = filtered[filtered["stage"] == "post"][["staff_id", "score", "submitted_at"]].rename(
    columns={"score": "post_score"}
)
paired = pre.merge(post, on="staff_id", how="inner").dropna()
paired = paired.sort_values("submitted_at", ascending=False).drop(columns=["submitted_at"])

info_cols = filtered[filtered["stage"] == "pre"][["staff_id", "state_code", "level", "training_name"]]
paired_display = paired.merge(info_cols, on="staff_id", how="left")

st.metric("Paired responses available in this filter", len(paired))

if len(paired) >= 2:
    t_stat, p_val = stats.ttest_rel(paired["post_score"], paired["pre_score"])
    mean_diff = (paired["post_score"] - paired["pre_score"]).mean()
    m1, m2, m3 = st.columns(3)
    m1.metric("Mean pre-score", round(paired["pre_score"].mean(), 2))
    m2.metric("Mean post-score", round(paired["post_score"].mean(), 2))
    m3.metric("Mean improvement", round(mean_diff, 2))
    st.success("A paired t-test CAN be performed (n >= 2).")
    st.subheader("Paired t-test (post vs pre)")
    st.write(f"t-statistic = **{t_stat:.3f}**, p-value = **{p_val:.4f}**")
    if p_val < 0.05:
        st.success("Statistically significant difference (p < 0.05).")
    else:
        st.warning("Not statistically significant at the 0.05 level.")
    st.subheader("Paired scores")
    st.dataframe(paired_display, use_container_width=True)
else:
    st.warning(
        f"A paired t-test CANNOT yet be performed for this filter — only "
        f"{len(paired)} paired response(s) available (need at least 2)."
    )

st.divider()
st.subheader("Paired-response counts by state and training")
pre_all = merged[merged["stage"] == "pre"][["staff_id", "state_code", "training_name", "level"]]
post_all = merged[merged["stage"] == "post"][["staff_id"]]
all_paired = pre_all.merge(post_all, on="staff_id", how="inner")
if not all_paired.empty:
    summary = all_paired.groupby(["state_code", "training_name"]).size().reset_index(name="paired_count")
    st.dataframe(summary, use_container_width=True)
else:
    st.info("No paired responses anywhere yet.")
