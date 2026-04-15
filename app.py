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
# 3. MAIN APP LOGIC
# ==========================================
if st.session_state.user:
    data = get_user_data(st.session_state.user)
    if not data: 
        st.session_state.user = None
        st.rerun()
    
    wallet = float(data.get('wallet', 0.0))
    ph_now = datetime.now() + timedelta(hours=8)
    req_id = ph_now.strftime("%f")

    qp = st.query_params
    if "act" in qp:
        act_type = qp["act"]; idx = int(qp["idx"])
        item = data['inv'][idx]
        roi_total = item['amount'] * 0.20
        current_cycle_id = datetime.fromisoformat(item['start_time']).strftime("%Y%m%d%H")
        last_claim = item.get('last_claim_id', "")
        if act_type == "claim" and last_claim != current_cycle_id:
            data['wallet'] += roi_total
            item['start_time'] = ph_now.isoformat()
            item['last_claim_id'] = current_cycle_id
            save(st.session_state.user, data)
        elif act_type == "pull" and last_claim != current_cycle_id:
            data['wallet'] += (item['amount'] + roi_total)
            data['inv'].pop(idx)
            save(st.session_state.user, data)
        st.query_params.clear(); st.rerun()

    st.markdown(f"<div class='balance-box'><h3>AVAILABLE BALANCE</h3><h1>₱{max(0.0, wallet):,.2f}</h1></div>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📥 DEPOSIT"): st.session_state.action_type = "DEPOSIT"
    with c2:
        if st.button("📤 WITHDRAW"): st.session_state.action_type = "WITHDRAW"
    with c3:
        if st.button("🔄 REINVEST"): st.session_state.action_type = "REINVEST"

    if st.button("LOGOUT"): 
        st.session_state.user = None; st.rerun()
        
    if st.session_state.action_type == "DEPOSIT":
        with st.form("d"):
            amt_d = st.number_input("Amount", 1000.0)
            st.file_uploader("Receipt", type=['jpg','png','jpeg'])
            if st.form_submit_button("SUBMIT"):
                data.setdefault('pending_actions', []).append({"type":"DEPOSIT", "amount":amt_d, "request_id":req_id})
                data.setdefault('history', []).append({"type":"DEPOSIT", "amount":amt_d, "status":"Waiting Approval", "request_id":req_id, "date":ph_now.strftime("%Y-%m-%d")})
                save(st.session_state.user, data); st.session_state.action_type=None; st.rerun()

    if st.session_state.action_type == "WITHDRAW":
        with st.form("w"):
            amt_w = st.number_input("Amount", 1000.0)
            bank = st.text_input("Bank name, Account name, Account#")
            if st.form_submit_button("SUBMIT"):
                if wallet >= amt_w:
                    user_ref = db.collection("investors").document(st.session_state.user)
                    @firestore.transactional
                    def exec_withdraw(transaction, ref):
                        snap = ref.get(transaction=transaction).to_dict()
                        if float(snap.get('wallet', 0)) >= amt_w:
                            snap['wallet'] -= amt_w
                            snap.setdefault('pending_actions', []).append({"type":"WITHDRAW", "amount":amt_w, "request_id":req_id, "details":bank})
                            snap.setdefault('history', []).append({"type":"WITHDRAW", "amount":amt_w, "status":"PENDING", "request_id":req_id, "date":ph_now.strftime("%Y-%m-%d")})
                            transaction.set(ref, snap); return True
                        return False
                    if exec_withdraw(db.transaction(), user_ref): st.rerun()
                else: st.error("Insufficient Balance!")

    if st.session_state.action_type == "REINVEST":
        with st.form("r"):
            amt_r = st.number_input("Reinvest Amount", 0.0, max_value=max(0.0, wallet))
            if st.form_submit_button("CONFIRM"):
                if wallet >= amt_r > 0:
                    data['wallet'] -= amt_r
                    data.setdefault('pending_actions', []).append({"type":"REINVEST", "amount":amt_r, "request_id":req_id})
                    data.setdefault('history', []).append({"type":"REINVEST", "amount":amt_r, "status":"PENDING", "request_id":req_id, "date":ph_now.strftime("%Y-%m-%d")})
                    save(st.session_state.user, data); st.session_state.action_type = None; st.rerun()

    st.markdown("<h4 style='margin-bottom:0px;'>🔗 My Referral Link</h4>", unsafe_allow_html=True)
    reflink = "https://unfacedinternational-dev.github.io/ismex-philippines/?ref=" + st.session_state.user.replace(' ', '%20')
    st.text_input("Link", value=reflink, label_visibility="collapsed")
    
    st.markdown("<h4 style='margin-bottom:5px;'>👥 My Referrals</h4>", unsafe_allow_html=True)
    reg_ref = load_reg()
    my_refs = [name for name, info in reg_ref.items() if info.get('ref_by') == st.session_state.user]
    claimed_list = data.get('claimed_refs', [])

    if not my_refs:
        st.info("No referrals yet.")
    else:
        for ref_name in my_refs:
            ref_data = reg_ref[ref_name]; ref_invest = ref_data.get('inv', [])
            f_dep = float(ref_invest[0]['amount']) if ref_invest else 0.0
            comm = f_dep * 0.20
            st.markdown(f"<div style='background:#1c2128; padding:10px; border:1px solid #30363d;'><b>{ref_name}</b> | Comm: ₱{comm:,.0f}</div>", unsafe_allow_html=True)
            if f_dep > 0 and ref_name not in claimed_list:
                if st.button(f"CLAIM COMMISSION ({ref_name})", key=f"claim_{ref_name}"):
                    data.setdefault('pending_actions', []).append({"type":"REF_CLAIM", "amount":comm, "request_id":f"REF_{ref_name}"})
                    data.setdefault('history', []).append({"type":"COMMISSION", "amount":comm, "status":"PENDING", "request_id":f"REF_{ref_name}", "date":ph_now.strftime("%Y-%m-%d")})
                    data.setdefault('claimed_refs', []).append(ref_name)
                    save(st.session_state.user, data); st.rerun()
        
    st.subheader("🚀 RUNNING CAPITALS")
    for idx, item in enumerate(list(data.get('inv', []))):
        start_dt = datetime.fromisoformat(item['start_time'])
        end_dt = start_dt + timedelta(days=7); pull_out_end = end_dt + timedelta(hours=1)
        if ph_now > pull_out_end:
            item['start_time'] = ph_now.isoformat(); save(st.session_state.user, data); st.rerun()
        elapsed = (ph_now - start_dt).total_seconds()
        progress = min(1.0, elapsed / 604800); roi_total = item['amount'] * 0.20; live_profit = progress * roi_total
        is_op = end_dt <= ph_now <= pull_out_end; dis_class = "" if is_op else "disabled"
        st.markdown(f"""
        <div style="background-color: #1c2128; padding: 15px; border-radius: 10px; border-left: 5px solid #00ff88; margin-bottom: 10px; border: 1px solid #30363d;">
            <div style="display: flex; justify-content: space-between;"><span style="color:#8b949e;">CAPITAL: ₱{item['amount']:,.2f}</span><span style="color:#00ff88;">ROI: ₱{roi_total:,.2f}</span></div>
            <div style="color:white; font-size:0.9em;">LIVE PROFIT: ₱{live_profit:,.2f}</div>
            <div style="color:#e3b341; font-size:0.8em; margin-top:10px;">⚠️ Ready on: {end_dt.strftime('%Y-%m-%d %I:%M %p')}</div>
            <a href="/?act=claim&idx={idx}" target="_self" class="nested-btn {dis_class}">CLAIM INTEREST</a>
            <a href="/?act=pull&idx={idx}" target="_self" class="nested-btn {dis_class}">PULL OUT CAPITAL</a>
        </div>
        """, unsafe_allow_html=True)

    st.subheader("📜 My History")
    for h in reversed(data.get('history', [])):
        st.markdown(f"<p style='font-size:10px; color:#8b949e;'>• {h['type']} | ₱{h['amount']:,.2f} | {h['status']}</p>", unsafe_allow_html=True)

