# app.py
import os
import datetime
import pandas as pd
import streamlit as st
from typing import Optional, Dict, Any, List
from supabase import create_client, Client

# =========================
# Config & Setup
# =========================
st.set_page_config(page_title="NAAT Multipurpose Cooperative JOSTUM", page_icon="", layout="wide")
COOP_NAME = "NAAT Multipurpose Cooperative JOSTUM"

# Read Supabase credentials from Streamlit secrets (recommended) or env vars
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL", ""))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY", ""))

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Supabase credentials missing. Set SUPABASE_URL and SUPABASE_KEY in Streamlit Secrets.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Session state
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "user_id" not in st.session_state:
    st.session_state.user_id = None  # auth user id if you later store it
if "page" not in st.session_state:
    st.session_state.page = "Login"

# =========================
# Utilities
# =========================
def format_naira(amount: Optional[float]) -> str:
    try:
        return f"₦{float(amount):,.2f}"
    except Exception:
        return "₦0.00"

def get_member_by_email(email: str) -> Optional[Dict[str, Any]]:
    res = supabase.table("members").select("*").eq("email", email).limit(1).execute()
    data = res.data or []
    return data[0] if data else None

@st.cache_data(ttl=60)
def get_members_map() -> Dict[str, Dict[str, str]]:
    """Map member_id -> {'name':..., 'email':...} to avoid N queries in admin tables."""
    res = supabase.table("members").select("id,name,email,role").execute()
    out = {}
    for row in res.data or []:
        out[row["id"]] = {"name": row.get("name") or "", "email": row.get("email") or "", "role": row.get("role") or "member"}
    return out

def is_admin(email: str) -> bool:
    m = get_member_by_email(email)
    return (m or {}).get("role") == "admin"

def login(email: str, password: str) -> bool:
    try:
        resp = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if resp and resp.user and resp.user.email:
            st.session_state.user_email = resp.user.email
            st.session_state.user_id = getattr(resp.user, "id", None)
            st.session_state.page = "Member" if not is_admin(resp.user.email) else "Admin"
            return True
    except Exception as e:
        st.error(f"Login failed: {e}")
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
        resp = supabase.auth.sign_up({"email": email, "password": password})
        # Insert a member profile (email is unique)
        supabase.table("members").insert({
            "name": name,
            "email": email,
            "savings_balance": 0,
            "loan_balance": 0,
            "role": "member"
        }).execute()
        return True
    except Exception as e:
        st.error(f"Signup failed: {e}")
        return False

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
# UI: Authentication Pages
# =========================
def page_login():
    st.title(f"{COOP_NAME} – Login")
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
    if submitted:
        if login(email, password):
            st.success("Logged in successfully.")
            st.experimental_rerun()

def page_register():
    st.title(f"Register – {COOP_NAME}")
    with st.form("register_form", clear_on_submit=False):
        name = st.text_input("Full Name")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Create Account")
    if submitted:
        if signup(name, email, password):
            st.success("Registration successful! Please log in.")
            st.session_state.page = "Login"
            st.experimental_rerun()

