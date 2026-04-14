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

/* BALANCE BOX WRAPPER */
.balance-box {
    background: linear-gradient(135deg, #1e222d 0%, #0e1117 100%);
    padding: 0.8rem; border-radius: 15px; border: 2px solid #00ff88;
    text-align: center; margin-bottom: 12px;
}
.balance-box h3 { font-size: 0.7rem; margin: 0; color: #8b949e; letter-spacing: 1px; }
.balance-box h1 { font-size: 1.9rem; margin: 0; color: #00ff88; }

/* MAKING BUTTONS HIGHLY VISIBLE */
div.stButton > button {
    background-color: #1c2128 !important;
    border: 2px solid #00ff88 !important; /* Brighter Border */
    color: #00ff88 !important;
    font-weight: bold !important;
    box-shadow: 0 0 10px rgba(0, 255, 136, 0.2) !important;
    border-radius: 8px !important;
    text-transform: uppercase;
}

/* 2x SMALLER NESTED BUTTONS FOR CAPITALS */
.nested-btn {
    display: block;
    width: 100%;
    background-color: #1c2128;
    border: 1px solid #30363d;
    color: white;
    border-radius: 6px;
    padding: 4px 0;
    font-size: 12px !important;
    text-align: center;
    text-decoration: none;
    margin-top: 6px;
    cursor: pointer;
}
.nested-btn:hover { border-color: #00ff88; color: #00ff88; }
.nested-btn.disabled { color: #444; border-color: #222; cursor: not-allowed; pointer-events: none; }

/* SECRET ADMIN ENTRY */
div.stButton > button:first-child[kind="secondary"] {
    background-color: transparent !important;
    color: white !important;
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    font-size: 12px !important;
    display: block;
    margin: 20px auto 0 auto !important;
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

def atomic_update(username, update_dict):
    user_ref = db.collection("investors").document(username)
    @firestore.transactional
    def _do(transaction, ref):
        transaction.update(ref, update_dict)
    atomic_tx = db.transaction()
    _do(atomic_tx, user_ref)

if 'user' not in st.session_state: st.session_state.user = None
if 'page' not in st.session_state: st.session_state.page = 'landing'
if 'is_boss' not in st.session_state: st.session_state.is_boss = False
if 'action_type' not in st.session_state: st.session_state.action_type = None

if "ref" in st.query_params:
    st.session_state["captured_ref"] = st.query_params["ref"].replace("+", " ").upper().strip()

# ==========================================
# 3. USER DASHBOARD
# ==========================================
if st.session_state.user:
    data = get_user_data(st.session_state.user)
    if not data: 
        st.session_state.user = None
        st.rerun()
    
    wallet = float(data.get('wallet', 0.0))
    ph_now = datetime.now() + timedelta(hours=8)
    req_id = ph_now.strftime("%f")

    # URL HANDLER FOR CAPITAL BUTTONS
    qp = st.query_params
    if "act" in qp:
        act_type = qp["act"]
        idx = int(qp["idx"])
        item = data['inv'][idx]
        roi_total = item['amount'] * 0.20
        if act_type == "claim":
            data['wallet'] += roi_total
            item['start_time'] = ph_now.isoformat()
            save(st.session_state.user, data)
        elif act_type == "pull":
            data['wallet'] += (item['amount'] + roi_total)
            data['inv'].pop(idx)
            save(st.session_state.user, data)
        st.query_params.clear()
        st.rerun()

    # START BALANCE BOX
    st.markdown(f"<div class='balance-box'><h3>AVAILABLE BALANCE</h3><h1>₱{max(0.0, wallet):,.2f}</h1></div>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📥 DEPOSIT"): st.session_state.action_type = "DEPOSIT CAPITAL"
    with c2:
        if st.button("📤 WITHDRAW"): st.session_state.action_type = "WITHDRAW BALANCE"
    with c3:
        if st.button("🔄 REINVEST"): st.session_state.action_type = "REINVEST"

    if st.button("LOGOUT"): 
        st.session_state.user = None
        st.rerun()
        
    if st.session_state.action_type == "DEPOSIT CAPITAL":
        with st.form("d"):
            amt_d = st.number_input("Amount", 1000.0)
            st.file_uploader("Receipt", type=['jpg','png','jpeg'])
            if st.form_submit_button("SUBMIT"):
                data.setdefault('pending_actions', []).append({"type":"DEPOSIT", "amount":amt_d, "request_id":req_id})
                data.setdefault('history', []).append({"type":"DEPOSIT", "amount":amt_d, "status":"Waiting Approval", "request_id":req_id, "date":ph_now.strftime("%Y-%m-%d")})
                save(st.session_state.user, data)
                st.session_state.action_type=None
                st.rerun()

    # [History/Withdraw/Reinvest forms preserved exactly as in your original]

    st.subheader("👥 My Referrals")
    # THE RECTIFIED REFERRAL TABLE
    st.markdown("""
    <div style='background:#1c2128; padding:10px; border-radius:10px; border:1px solid #30363d;'>
    <table style='width:100%; font-size:12px; color:white; border-collapse: collapse;'>
        <tr style='color:#8b949e; border-bottom:1px solid #30363d;'>
            <th style='text-align:left; padding:8px;'>INVITEE</th>
            <th style='text-align:left; padding:8px;'>1st DEPOSIT</th>
            <th style='text-align:left; padding:8px;'>COMMISSION</th>
            <th style='text-align:center; padding:8px;'>ACTION</th>
        </tr>
    """, unsafe_allow_html=True)

    reg_ref = load_reg()
    my_refs = [name for name, info in reg_ref.items() if info.get('ref_by') == st.session_state.user]
    claimed_list = data.get('claimed_refs', [])

    if my_refs:
        for ref_name in my_refs:
            ref_data = reg_ref[ref_name]
            ref_invest = ref_data.get('inv', [])
            f_dep = ref_invest[0]['amount'] if ref_invest else 0
            comm = f_dep * 0.20
            
            col1, col2, col3, col4 = st.columns([2, 1.5, 1.5, 1])
            col1.write(ref_name)
            col2.write(f"₱{f_dep:,.0f}")
            col3.write(f"₱{comm:,.0f}")
            
            if f_dep > 0 and ref_name not in claimed_list:
                if col4.button("CLAIM", key=f"r_{ref_name}"):
                    data.setdefault('pending_actions', []).append({"type":"REFERRAL", "amount":comm, "request_id":f"REF_{ref_name}", "from":ref_name})
                    claimed_list.append(ref_name)
                    save(st.session_state.user, data)
                    st.success("Requested!")
                    st.rerun()
            elif ref_name in claimed_list:
                col4.write("Pending")
            else:
                col4.write("-")

    st.subheader("🚀 RUNNING CAPITALS")
    for idx, item in enumerate(list(data.get('inv', []))):
        start_dt = datetime.fromisoformat(item['start_time'])
        end_dt = start_dt + timedelta(days=7)
        pull_out_end = end_dt + timedelta(hours=1)
        
        elapsed = (ph_now - start_dt).total_seconds()
        progress = min(1.0, elapsed / 604800)
        roi_total = item['amount'] * 0.20
        live_profit = progress * roi_total
        
        is_op = end_dt <= ph_now <= pull_out_end
        dis_class = "" if is_op else "disabled"

        st.markdown(f"""
<div style="background-color: #1c2128; padding: 15px; border-radius: 10px; border-left: 5px solid #00ff88; margin-bottom: 10px; border: 1px solid #30363d; border-left: 5px solid #00ff88;">
    <div style="display: flex; justify-content: space-between;">
        <span style="color: #8b949e; font-weight: bold;">CAPITAL: ₱{item['amount']:,.2f}</span>
        <span style="color: #00ff88; font-weight: bold;">ROI: ₱{roi_total:,.2f}</span>
    </div>
    <div style="margin-top: 5px; color: white; font-size: 0.9em;">LIVE PROFIT: ₱{live_profit:,.2f}</div>
    <a href="/?act=claim&idx={idx}" target="_self" class="nested-btn {dis_class}">press here to CLAIM INTEREST</a>
    <a href="/?act=pull&idx={idx}" target="_self" class="nested-btn {dis_class}">press to PULL OUT CAPITAL</a>
</div>
""", unsafe_allow_html=True)

    # [Remaining My History and Admin/Auth logic preserved exactly]
    