elif st.session_state.page == "boss_key":
    boss_pass = st.text_input("Authentication", type="password", key="boss_in")
    if boss_pass == st.secrets.get("BOSS_KEY", "0102030405"):
        st.session_state.is_boss = True; st.session_state.page = "admin"; st.rerun()

elif st.session_state.page == "admin" and st.session_state.is_boss:
    st.title("👑 ADMIN")
    if st.button("EXIT"): st.session_state.page = "landing"; st.rerun()
    reg = load_reg(); t1, t2, t3 = st.tabs(["📥 APPROVALS", "👥 MEMBERS", "📜 HISTORY"])
    with t1:
        for u, u_d in reg.items():
            for idx, act in enumerate(list(u_d.get('pending_actions', []))):
                with st.expander(f"{act['type']} - {u}"):
                    if st.button("APPROVE", key=f"ap_{u}_{idx}"):
                        ref = db.collection("investors").document(u)
                        @firestore.transactional
                        def _app(transaction, r):
                            s = r.get(transaction=transaction).to_dict()
                            if act['type'] == "DEPOSIT" and not s.get('has_deposited'):
                                inv = s.get('ref_by', 'OFFICIAL')
                                if inv in reg: db.collection("investors").document(inv).update({"wallet": firestore.Increment(act['amount'] * 0.20)})
                                s['has_deposited'] = True
                            if act['type'] in ["DEPOSIT", "REINVEST"]: s.setdefault('inv', []).append({"amount": act['amount'], "start_time": (datetime.now()+timedelta(hours=8)).isoformat()})
                            if act['type'] == "REF_CLAIM": s['wallet'] = s.get('wallet', 0) + act['amount']
                            for h in s.get('history', []):
                                if h.get('request_id') == act.get('request_id'): h['status'] = "CONFIRMED"
                            s['pending_actions'].pop(idx); transaction.set(r, s)
                        _app(db.transaction(), ref); st.rerun()
    with t2: st.table([{"NAME": n, "WALLET": i.get('wallet'), "REF": i.get('ref_by')} for n, i in reg.items()])

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
        inv_n = st.text_input("Invitor", value=st.session_state.get('captured_ref', 'OFFICIAL'), key="r_i").upper().strip()
        nu = st.text_input("Full Name (First, Middle, Last)", key="r_u").upper().strip()
        np = st.text_input("PIN (6 digits)", type="password", max_chars=6, key="r_p1")
        np_c = st.text_input("Confirm PIN", type="password", max_chars=6, key="r_p2")
        if st.button("CREATE", key="r_b"):
            if not nu or len(np) != 6 or np != np_c: st.error("Check inputs")
            else:
                save(nu, {"pin":np, "wallet":0.0, "ref_by":inv_n, "inv":[], "history":[], "pending_actions":[], "has_deposited":False, "claimed_refs": []})
                st.success("Success! Please Login."); time.sleep(2); st.rerun()

else:
    st.markdown("""<div style="background: linear-gradient(135deg, #1e222d 0%, #0e1117 100%); padding: 25px; border-radius: 20px; border: 2px solid #00ff88; text-align: center;">
    <h1 style="color: #00ff88;">FORCE YOUR MONEY TO WORK</h1><p style="color: #8b949e;">Movement is profit.</p>
    <div style="background: rgba(0, 255, 136, 0.1); padding: 15px; border-radius: 10px; border: 1px dashed #00ff88;"><b>20% WEEKLY VELOCITY</b></div></div>""", unsafe_allow_html=True)
    if st.button("🚀 JOIN COMMUNITY", use_container_width=True): st.session_state.page = "auth"; st.rerun()
    if st.button(".", key="secret"): st.session_state.page = "boss_key"; st.rerun()
        # YOUR SECRET BOSS TRIGGER (The tiny dot)
    if st.button(".", key="secret_boss_trigger"): 
        st.session_state.page = "boss_key"
        st.rerun()
