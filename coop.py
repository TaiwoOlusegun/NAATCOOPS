# coop.py
import os
import datetime
import pandas as pd
import streamlit as st
from typing import Optional, Dict, Any
from supabase import create_client, Client

# =========================
# Config & Setup
# =========================
st.set_page_config(
    page_title="NAAT Multipurpose Cooperative JOSTUM",
    page_icon="🏦",
    layout="wide"
)

COOP_NAME = "NAAT Multipurpose Cooperative JOSTUM"

# -------------------------
# Supabase Credentials
# -------------------------
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    st.error("❌ Supabase credentials missing. Please add SUPABASE_URL and SUPABASE_KEY to your Streamlit Cloud secrets.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# Helpers to handle responses
# -------------------------
def resp_data(resp):
    """Extract data from Supabase response object or dict"""
    try:
        d = getattr(resp, "data", None)
        if d is not None:
            return d
    except Exception:
        pass
    if isinstance(resp, dict):
        return resp.get("data") or resp.get("result") or resp.get("body")
    return None

def resp_user(resp):
    """Extract user object from Supabase auth response"""
    try:
        user = getattr(resp, "user", None)
        if user:
            return user
    except Exception:
        pass
    d = resp_data(resp)
    if isinstance(d, dict):
        if "user" in d:
            return d["user"]
        session = d.get("session")
        if isinstance(session, dict) and "user" in session:
            return session["user"]
    if isinstance(resp, dict):
        return resp.get("user")
    return None

# =========================
# Session state
# =========================
for key, default in {
    "user_email": None,
    "user_id": None,
    "page": "Login",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# =========================
# Utilities
# =========================
def format_naira(amount: Optional[float]) -> str:
    try:
        return f"₦{float(amount):,.2f}"
    except Exception:
        return "₦0.00"

def get_member_by_email(email: str) -> Optional[Dict[str, Any]]:
    resp = supabase.table("members").select("*").eq("email", email).limit(1).execute()
    data = resp_data(resp) or []
    return data[0] if data else None

@st.cache_data(ttl=60)
def get_members_map() -> Dict[str, Dict[str, str]]:
    resp = supabase.table("members").select("id,name,email,role").execute()
    rows = resp_data(resp) or []
    return {
        row["id"]: {
            "name": row.get("name", ""),
            "email": row.get("email", ""),
            "role": row.get("role", "member"),
        }
        for row in rows
    }

def is_admin(email: str) -> bool:
    m = get_member_by_email(email)
    return (m or {}).get("role") == "admin"

# =========================
# Auth: login / signup / logout / reset
# =========================
def login(email: str, password: str) -> bool:
    try:
        resp = supabase.auth.sign_in_with_password({"email": email, "password": password})
        user = resp_user(resp)
        if user:
            st.session_state.user_email = user.get("email") if isinstance(user, dict) else getattr(user, "email", None)
            st.session_state.user_id = user.get("id") if isinstance(user, dict) else getattr(user, "id", None)
            st.session_state.page = "Admin" if is_admin(st.session_state.user_email) else "Member"
            return True
        st.error("❌ Login failed: Invalid credentials or no user returned.")
    except Exception as e:
        st.error(f"❌ Login failed: {e}")
    return False

def logout():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.user_email = None
    st.session_state.user_id = None
    st.session_state.page = "Login"

def signup(name: str, email: str, password: str) -> bool:
    try:
        if get_member_by_email(email):
            st.error("⚠️ Email already registered. Please log in instead.")
            return False
        supabase.auth.sign_up({"email": email, "password": password})
        supabase.table("members").insert({
            "name": name,
            "email": email,
            "savings_balance": 0,
            "loan_balance": 0,
            "role": "member"
        }).execute()
        return True
    except Exception as e:
        st.error(f"❌ Signup failed: {e}")
        return False

def send_password_reset(email: str):
    try:
        supabase.auth.reset_password_for_email(
            email,
            options={"redirect_to": "http://localhost:8501"}
        )
        st.success("✅ Password reset email sent! Check your inbox.")
    except Exception as e:
        st.error(f"❌ Password reset failed: {e}")

def get_member_required() -> Dict[str, Any]:
    if not st.session_state.user_email:
        st.error("Not authenticated.")
        st.stop()
    m = get_member_by_email(st.session_state.user_email)
    if not m:
        st.error("Member record not found.")
        st.stop()
    return m

# =========================
# Pages
# =========================
def page_login():
    st.title(f"{COOP_NAME} – Login")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
    if submitted and login(email, password):
        st.success("✅ Logged in successfully.")
        st.experimental_rerun()
    if st.button("🔄 Reset Password"):
        st.session_state.page = "ForgotPassword"
        st.experimental_rerun()

def page_register():
    st.title(f"Register – {COOP_NAME}")
    with st.form("register_form"):
        name = st.text_input("Full Name")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Create Account")
    if submitted and signup(name, email, password):
        st.success("✅ Registration successful! Please log in.")
        st.session_state.page = "Login"
        st.experimental_rerun()

def page_forgot_password():
    st.title("🔄 Reset Your Password")
    with st.form("reset_form"):
        email = st.text_input("Email")
        submitted = st.form_submit_button("Send Reset Link")
    if submitted:
        if email:
            send_password_reset(email)
        else:
            st.warning("⚠️ Please enter your email.")

def page_admin_dashboard():
    st.title("👨‍💼 Admin Dashboard")
    st.write("Welcome Admin! (placeholder content)")

def page_member_dashboard():
    st.title("👤 Member Dashboard")
    st.write("Welcome Member! (placeholder content)")

# =========================
# Sidebar Navigation
# =========================
with st.sidebar:
    st.markdown(f"## 🏦 {COOP_NAME}")
    if st.session_state.user_email:
        st.write(f"**Signed in:** {st.session_state.user_email}")
        if is_admin(st.session_state.user_email):
            choice = st.radio("Go to", ["Admin", "Member"], index=0 if st.session_state.page == "Admin" else 1)
        else:
            choice = "Member"
        if st.button("Logout"):
            logout()
            st.experimental_rerun()
        st.session_state.page = choice
    else:
        choice = st.radio("Go to", ["Login", "Register"], index=0 if st.session_state.page == "Login" else 1)
        st.session_state.page = choice

# =========================
# Router
# =========================
if st.session_state.user_email:
    if st.session_state.page == "Admin":
        page_admin_dashboard()
    else:
        page_member_dashboard()
else:
    if st.session_state.page == "Register":
        page_register()
    elif st.session_state.page == "ForgotPassword":
        page_forgot_password()
    else:
        page_login()
