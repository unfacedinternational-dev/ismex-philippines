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
.balance-box h1 { font-size: 1.6rem; margin: 0; color: #00ff88; }
.cap-card {
    background: #1c2128; padding: 15px; border-radius: 10px; 
    border-left: 5px solid #00ff88; margin-bottom: 10px;
}

/* 2x SMALLER BUTTONS FOR CLAIM/PULL OUT */
.small-btn {
    background-color: transparent !important;
    border: 1px solid #00ff88 !important;
    color: #00ff88 !important;
    border-radius: 5px !important;
    font-size: 9px !important;
    padding: 2px 5px !important;
    width: 100%;
    margin-top: 4px;
    cursor: pointer;
    text-transform: uppercase;
    font-weight: bold;
}
.small-btn:disabled {
    border-color: #30363d !important;
    color: #8b949e !important;
}

/* SECRET ADMIN ENTRY */
div.stButton > button:first-child[kind="secondary"] {
    background-color: transparent !important;
    color: white !important;
    border: none !important;
    padding: 0 !important;
    font-size: 12px !important;
    margin: 20px auto 0 auto !important;
    display: block;
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

    st.markdown(f"<div class='balance-box'><h3>AVAILABLE BALANCE</h3><h1>₱{max(0.0, wallet):,.2f}</h1></div>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    if c1.button("📥 DEPOSIT"): st.session_state.action_type = "DEPOSIT CAPITAL"
    if c2.button("📤 WITHDRAW"): st.session_state.action_type = "WITHDRAW BALANCE"
    if c3.button("🔄 REINVEST"): st.session_state.action_type = "REINVEST"

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

    if st.session_state.action_type == "WITHDRAW BALANCE":
        with st.form("w"):
            amt_w = st.number_input("Amount", min_value=1000.0, value=1000.0)
            bank = st.text_input("Bank name, Account name, Account#")
            if st.form_submit_button("SUBMIT"):
                if wallet >= amt_w:
                    new_w = max(0.0, wallet - amt_w)
                    pends = data.get('pending_actions', [])
                    pends.append({"type":"WITHDRAW", "amount":amt_w, "request_id":req_id, "details":bank})
                    hist = data.get('history', [])
                    hist.append({"type":"WITHDRAW", "amount":amt_w, "status":"PENDING", "request_id":req_id, "date":ph_now.strftime("%Y-%m-%d")})
                    atomic_update(st.session_state.user, {"wallet": new_w, "pending_actions": pends, "history": hist})
                    st.success("Submitted!")
                    time.sleep(1); st.session_state.action_type = None; st.rerun()
                else:
                    st.error(f"Insufficient Balance! (₱{wallet:,.2f})")

    if st.session_state.action_type == "REINVEST":
        with st.form("r"):
            amt_r = st.number_input("Reinvest Amount", 0.0, max_value=max(0.0, wallet))
            if st.form_submit_button("CONFIRM"):
                if wallet >= amt_r and amt_r > 0:
                    new_w = max(0.0, wallet - amt_r)
                    pends = data.get('pending_actions', [])
                    pends.append({"type":"REINVEST", "amount":amt_r, "request_id":req_id})
                    hist = data.get('history', [])
                    hist.append({"type":"REINVEST", "amount":amt_r, "status":"PENDING", "request_id":req_id, "date":ph_now.strftime("%Y-%m-%d")})
                    atomic_update(st.session_state.user, {"wallet": new_w, "pending_actions": pends, "history": hist})
                    st.session_state.action_type = None
                    st.rerun()

    st.markdown("<h4 style='margin-bottom:0px;'>🔗 My Referral Link</h4>", unsafe_allow_html=True)
    base_url = "https://unfacedinternational-dev.github.io/ismex-philippines/"
    u_ref = st.session_state.user.replace(' ', '%20')
    reflink = base_url + "?ref=" + u_ref
    st.text_input("Link", value=reflink, label_visibility="collapsed")
    
    copy_js = f"""
<script>
function copyRef() {{
    const el = document.createElement('textarea');
    el.value = '{reflink}';
    document.body.appendChild(el); el.select();
    document.execCommand('copy');
    document.body.removeChild(el); alert('Referral Link Copied!');
}}
</script>
<button onclick="copyRef()" style="width: 100%; background-color: #1c2128; color: #00ff88; border: 1px solid #00ff88; padding: 10px; border-radius: 8px; cursor: pointer; font-weight: bold;">📋 COPY REFERRAL LINK</button>
"""
    st.components.v1.html(copy_js, height=60)

    st.markdown("<h4 style='margin-bottom:5px;'>👥 My Referrals</h4>", unsafe_allow_html=True)
    h1, h2, h3 = st.columns([2, 1.5, 1.5])
    h1.caption("INVESTOR"); h2.caption("DEPOSIT"); h3.caption("ACTION")
                    
    reg_ref = load_reg()
    my_refs = [name for name, info in reg_ref.items() if info.get('ref_by') == st.session_state.user]
    claimed_list = data.get('claimed_refs', [])

    if my_refs:
        for ref_name in my_refs:
            ref_data = reg_ref[ref_name]
            ref_invest = ref_data.get('inv', [])
            f_dep = ref_invest[0]['amount'] if ref_invest else 0
            comm = f_dep * 0.20
            with st.container():
                col1, col2, col3 = st.columns([2, 1.5, 1.5])
                col1.markdown(f"<p style='font-size:12px; margin:0;'>{ref_name}</p>", unsafe_allow_html=True)
                col2.markdown(f"<p style='font-size:12px; margin:0;'>₱{f_dep:,.0f}</p>", unsafe_allow_html=True)
                
                if f_dep > 0 and ref_name not in claimed_list:
                    if col3.button(f"CLAIM ₱{comm:,.0f}", key=f"r_{ref_name}", use_container_width=True):
                        claimed_list.append(ref_name)
                        atomic_update(st.session_state.user, {
                            "wallet": firestore.Increment(comm),
                            "claimed_refs": claimed_list
                        })
                        st.success("Commission added!")
                        st.rerun()
                elif ref_name in claimed_list:
                    col3.markdown("<p style='font-size:10px; color:#00ff88; margin:0;'>Claimed ✓</p>", unsafe_allow_html=True)
                else:
                    col3.markdown("<p style='font-size:10px; color:gray; margin:0;'>No Dep.</p>", unsafe_allow_html=True)
            st.markdown("<hr style='margin:2px 0;'>", unsafe_allow_html=True)

    st.subheader("🚀 RUNNING CAPITALS")
    for idx, item in enumerate(list(data.get('inv', []))):
        start_dt = datetime.fromisoformat(item['start_time'])
        end_dt = start_dt + timedelta(days=7)
        pull_out_end = end_dt + timedelta(hours=1)
        
        if ph_now > pull_out_end:
            item['start_time'] = ph_now.isoformat()
            save(st.session_state.user, data)
            st.rerun()

        elapsed = (ph_now - start_dt).total_seconds()
        progress = min(1.0, elapsed / 604800)
        roi_total = item['amount'] * 0.20
        live_profit = progress * roi_total
        is_op = end_dt <= ph_now <= pull_out_end
        dis_attr = "" if is_op else "disabled"

        # FORCED INSIDE THE BOX + 2X SMALLER
        st.markdown(f"""
<div class="cap-card">
    <div style="display: flex; justify-content: space-between;">
        <span style="color: #8b949e; font-weight: bold; font-size: 0.9em;">CAPITAL: ₱{item['amount']:,.2f}</span>
        <span style="color: #00ff88; font-weight: bold; font-size: 0.9em;">ROI: ₱{roi_total:,.2f}</span>
    </div>
    <div style="margin-top: 5px; color: white; font-size: 0.8em;">LIVE PROFIT: ₱{live_profit:,.2f}</div>
    <div style="color: #e3b341; font-size: 0.7em; margin-top: 8px; line-height: 1.2;">
        ⚠️ <b>1-HOUR WINDOW:</b><br>
        Ready on: <b>{end_dt.strftime('%m-%d %I:%M %p')}</b>
    </div>
    <div style="margin-top: 10px;">
        <a href="/?act=claim&idx={idx}" target="_self"><button class="small-btn" {dis_attr}>CLAIM INTEREST</button></a>
        <a href="/?act=pull&idx={idx}" target="_self"><button class="small-btn" {dis_attr}>PULL OUT CAPITAL</button></a>
    </div>
</div>
""", unsafe_allow_html=True)

    # Logic for URL Actions
    q_params = st.query_params
    if "act" in q_params:
        idx_act = int(q_params["idx"])
        act_type = q_params["act"]
        inv_item = data['inv'][idx_act]
        inv_roi = inv_item['amount'] * 0.20
        
        if act_type == "claim":
            data['wallet'] += inv_roi
            inv_item['start_time'] = ph_now.isoformat()
        elif act_type == "pull":
            data['wallet'] += (inv_item['amount'] + inv_roi)
            data['inv'].pop(idx_act)
            
        save(st.session_state.user, data)
        st.query_params.clear()
        st.rerun()

    st.subheader("📜 My History")
    for h in reversed(data.get('history', [])):
        st.markdown(f"<p style='font-size:8px; margin:2px 0; color:#8b949e;'>• {h['type']} | ₱{h['amount']:,.2f} | <span style='color:#00ff88;'>{h['status']}</span></p>", unsafe_allow_html=True)

# ==========================================
# 4. NAVIGATION & AUTH
# ==========================================
elif st.session_state.page == "boss_key":
    boss_pass = st.text_input("error execution", type="password")
    if boss_pass:
        if boss_pass == st.secrets.get("BOSS_KEY", "0102030405"):
            st.session_state.is_boss = True
            st.session_state.page = "admin"
            st.rerun()

elif st.session_state.page == "admin" and st.session_state.is_boss:
    st.title("👑 ADMIN")
    if st.button("EXIT"): 
        st.session_state.is_boss = False
        st.session_state.page = "landing"
        st.rerun()
    reg = load_reg()
    t1, t2, t3 = st.tabs(["📥 APPROVALS", "👥 MEMBERS", "📜 HISTORY"])
    with t1:
        for u, u_data in reg.items():
            pend = u_data.get('pending_actions', [])
            for idx, act in enumerate(list(pend)):
                with st.expander(f"{act['type']} - {u}"):
                    if st.button("APPROVE", key=f"ap_{u}_{idx}"):
                        ph = datetime.now() + timedelta(hours=8)
                        user_ref = db.collection("investors").document(u)
                        @firestore.transactional
                        def proc(transaction, ref):
                            snap = ref.get(transaction=transaction).to_dict()
                            if act['type'] == "DEPOSIT" and not snap.get('has_deposited'):
                                inv_name = snap.get('ref_by', 'OFFICIAL')
                                if inv_name in reg:
                                    db.collection("investors").document(inv_name).update({"wallet": firestore.Increment(act['amount'] * 0.20)})
                                snap['has_deposited'] = True
                            if act['type'] in ["DEPOSIT", "REINVEST"]:
                                snap.setdefault('inv', []).append({"amount": act['amount'], "start_time": ph.isoformat()})
                            for h in snap.get('history', []):
                                if h.get('request_id') == act.get('request_id'): h['status'] = "CONFIRMED"
                            snap['pending_actions'].pop(idx)
                            transaction.set(ref, snap)
                        proc(db.transaction(), user_ref)
                        st.rerun()
    with t2:
        st.table([{"NAME": n, "WALLET": i.get('wallet')} for n, i in reg.items()])

elif st.session_state.page == "auth":
    t1, t2 = st.tabs(["LOGIN", "REGISTER"])
    with t1:
        u = st.text_input("NAME").upper().strip()
        p = st.text_input("PIN", type="password")
        if st.button("GO"):
            r_data = get_user_data(u)
            if r_data and str(r_data.get('pin')) == p: 
                st.session_state.user = u
                st.rerun()
    with t2:
        inv_n = st.session_state.get('captured_ref', 'OFFICIAL')
        st.write(f"Invitor: {inv_n}")
        nu = st.text_input("Full Name").upper().strip()
        np = st.text_input("PIN (6 digits)", type="password", max_chars=6)
        if st.button("CREATE"):
            if nu and len(np) == 6:
                save(nu, {"pin":np, "wallet":0.0, "ref_by":inv_n, "inv":[], "history":[], "pending_actions":[], "has_deposited":False, "claimed_refs": []})
                st.success("Done!"); time.sleep(1); st.rerun()

else:
    st.markdown("""
<div style="background: linear-gradient(135deg, #1e222d 0%, #0e1117 100%); padding: 25px; border-radius: 20px; border: 2px solid #00ff88; margin-bottom: 25px; text-align: center;">
<h1 style="color: #00ff88;">FORCE YOUR MONEY TO WORK</h1>
<p style="color: #8b949e;">20% ROI + 20% UNLIMITED DIVIDENDS</p>
</div>
""", unsafe_allow_html=True)
    if st.button("🚀 TAP HERE TO JOIN THE COMMUNITY NOW", use_container_width=True): 
        st.session_state.page = "auth"
        st.rerun()
    if st.button(".", key="secret_boss"): 
        st.session_state.page = "boss_key"
        st.rerun()
                    
