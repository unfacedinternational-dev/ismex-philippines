import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
from datetime import datetime, timedelta
import time

# ==========================================
# 1. UI CONFIGURATION (FULL CUSTOM CSS)
# ==========================================
st.set_page_config(page_title="ISMEX Official", layout="wide")

st.markdown("""
<style>
header, [data-testid="stToolbar"], footer { visibility: hidden !important; display: none !important; }
.stApp { background-color: #0e1117 !important; color: white; }

.balance-box {
    background: linear-gradient(135deg, #1e222d 0%, #0e1117 100%);
    padding: 0.8rem; border-radius: 15px; border: 2px solid #00ff88;
    text-align: center; margin-bottom: 12px;
}
.balance-box h3 { font-size: 0.7rem; margin: 0; color: #8b949e; letter-spacing: 1px; }
.balance-box h1 { font-size: 2.1rem; margin: 0; color: #00ff88; }

.nested-btn {
    display: block; width: 100%; background-color: #1c2128; border: 1px solid #30363d;
    color: white; border-radius: 6px; padding: 4px 0; font-size: 15px !important;
    text-align: center; text-decoration: none; margin-top: 6px; cursor: pointer;
}
.nested-btn:hover { border-color: #00ff88; color: #00ff88; }
.nested-btn.disabled { color: #444; border-color: #222; cursor: not-allowed; pointer-events: none; }

[data-testid="column"] div.stButton > button {
    width: 100% !important; background-color: #1c2128 !important;
    border: 2px solid #00ff88 !important; color: #00ff88 !important;
    font-weight: bold !important; box-shadow: 0 0 15px rgba(0, 255, 136, 0.2) !important;
    border-radius: 8px !important;
}

div.stButton > button { background-color: #1c2128 !important; border: 1px solid #30363d !important; border-radius: 8px !important; }

div.stButton > button:first-child[kind="secondary"] {
    background-color: transparent !important; color: white !important; border: none !important;
    outline: none !important; box-shadow: none !important; padding: 0 !important;
    font-size: 12px !important; width: auto !important; height: auto !important;
    display: block; margin: 50px auto 0 auto !important;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. DATABASE & STATE MANAGEMENT
# ==========================================
@st.cache_resource
def get_db():
    if "firebase" in st.secrets:
        info = dict(st.secrets["firebase"])
        info["private_key"] = info["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(info)
        return firestore.Client(credentials=creds)
    return None

db = get_db()

def get_user_data(username):
    doc = db.collection("investors").document(username).get()
    return doc.to_dict() if doc.exists else None

def load_reg(): 
    return {doc.id: doc.to_dict() for doc in db.collection("investors").stream()}

def save(n, d): 
    db.collection("investors").document(n).set(d)

if 'user' not in st.session_state: st.session_state.user = None
if 'page' not in st.session_state: st.session_state.page = 'landing'
if 'is_boss' not in st.session_state: st.session_state.is_boss = False
if 'action_type' not in st.session_state: st.session_state.action_type = None

# ==========================================
# 3. APP NAVIGATION
# ==========================================
if st.session_state.user:
    # ---------------- USER DASHBOARD ----------------
    data = get_user_data(st.session_state.user)
    if not data: st.session_state.user = None; st.rerun()
    
    wallet = float(data.get('wallet', 0.0))
    ph_now = datetime.now() + timedelta(hours=8)
    req_id = ph_now.strftime("%f")

    # Claim/Pull Logic
    qp = st.query_params
    if "act" in qp:
        act_type = qp["act"]; idx = int(qp["idx"])
        item = data['inv'][idx]
        roi_total = item['amount'] * 0.20
        current_cycle_id = datetime.fromisoformat(item['start_time']).strftime("%Y%m%d%H")
        if act_type == "claim" and item.get('last_claim_id') != current_cycle_id:
            data['wallet'] += roi_total
            item['start_time'] = ph_now.isoformat(); item['last_claim_id'] = current_cycle_id
            save(st.session_state.user, data)
        elif act_type == "pull":
            data['wallet'] += (item['amount'] + roi_total)
            data['inv'].pop(idx); save(st.session_state.user, data)
        st.query_params.clear(); st.rerun()

    st.markdown(f"<div class='balance-box'><h3>AVAILABLE BALANCE</h3><h1>₱{max(0.0, wallet):,.2f}</h1></div>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📥 DEPOSIT"): st.session_state.action_type = "DEPOSIT"
    with c2:
        if st.button("📤 WITHDRAW"): st.session_state.action_type = "WITHDRAW"
    with c3:
        if st.button("🔄 REINVEST"): st.session_state.action_type = "REINVEST"

    # Action Forms
    if st.session_state.action_type in ["DEPOSIT", "WITHDRAW", "REINVEST"]:
        with st.form("action_form"):
            amt = st.number_input("Amount", 1000.0)
            if st.form_submit_button("SUBMIT"):
                if st.session_state.action_type != "DEPOSIT" and amt > wallet: st.error("Insufficient Balance")
                else:
                    if st.session_state.action_type != "DEPOSIT": data['wallet'] -= amt
                    data.setdefault('pending_actions', []).append({"type":st.session_state.action_type, "amount":amt, "request_id":req_id})
                    data.setdefault('history', []).append({"type":st.session_state.action_type, "amount":amt, "status":"PENDING", "request_id":req_id, "date":ph_now.strftime("%Y-%m-%d")})
                    save(st.session_state.user, data); st.session_state.action_type=None; st.rerun()

    # Running Capitals
    st.subheader("🚀 RUNNING CAPITALS")
    for idx, item in enumerate(list(data.get('inv', []))):
        start_dt = datetime.fromisoformat(item['start_time'])
        end_dt = start_dt + timedelta(days=7); pull_out_end = end_dt + timedelta(hours=1)
        if ph_now > pull_out_end:
            item['start_time'] = ph_now.isoformat(); save(st.session_state.user, data); st.rerun()
        elapsed = (ph_now - start_dt).total_seconds()
        roi_total = item['amount'] * 0.20; live_profit = min(1.0, elapsed / 604800) * roi_total
        is_op = end_dt <= ph_now <= pull_out_end; dis_class = "" if is_op else "disabled"
        st.markdown(f"""
<div style="background-color: #1c2128; padding: 15px; border-radius: 10px; border-left: 5px solid #00ff88; margin-bottom: 10px; border: 1px solid #30363d;">
    <div style="display: flex; justify-content: space-between;"><span style="color:#8b949e; font-weight:bold;">CAPITAL: ₱{item['amount']:,.2f}</span><span style="color:#00ff88; font-weight:bold;">ROI: ₱{roi_total:,.2f}</span></div>
    <div style="margin-top:5px; color:white; font-size:0.9em;">LIVE PROFIT: ₱{live_profit:,.2f}</div>
    <a href="/?act=claim&idx={idx}" target="_self" class="nested-btn {dis_class}">press here to CLAIM INTEREST on schedule</a>
    <a href="/?act=pull&idx={idx}" target="_self" class="nested-btn {dis_class}">press to PULL OUT CAPITAL on schedule</a>
</div>""", unsafe_allow_html=True)
    
    if st.button("LOGOUT"): st.session_state.user = None; st.rerun()

elif st.session_state.page == "admin" and st.session_state.is_boss:
    # ---------------- ADMIN COMMAND CENTER ----------------
    st.title("👑 ADMIN COMMAND CENTER")
    if st.button("EXIT ADMIN"): st.session_state.page = "landing"; st.rerun()
    reg = load_reg(); t1, t2, t3 = st.tabs(["📥 APPROVALS", "👥 MEMBERS", "📜 HISTORY"])
    
    with t1:
        for u, u_d in reg.items():
            for idx, act in enumerate(list(u_d.get('pending_actions', []))):
                with st.expander(f"{act['type']} - {u} (₱{act['amount']:,.0f})"):
                    col1, col2 = st.columns(2)
                    if col1.button("APPROVE", key=f"ap_{u}_{idx}"):
                        ref = db.collection("investors").document(u)
                        @firestore.transactional
                        def _app(transaction, r):
                            s = r.get(transaction=transaction).to_dict()
                            if act['type'] == "DEPOSIT" and not s.get('has_deposited'):
                                inv = s.get('ref_by', 'OFFICIAL')
                                if inv in reg: db.collection("investors").document(inv).update({"wallet": firestore.Increment(act['amount'] * 0.20)})
                                s['has_deposited'] = True
                            if act['type'] in ["DEPOSIT", "REINVEST"]:
                                s.setdefault('inv', []).append({"amount": act['amount'], "start_time": (datetime.now()+timedelta(hours=8)).isoformat()})
                            if act['type'] == "REF_CLAIM": s['wallet'] = s.get('wallet', 0) + act['amount']
                            for h in s.get('history', []):
                                if h.get('request_id') == act.get('request_id'): h['status'] = "CONFIRMED"
                            s['pending_actions'].pop(idx); transaction.set(r, s)
                        _app(db.transaction(), ref); st.rerun()
                    if col2.button("REJECT", key=f"rj_{u}_{idx}"):
                        if act['type'] in ["WITHDRAW", "REINVEST"]: u_d['wallet'] += act['amount']
                        u_d['pending_actions'].pop(idx); save(u, u_d); st.rerun()

elif st.session_state.page == "auth":
    t1, t2 = st.tabs(["LOGIN", "REGISTER"])
    with t1:
        u = st.text_input("NAME", key="l_u").upper().strip()
        p = st.text_input("PIN", type="password", key="l_p")
        if st.button("GO", key="l_b"):
            rd = get_user_data(u)
            if rd and str(rd.get('pin')) == p: st.session_state.user = u; st.rerun()
            else: st.error("Invalid Login")
    with t2:
        nu = st.text_input("Full Name (First, Middle, Last Name)", key="r_u").upper().strip()
        np = st.text_input("6-Digit PIN", type="password", max_chars=6, key="r_p")
        if st.button("CREATE", key="r_b"):
            save(nu, {"pin":np, "wallet":0.0, "ref_by":"OFFICIAL", "inv":[], "history":[], "pending_actions":[], "has_deposited":False})
            st.success("Success!"); time.sleep(1); st.session_state.page="auth"; st.rerun()

else:
    # ---------------- LANDING PAGE ----------------
    st.markdown("""
<div style="background: linear-gradient(135deg, #1e222d 0%, #0e1117 100%); padding: 25px; border-radius: 20px; border: 2px solid #00ff88; margin-bottom: 25px;">
<h1 style="color: #00ff88; font-size: 1.8rem; text-align: center; margin-bottom: 5px;">FORCE YOUR MONEY TO WORK</h1>
<p style="text-align: center; color: #8b949e; font-size: 1rem; margin-bottom: 20px;">Stop letting your savings lose value. Movement is profit.</p>
<div style="background: #1c2128; padding: 15px; border-radius: 12px; border-left: 3px solid #00ff88; margin-bottom: 10px;">
<h4 style="margin: 0; color: #ffffff; font-size: 0.9rem;">20% WEEKLY VELOCITY</h4>
<p style="margin: 5px 0 0 0; color: #8b949e; font-size: 0.8rem;">While traditional stocks grow 10% a year, our engine executes 20% growth in just 7 days.</p>
</div>
</div>""", unsafe_allow_html=True)
    if st.button("🚀 TAP HERE TO JOIN THE COMMUNITY NOW", use_container_width=True, key="join_b"): st.session_state.page = "auth"; st.rerun()
    if st.button(".", key="secret_dot"): 
        boss_pass = st.text_input("Execution Error", type="password")
        if boss_pass == "0102030405": st.session_state.is_boss = True; st.session_state.page = "admin"; st.rerun()
    
