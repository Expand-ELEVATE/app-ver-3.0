"""Manage State Login — national-only. v3's ONE single shared account/
password used by EVERY state analyst, in EVERY state. Unlike national
logins, there is deliberately only ever ONE of these — this page
creates it once if missing, and lets the national admin reset its
password (e.g. when rotating it after a departure, or on a routine
schedule — since everyone knows this password, rotation is the main
defence against it ever becoming stale/compromised).
"""
import streamlit as st
import secrets
import string
from common import require_role, get_admin_client

require_role(["national"])
sb = get_admin_client()
st.title("Manage State Login (shared)")

st.warning(
    "Dr Aswath's explicit decision: this is ONE single login shared by "
    "every state's data analyst across every state. There is no "
    "individual audit trail on the state side, and no database-level "
    "isolation between states — see docs/ARCHITECTURE.md section 9. "
    "Treat this password the same way you'd treat a shared building key: "
    "rotate it whenever anyone who knew it no longer should."
)


def generate_temp_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


existing = sb.table("admin_profiles").select("user_id, created_at").eq("role", "state").execute()
state_profiles = existing.data or []

if len(state_profiles) > 1:
    st.error(
        f"Found {len(state_profiles)} 'state' role accounts — v3 expects "
        "exactly one. This is unexpected; check the Supabase dashboard "
        "directly before proceeding."
    )

if not state_profiles:
    st.subheader("Create the shared State login (one-time)")
    st.caption("No shared State account exists yet. Create it once; every analyst will use this same login.")
    with st.form("create_state_login"):
        email = st.text_input("Email for the shared State account (e.g. a generic address everyone can use)")
        submitted = st.form_submit_button("Create the shared State login")
    if submitted:
        if not email.strip():
            st.error("Email is required.")
        else:
            temp_password = generate_temp_password()
            try:
                created = sb.auth.admin.create_user(
                    {"email": email.strip(), "password": temp_password, "email_confirm": True}
                )
                sb.table("admin_profiles").insert({"user_id": created.user.id, "role": "state"}).execute()
                st.success(f"Created the shared State login: **{email}**.")
                st.info(
                    f"**Password (shown once — copy it now):** `{temp_password}`\n\n"
                    "Distribute this email + password to EVERY state's data analyst, "
                    "over a secure channel. Everyone uses the exact same credential."
                )
                st.rerun()
            except Exception as e:
                st.error(f"Could not create login: {e}")
else:
    user_id = state_profiles[0]["user_id"]
    try:
        user = sb.auth.admin.get_user_by_id(user_id)
        email = user.user.email
        banned = getattr(user.user, "banned_until", None)
    except Exception:
        email = "(user record missing)"
        banned = None

    st.subheader("Current shared State login")
    st.write(f"**Email:** {email}")
    st.write(f"**Status:** {'revoked' if banned else 'active'}")
    st.caption(f"Created: {state_profiles[0]['created_at']}")

    st.divider()
    st.subheader("Reset the shared password")
    st.markdown(
        "Generates a brand-new password for the ONE shared account. "
        "**Every** state analyst must be told the new password before "
        "they can log in again — there is no per-person password to "
        "reset individually."
    )
    if st.button("Generate new shared password", type="primary"):
        new_pw = generate_temp_password()
        try:
            sb.auth.admin.update_user_by_id(user_id, {"password": new_pw})
            st.success("Shared State password reset.")
            st.info(
                f"**New shared password (shown once — copy it now):** `{new_pw}`\n\n"
                "Distribute this to EVERY state's data analyst immediately — "
                "the old password stops working the moment you see this message."
            )
        except Exception as e:
            st.error(f"Could not reset password: {e}")

    st.divider()
    st.subheader("Revoke the shared login entirely")
    st.error(
        "This disables login for EVERY state analyst at once (long ban, "
        "reversible). Use this only if the shared credential is suspected "
        "compromised and you need to lock everyone out immediately before "
        "creating a fresh one."
    )
    if not banned and st.button("Revoke the shared State login for everyone", type="primary"):
        try:
            sb.auth.admin.update_user_by_id(user_id, {"ban_duration": "876000h"})
            st.success("Shared State login revoked for everyone.")
            st.rerun()
        except Exception as e:
            st.error(f"Could not revoke: {e}")