# =========================
# UI: Member Dashboard
# =========================
def page_member_dashboard():
    member = get_member_required()
    st.title(f"Member Dashboard – {COOP_NAME}")
    st.caption(f"Welcome, {member.get('name') or st.session_state.user_email}")

    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("Savings Balance", format_naira(member["savings_balance"]))
    with col_b:
        st.metric("Loan Outstanding", format_naira(member["loan_balance"]))

    st.divider()

    # ---- Savings: Deposit / Withdraw ----
    st.subheader("Manage Savings")
    with st.form("savings_form", clear_on_submit=True):
        action = st.radio("Action", ["Deposit", "Withdraw"], horizontal=True)
        amount = st.number_input("Amount (₦)", min_value=0.0, step=1000.0, format="%.2f")
        submitted = st.form_submit_button("Submit")
    if submitted:
        if amount <= 0:
            st.error("Amount must be greater than zero.")
        else:
            if action == "Deposit":
                new_balance = float(member["savings_balance"]) + float(amount)
                supabase.table("members").update({"savings_balance": new_balance}).eq("id", member["id"]).execute()
                supabase.table("savings_transactions").insert({
                    "member_id": member["id"],
                    "transaction_type": "Deposit",
                    "amount": amount,
                    "created_at": datetime.datetime.now().isoformat()
                }).execute()
                st.success(f"Deposited {format_naira(amount)}. New balance: {format_naira(new_balance)}")
                st.experimental_rerun()
            else:
                if float(amount) > float(member["savings_balance"]):
                    st.error("Insufficient savings balance.")
                else:
                    new_balance = float(member["savings_balance"]) - float(amount)
                    supabase.table("members").update({"savings_balance": new_balance}).eq("id", member["id"]).execute()
                    supabase.table("savings_transactions").insert({
                        "member_id": member["id"],
                        "transaction_type": "Withdraw",
                        "amount": amount,
                        "created_at": datetime.datetime.now().isoformat()
                    }).execute()
                    st.success(f"Withdrew {format_naira(amount)}. New balance: {format_naira(new_balance)}")
                    st.experimental_rerun()

    st.divider()

    # ---- Loan Application ----
    st.subheader("Apply for Loan")
    with st.form("loan_apply_form", clear_on_submit=True):
        loan_amount = st.number_input("Loan Amount (₦)", min_value=0.0, step=10000.0, format="%.2f")
        submit_loan = st.form_submit_button("Submit Application")
    if submit_loan:
        if loan_amount <= 0:
            st.error("Loan amount must be greater than zero.")
        else:
            insert = supabase.table("loan_applications").insert({
                "member_id": member["id"],
                "amount": loan_amount,
                "status": "Pending",
                "created_at": datetime.datetime.now().isoformat()
            }).execute()
            # Insert returns data in most setups; guard for safety
            loan_row = (insert.data or [None])[0]
            supabase.table("loan_transactions").insert({
                "member_id": member["id"],
                "loan_application_id": loan_row["id"] if loan_row else None,
                "action": "Applied",
                "amount": loan_amount,
                "created_at": datetime.datetime.now().isoformat()
            }).execute()
            st.success("Loan application submitted.")
            st.experimental_rerun()

    st.divider()

    # ---- Savings History ----
    st.subheader("Savings Transactions History")
    savings_logs = supabase.table("savings_transactions")\
        .select("*").eq("member_id", member["id"]).order("created_at", desc=True).execute().data or []
    if savings_logs:
        df_sav = pd.DataFrame(savings_logs)
        df_sav["amount"] = df_sav["amount"].astype(float)
        df_sav = df_sav[["created_at", "transaction_type", "amount"]]
        df_sav.rename(columns={"created_at": "Date", "transaction_type": "Type", "amount": "Amount (₦)"}, inplace=True)
        st.dataframe(df_sav, use_container_width=True, hide_index=True)
    else:
        st.info("No savings transactions yet.")

    # ---- Loan History ----
    st.subheader("Loan Transactions History")
    loan_logs = supabase.table("loan_transactions")\
        .select("*").eq("member_id", member["id"]).order("created_at", desc=True).execute().data or []
    if loan_logs:
        df_loan = pd.DataFrame(loan_logs)
        df_loan["amount"] = df_loan["amount"].astype(float)
        df_loan = df_loan[["created_at", "action", "amount", "loan_application_id"]]
        df_loan.rename(columns={
            "created_at": "Date",
            "action": "Action",
            "amount": "Amount (₦)",
            "loan_application_id": "Application ID"
        }, inplace=True)
        st.dataframe(df_loan, use_container_width=True, hide_index=True)
    else:
        st.info("No loan transactions yet.")

