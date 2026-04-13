import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
from datetime import datetime, timedelta
import time

# ==========================================
# 1. UI CONFIGURATION (FULL CUSTOM CSS) - PRESERVED
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
    background: #1c2128; padding: 20px; border-radius: 15px;
    margin-bottom: 15px; border: 1px solid #30363d;
}
.hist-card {
    background: #1c2128; padding: 15px; border-radius: 12px;
    margin-bottom: 10px; border-left: 5px solid #00ff88;
}
.main .block-container { padding: 1rem !important; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. DATABASE & STATE MANAGEMENT (OPTIMIZED)
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
# 3. USER DASHBOARD & FULL TRANSACTION LOGIC
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

    # --- REFERRAL SECTION (PRESERVED) ---
    st.markdown("<h4 style='margin-bottom:0px;'>🔗 My Referral Link</h4>", unsafe_allow_html=True)
    base_url = "https://twee-gith.github.io/ismex-philippines-/"
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

        st.markdown(f"""
<div style="background-color: #1c2128; padding: 15px; border-radius: 10px; border-left: 5px solid #00ff88; margin-bottom: 10px;">
    <div style="display: flex; justify-content: space-between;">
        <span style="color: #8b949e; font-weight: bold;">CAPITAL: ₱{item['amount']:,.2f}</span>
        <span style="color: #00ff88; font-weight: bold;">ROI: ₱{roi_total:,.2f}</span>
    </div>
    <div style="margin-top: 5px; color: white; font-size: 0.9em;">LIVE PROFIT: ₱{live_profit:,.2f}</div>
    <div style="color: #e3b341; font-size: 0.8em; margin-top: 10px; line-height: 1.3;">
        ⚠️ <b>STRICT 1-HOUR WINDOW:</b><br>
        Capital & Interest ready to pull out on:<br>
        <b>{end_dt.strftime('%Y-%m-%d %I:%M %p')}</b> until <b>{pull_out_end.strftime('%I:%M %p')}</b><br>
        <i style="color: #ff4b4b;">*Auto-reinvests after {pull_out_end.strftime('%I:%M %p')}</i>
    </div>
</div>
""", unsafe_allow_html=True)
        
        is_op = end_dt <= ph_now <= pull_out_end
        ca, cb = st.columns(2)
        if ca.button("press here to CLAIM INTEREST", key=f"int_{idx}", disabled=not is_op, use_container_width=True):
            data['wallet'] += roi_total
            item['start_time'] = ph_now.isoformat()
            save(st.session_state.user, data)
            st.rerun()
        if cb.button("press here to PULL OUT CAPITAL", key=f"pull_{idx}", disabled=not is_op, use_container_width=True):
            data['wallet'] += (item['amount'] + roi_total)
            data['inv'].pop(idx)
            save(st.session_state.user, data)
            st.rerun()

    st.markdown("<h4 style='margin-top:20px;'>📜 My History</h4>", unsafe_allow_html=True)
    for h in reversed(data.get('history', [])):
        st.markdown(f"<p style='font-size:12px; margin:2px 0; color:#8b949e;'>• {h['type']} | ₱{h['amount']:,.2f} | <span style='color:#00ff88;'>{h['status']}</span></p>", unsafe_allow_html=True)

# ==========================================
# 4. NAVIGATION & AUTH (PRESERVED)
# ==========================================
elif st.session_state.page == "boss_key":
    boss_pass = st.text_input("Key", type="password", placeholder="Enter Key")
    if st.button("💃", use_container_width=True):
        master_key = st.secrets.get("BOSS_KEY", "0102030405")
        if boss_pass == master_key:
            st.session_state.is_boss = True
            st.session_state.page = "admin"
            st.rerun()
        else:
            st.session_state.page = "landing"
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
                with st.expander(f"{act['type']} - {u} (₱{act.get('amount',0):,.2f})"):
                    c1, c2 = st.columns(2)
                    if c1.button("APPROVE", key=f"ap_{u}_{idx}"):
                        ph = datetime.now() + timedelta(hours=8)
                        user_ref = db.collection("investors").document(u)
                        
                        @firestore.transactional
                        def process_approval(transaction, ref):
                            snap_doc = ref.get(transaction=transaction)
                            snap = snap_doc.to_dict()
                            
                            if act['type'] == "DEPOSIT" and not snap.get('has_deposited'):
                                inv_name = snap.get('ref_by', 'OFFICIAL')
                                if inv_name in reg:
                                    db.collection("investors").document(inv_name).update({"wallet": firestore.Increment(act['amount'] * 0.20)})
                                snap['has_deposited'] = True
                            
                            if act['type'] in ["DEPOSIT", "REINVEST"]:
                                snap.setdefault('inv', []).append({"amount": act['amount'], "start_time": ph.isoformat()})
                            
                            for h in snap.get('history', []):
                                if h.get('request_id') == act.get('request_id'): 
                                    h['status'] = "CONFIRMED"
                            
                            snap['pending_actions'].pop(idx)
                            transaction.set(ref, snap)

                        tx = db.transaction()
                        process_approval(tx, user_ref)
                        st.rerun()
                        
                    if c2.button("REJECT", key=f"rj_{u}_{idx}"):
                        if act['type'] in ["WITHDRAW", "REINVEST"]: u_data['wallet'] += act['amount']
                        u_data['pending_actions'].pop(idx)
                        save(u, u_data)
                        st.rerun()
    with t2:
        st.table([{"NAME": n, "PIN": i.get('pin'), "WALLET": i.get('wallet'), "REF": i.get('ref_by')} for n, i in reg.items()])
    with t3:
        for u_n, u_i in reg.items():
            u_h = u_i.get('history', [])
            if u_h:
                st.markdown(f"**Investor: {u_n}**")
                for h in reversed(u_h): st.write(f"﹂ {h['type']} | ₱{h['amount']:,.2f} | {h['status']}")
                st.markdown("---")

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
    st.title("ISMEX PHILIPPINES")
    if st.button("🚀 ENTER ISMEX NOW", use_container_width=True): 
        st.session_state.page = "auth"
        st.rerun()
    if st.button("🔒"): 
        st.session_state.page = "boss_key"
        st.rerun()
                    
