u_login = "" 
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
/* 1. APP BASE */
header, [data-testid="stToolbar"], footer { visibility: hidden !important; }
.stApp { background-color: #0e1117 !important; }

/* 2. THE YELLOW JOIN BUTTON (FORCED) */
.landing-page-only div.stButton > button {
    background-color: #ffcc00 !important;
    color: #000000 !important;
    height: 60px !important;
    width: 100% !important;
    border: 2px solid #ffffff !important;
    border-radius: 12px !important;
    font-weight: 900 !important;
    opacity: 1 !important;
}

/* 3. THE SECRET DOT (TOTALLY STRIPPED) */
/* This targets the button specifically to remove that box in your screenshot */
div.stButton > button:has(p:contains(".")) {
    background-color: transparent !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: #333 !important; /* Makes the dot very dim */
    min-height: 0 !important;
    width: 30px !important;
    margin-top: 20px !important;
}

/* 4. DASHBOARD BUTTONS (GREEN BOXES) */
[data-testid="column"] div.stButton > button {
    background-color: #1c2128 !important;
    color: #00ff88 !important;
    border: 2px solid #00ff88 !important;
    font-weight: bold !important;
}

/* 5. THE TEXT FIX (CRITICAL) */
/* This ensures the text 'TAP HERE' is black and visible */
.landing-page-only div.stButton > button p {
    color: #000000 !important;
    font-weight: 900 !important;
}

/* This ensures dashboard button text is green */
[data-testid="column"] div.stButton > button p {
    color: #00ff88 !important;
}
</style>


""", unsafe_allow_html=True)  # <--- ADD THIS LINE HERE

# ==========================================
# 2. DATABASE & STATE MANAGEMENT
# ==========================================
if 'user' not in st.session_state: st.session_state.user = None
if 'page' not in st.session_state: st.session_state.page = 'landing'
if 'is_boss' not in st.session_state: st.session_state.is_boss = False
if 'action_type' not in st.session_state: st.session_state.action_type = None

if "ref" in st.query_params:
    st.session_state["captured_ref"] = st.query_params["ref"].replace("+", " ").upper().strip()

if "ref" in st.query_params:
    st.session_state["captured_ref"] = st.query_params["ref"].replace("+", " ").upper().strip()

# ==========================================
# 3. USER DASHBOARD
# ==========================================
# 1. INITIALIZE ALL STATE VARIABLES
if 'user' not in st.session_state: st.session_state.user = None
if 'page' not in st.session_state: st.session_state.page = 'landing'
if 'is_boss' not in st.session_state: st.session_state.is_boss = False
if 'action_type' not in st.session_state: st.session_state.action_type = None

# 2. THE ANTI-CRASH LINE (PRE-DEFINING VARIABLES)
u_login = "" 
data = {}

# 3. CAPTURE REFERRAL & LOGIN
if "ref" in st.query_params:
    st.session_state["captured_ref"] = st.query_params["ref"].replace("+", " ").upper().strip()

# 4. FETCH LOGGED-IN DATA SAFELY
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
        st.query_params.clear()
        st.rerun()

    st.markdown(f"""
<div class='balance-box'>
    <h3>AVAILABLE BALANCE</h3>
    <h1>PHP {round(wallet, 2)}</h1>
</div>
""", unsafe_allow_html=True)

    
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("DEPOSIT"): st.session_state.action_type = "DEPOSIT CAPITAL"
    with c2:
        if st.button("WITHDRAW"): st.session_state.action_type = "WITHDRAW BALANCE"
    with c3:
        if st.button("REINVEST"): st.session_state.action_type = "REINVEST"

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
                    user_ref = db.collection("investors").document(st.session_state.user)
                    @firestore.transactional
                    def exec_withdraw(transaction, ref):
                        snap = ref.get(transaction=transaction).to_dict()
                        curr_w = float(snap.get('wallet', 0))
                        if curr_w >= amt_w:
                            new_bal = max(0.0, curr_w - amt_w)
                            pends = snap.get('pending_actions', [])
                            pends.append({"type":"WITHDRAW", "amount":amt_w, "request_id":req_id, "details":bank})
                            hist = snap.get('history', [])
                            hist.append({"type":"WITHDRAW", "amount":amt_w, "status":"PENDING", "request_id":req_id, "date":ph_now.strftime("%Y-%m-%d")})
                            transaction.update(ref, {"wallet": new_bal, "pending_actions": pends, "history": hist})
                            return True
                        return False
                    
                    if exec_withdraw(db.transaction(), user_ref):
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
    u_ref_encoded = st.session_state.user.replace(' ', '%20')
    reflink = base_url + "?ref=" + u_ref_encoded
    st.text_input("Link", value=reflink, label_visibility="collapsed")
    
    copy_js = f"""
<script>
async function copyRef() {{
    try {{
        await navigator.clipboard.writeText('{reflink}');
        alert('Referral Link Copied!');
    }} catch (err) {{
        const el = document.createElement('textarea');
        el.value = '{reflink}';
        document.body.appendChild(el); el.select();
        document.execCommand('copy');
        document.body.removeChild(el); alert('Referral Link Copied!');
    }}
}}
</script>
<button onclick="copyRef()" style="width: 100%; background-color: #1c2128; color: #00ff88; border: 1px solid #00ff88; padding: 10px; border-radius: 8px; cursor: pointer; font-weight: bold;">COPY REFERRAL LINK</button>
"""
    st.components.v1.html(copy_js, height=60)

    # COMPACT REFERRAL LIST
    st.markdown("<h4 style='margin-bottom:5px;'>👥 My Referrals</h4>", unsafe_allow_html=True)
    reg_ref = load_reg()
    my_refs = [name for name, info in reg_ref.items() if info.get('ref_by') == st.session_state.user]
    claimed_list = data.get('claimed_refs', [])

    if not my_refs:
        st.info("No referrals yet.")
    else:
        st.markdown("<div style='background:#1c2128; border-radius:10px; border:1px solid #30363d; overflow:hidden;'>", unsafe_allow_html=True)
        for ref_name in my_refs:
            ref_data = reg_ref[ref_name]
            ref_invest = ref_data.get('inv', [])
            f_dep = float(ref_invest[0]['amount']) if ref_invest else 0.0
            comm = f_dep * 0.20
            
            st.markdown(f"""
            <div style="padding: 10px; border-bottom: 1px solid #30363d; display: flex; flex-direction: column; gap: 4px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 13px; font-weight: bold; color: white;">{ref_name}</span>
                    <span style="font-size: 12px; color: #00ff88; font-weight: bold;">+PHP {int(comm)}</span>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    st.write(f'<span style="font-size: 11px; color: #8b949e;">1st Dep: PHP ' + str(int(f_dep)) + '</span>', unsafe_allow_html=True)
                    <span style="font-size: 10px; font-style: italic; color: #8b949e;">{"Sent to Admin" if ref_name in claimed_list else "Waiting Deposit" if f_dep == 0 else "Ready"}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if f_dep > 0 and ref_name not in claimed_list:
                if st.button(f"CLAIM COMMISSION ({ref_name})", key=f"claim_{ref_name}"):
                    data.setdefault('pending_actions', []).append({"type":"REF_CLAIM", "amount":comm, "request_id":f"REF_{ref_name}"})
                    data.setdefault('history', []).append({"type":"COMMISSION", "amount":comm, "status":"PENDING", "request_id":f"REF_{ref_name}", "date":ph_now.strftime("%Y-%m-%d")})
                    data.setdefault('claimed_refs', []).append(ref_name)
                    save(st.session_state.user, data)
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
        
    st.subheader("RUNNING CAPITALS")
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
        dis_class = "" if is_op else "disabled"

        st.markdown(f"""
<div style="background-color: #1c2128; padding: 15px; border-radius: 10px; border-left: 5px solid #00ff88; margin-bottom: 10px; border-right: 1px solid #30363d; border-top: 1px solid #30363d; border-bottom: 1px solid #30363d;">
    <div style="display: flex; justify-content: space-between;">
        <<span style="color: #8b949e; font-weight: bold;">CAPITAL: \u20b1{item['amount']:,.2f}</span>
        <span style="color: #00ff88; font-weight: bold;">ROI: \u20b1{roi_total:,.2f}</span>
    </div>
    <div style="margin-top: 5px; color: white; font-size: 0.9em;">LIVE PROFIT: ₱{live_profit:,.2f}</div>
    <div style="color: #e3b341; font-size: 0.8em; margin-top: 10px; line-height: 1.3;">
          <b>STRICT 1-HOUR WINDOW:</b><br>
        Capital & Interest ready to pull out on:<br>
        <b>{end_dt.strftime('%Y-%m-%d %I:%M %p')}</b> until <b>{pull_out_end.strftime('%I:%M %p')}</b><br>
        <i style="color: #ff4b4b;">*Auto-reinvests after {pull_out_end.strftime('%I:%M %p')}</i>
    </div>
    <a href="/?act=claim&idx={idx}" target="_self" class="nested-btn {dis_class}">press here to CLAIM INTEREST on schedule</a>
    <a href="/?act=pull&idx={idx}" target="_self" class="nested-btn {dis_class}">press to PULL OUT CAPITAL on schedule</a>
</div>
""", unsafe_allow_html=True)

    st.subheader("My History")
    for h in reversed(data.get('history', [])):
        st.markdown(f"<p style='font-size:8px; margin:2px 0; color:#8b949e;'>• {h['type']} | ₱{h['amount']:,.2f} | <span style='color:#00ff88;'>{h['status']}</span></p>", unsafe_allow_html=True)
      # ==========================================
# 4. NAVIGATION & AUTH
# ==========================================
elif st.session_state.page == "boss_key":
    boss_pass = st.text_input("error execution (donot tap anything)", type="password", placeholder="...")
    if boss_pass:
        master_key = st.secrets.get("BOSS_KEY", "0102030405")
        if boss_pass == master_key:
            st.session_state.is_boss = True
            st.session_state.page = "admin"
            st.rerun()

elif st.session_state.page == "admin" and st.session_state.is_boss:
    st.title("ADMIN")
    if st.button("EXIT"): 
        st.session_state.is_boss = False
        st.session_state.page = "landing"
        st.rerun()
    reg = load_reg()
    t1, t2, t3 = st.tabs(["APPROVALS", "MEMBERS", "HISTORY"])
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
                            if act['type'] == "REF_CLAIM":
                                snap['wallet'] = snap.get('wallet', 0) + act['amount']
                            
                            for h in snap.get('history', []):
                                if h.get('request_id') == act.get('request_id'): h['status'] = "CONFIRMED"
                            
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

    with t3:
        try:
            reg = load_reg()
        except:
            reg = {}
            st.warning("Data loading... please wait.")

        for u_n, u_i in reg.items():
            u_h = u_i.get('history', [])
            if u_h:
                st.markdown(f"**Investor: {u_n}**")
                for h in reversed(u_h):
                    amt = h.get('amount', 0)
                    st.write(f"﹂ {h.get('type')} | PHP {int(amt)} | {h.get('status')}")
                st.markdown("---")

elif st.session_state.page == "auth":
    t1, t2 = st.tabs(["LOGIN", "REGISTER"])
    
    with t1:
        u_login = st.text_input("NAME").upper().strip()
        p_login = st.text_input("PIN", type="password")
        
        # Define r_data here so it exists before the button is clicked
        r_data = {}

        if st.button("ENTER ISMEX DASHBOARD", key="login_btn"):
            # Indented correctly to be 'inside' the button
            r_data = get_user_data(u_login)
            
            if r_data and str(r_data.get('pin')) == p_login:
                st.session_state.user = u_login
                st.session_state.page = "dashboard"
                st.rerun()
            else:
                st.error("Invalid Username or PIN")

    with t2:
        inv_val = st.session_state.get('captured_ref', 'OFFICIAL')
        inv_n = st.text_input("Invitor Name", value=inv_val).upper().strip()
        nu = st.text_input("Full Name (First, Middle, Last Name)").upper().strip()
        np = st.text_input("PIN (6 digits)", type="password", max_chars=6)
        np_confirm = st.text_input("Confirm PIN", type="password", max_chars=6)
        
        if st.button("CREATE"):
            if not nu:
                st.error("Please input your First, Middle, and Last name.")
            elif len(np) != 6:
                st.error("PIN must be exactly 6 digits.")
            elif np != np_confirm:
                st.error("PINs do not match. Please try again.")
            else:
                save(nu, {"pin":np, "wallet":0.0, "ref_by":inv_n, "inv":[], "history":[], "pending_actions":[], "has_deposited":False, "claimed_refs": []})
                st.success("Registration Successful! Please proceed to LOGIN now.")
                time.sleep(2)
                st.rerun()
else:
    # START THE YELLOW STYLE ZONE
    st.markdown('<div class="landing-page-only">', unsafe_allow_html=True)
    
    # YOUR ORIGINAL ADVERTISEMENT DESIGN
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1e222d 0%, #0e1117 100%); padding: 25px; border-radius: 20px; border: 2px solid #00ff88; margin-bottom: 25px;">
        <h1 style="color: #00ff88; font-size: 1.8rem; text-align: center; margin-bottom: 5px; line-height: 1.2;">FORCE YOUR MONEY TO WORK</h1>
        <p style="text-align: center; color: #8b949e; font-size: 1rem; margin-bottom: 20px;">Stop letting your savings lose value. Movement is profit.</p>
        <div style="background: #1c2128; padding: 15px; border-radius: 12px; border-left: 3px solid #00ff88; margin-bottom: 10px;">
            <h4 style="margin: 0; color: #ffffff; font-size: 0.9rem;">20% WEEKLY VELOCITY</h4>
            <p style="margin: 5px 0 0 0; color: #8b949e; font-size: 0.8rem;">While traditional stocks grow 10% a year, our engine executes 20% growth in just 7 days.</p>
        </div>
        <div style="background: #1c2128; padding: 15px; border-radius: 12px; border-left: 3px solid #00ff88; margin-bottom: 15px;">
            <h4 style="margin: 0; color: #ffffff; font-size: 0.9rem;">COMPOUNDING ROLLS</h4>
            <p style="margin: 5px 0 0 0; color: #8b949e; font-size: 0.8rem;">Reinvest your 7-day gains to turbocharge your wealth through exponential cycles.</p>
        </div>
        <div style="background: rgba(0, 255, 136, 0.1); padding: 15px; border-radius: 10px; text-align: center; border: 1px dashed #00ff88; margin-bottom: 10px;">
            <span style="color: #00ff88; font-weight: bold; font-size: 1.1rem;">⚡️ 20% ROI + 20% UNLIMITED DIVIDENDS</span><br>
            <span style="color: #ffffff; font-size: 0.75rem; letter-spacing: 0.5px; display: block; margin-top: 5px;">TRUSTED BY THOUSANDS OF INVESTORS LOCAL & INTERNATIONAL</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # THE YELLOW JOIN BUTTON
    if st.button("TAP HERE TO JOIN THE COMMUNITY NOW", use_container_width=True):
        st.session_state.page = "auth"
        st.rerun()
        
        # 1. Close the landing page styling
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 2. Add the physical gap
    st.markdown("<br>", unsafe_allow_html=True)

    # 3. The Secret Button (This will be unboxed by the CSS)
    if st.button(".", key="secret_boss"): 
        st.session_state.page = "boss_key"
        st.rerun()

        