# =========================
# UI: Admin Dashboard
# =========================
def page_admin_dashboard():
    if not is_admin(st.session_state.user_email):
        st.error("Admin access only.")
        st.stop()

    st.title(f"Admin Dashboard – {COOP_NAME}")
    members_map = get_members_map()

    tab1, tab2, tab3 = st.tabs(["Loan Applications", "All Savings Transactions", "All Loan Transactions"])

    # ---- Loan Applications ----
    with tab1:
        apps = supabase.table("loan_applications").select("*").order("created_at", desc=True).execute().data or []
        if not apps:
            st.info("No loan applications found.")
        else:
            for app in apps:
                member_info = members_map.get(app["member_id"], {})
                m_name = member_info.get("name") or "Unknown"
                m_email = member_info.get("email") or "unknown@example.com"

                with st.container(border=True):
                    st.write(
                        f"**Loan #{app['id']}** — {m_name} ({m_email}) | "
                        f"Amount: {format_naira(app['amount'])} | "
                        f"Status: **{app['status']}** | Date: {app['created_at']}"
                    )
                    if app["status"] == "Pending":
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button(f"✅ Approve #{app['id']}", key=f"approve_{app['id']}"):
                                # Approve application
                                supabase.table("loan_applications").update({"status": "Approved"}).eq("id", app["id"]).execute()
                                # Update member loan balance
                                member_row = supabase.table("members").select("*").eq("id", app["member_id"]).execute().data[0]
                                new_loan_balance = float(member_row["loan_balance"]) + float(app["amount"])
                                supabase.table("members").update({"loan_balance": new_loan_balance}).eq("id", member_row["id"]).execute()
                                # Log
                                supabase.table("loan_transactions").insert({
                                    "member_id": member_row["id"],
                                    "loan_application_id": app["id"],
                                    "action": "Approved",
                                    "amount": app["amount"],
                                    "created_at": datetime.datetime.now().isoformat()
                                }).execute()
                                st.success("Approved and updated member's loan balance.")
                                st.experimental_rerun()
                        with c2:
                            if st.button(f"⛔ Reject #{app['id']}", key=f"reject_{app['id']}"):
                                supabase.table("loan_applications").update({"status": "Rejected"}).eq("id", app["id"]).execute()
                                supabase.table("loan_transactions").insert({
                                    "member_id": app["member_id"],
                                    "loan_application_id": app["id"],
                                    "action": "Rejected",
                                    "amount": app["amount"],
                                    "created_at": datetime.datetime.now().isoformat()
                                }).execute()
                                st.warning("Rejected application.")
                                st.experimental_rerun()

    # ---- All Savings Transactions ----
    with tab2:
        sav_logs = supabase.table("savings_transactions").select("*").order("created_at", desc=True).execute().data or []
        if sav_logs:
            # Attach member info
            enriched = []
            for row in sav_logs:
                m = members_map.get(row["member_id"], {})
                enriched.append({
                    "Date": row["created_at"],
                    "Member": m.get("name") or "",
                    "Email": m.get("email") or "",
                    "Type": row["transaction_type"],
                    "Amount (₦)": float(row["amount"]),
                })
            df = pd.DataFrame(enriched)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Download CSV
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download Savings CSV", csv, file_name="savings_transactions.csv", mime="text/csv")
        else:
            st.info("No savings transactions found.")

    # ---- All Loan Transactions ----
    with tab3:
        loan_logs = supabase.table("loan_transactions").select("*").order("created_at", desc=True).execute().data or []
        if loan_logs:
            enriched: List[Dict[str, Any]] = []
            for row in loan_logs:
                m = members_map.get(row["member_id"], {})
                enriched.append({
                    "Date": row["created_at"],
                    "Member": m.get("name") or "",
                    "Email": m.get("email") or "",
                    "Action": row["action"],
                    "Amount (₦)": float(row["amount"]),
                    "Application ID": row.get("loan_application_id"),
                })
            df = pd.DataFrame(enriched)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Download CSV
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download Loans CSV", csv, file_name="loan_transactions.csv", mime="text/csv")
        else:
            st.info("No loan transactions found.")

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
            choice = st.radio("Go to", ["Member"], index=0)

        if st.button("Logout"):
            logout()
            st.experimental_rerun()

        # Update page based on choice
        if choice == "Admin":
            st.session_state.page = "Admin"
        else:
            st.session_state.page = "Member"
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
    else:
        page_login()
