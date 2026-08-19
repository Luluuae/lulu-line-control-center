
import streamlit as st
import sqlite3, hashlib, secrets, hmac, io, zipfile, re, os, tempfile
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
from database import connect as db_connect, is_postgres

DB = os.getenv("LLCC_DB_PATH", "lulu_line.db")

def configured_database_url():
    value = os.getenv("DATABASE_URL", "").strip()
    if value:
        return value
    try:
        return str(st.secrets.get("DATABASE_URL", "")).strip()
    except Exception:
        return ""

DATABASE_URL = configured_database_url()
COMPANY = "LULU LINE GENERAL CONTRACTING AND EQUIPMENT LLC-SPC"

st.set_page_config(
    page_title="Lulu Line Control Center",
    page_icon="icon-512.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

SESSION_TIMEOUT_MINUTES = 30
MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15
PASSWORD_MIN_LENGTH = 12

# -----------------------------
# Core database / security
# -----------------------------
def conn():
    return db_connect(DATABASE_URL, DB)

def hashpw(pw, salt=None, iterations=600000):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${h}"

def checkpw(pw, stored):
    try:
        if stored.startswith("pbkdf2_sha256$"):
            _, its, salt, expected = stored.split("$", 3)
            calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), int(its)).hex()
            return hmac.compare_digest(calc, expected)
        # Backward compatibility with the previous salt$hash format.
        salt, expected = stored.split("$", 1)
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200000).hex()
        return hmac.compare_digest(calc, expected)
    except Exception:
        return False

def password_policy_error(pw):
    if len(pw) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    if not re.search(r"[A-Z]", pw): return "Password needs at least one uppercase letter."
    if not re.search(r"[a-z]", pw): return "Password needs at least one lowercase letter."
    if not re.search(r"\d", pw): return "Password needs at least one number."
    if not re.search(r"[^A-Za-z0-9]", pw): return "Password needs at least one special character."
    return None

def add_col(c, table, col, ddl):
    cols = [r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")

def init():
    c = conn()
    c.executescript("""
    PRAGMA journal_mode=WAL;

    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY,
      username TEXT UNIQUE,
      name TEXT,
      role TEXT,
      password TEXT,
      active INTEGER DEFAULT 1,
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS settings(
      key TEXT PRIMARY KEY,
      value TEXT
    );

    CREATE TABLE IF NOT EXISTS requests(
      id INTEGER PRIMARY KEY,
      req_no TEXT UNIQUE,
      created_at TEXT,
      created_by TEXT,
      category TEXT,
      project TEXT,
      beneficiary TEXT,
      amount REAL,
      description TEXT,
      evidence TEXT,
      status TEXT,
      manager_decision TEXT,
      manager_by TEXT,
      updated_at TEXT,
      attachment_name TEXT,
      attachment_type TEXT,
      attachment_blob BLOB
    );

    CREATE TABLE IF NOT EXISTS partner_votes(
      id INTEGER PRIMARY KEY,
      request_id INTEGER,
      partner_username TEXT,
      vote TEXT,
      voted_at TEXT,
      UNIQUE(request_id, partner_username)
    );

    CREATE TABLE IF NOT EXISTS projects(
      id INTEGER PRIMARY KEY,
      code TEXT UNIQUE,
      name TEXT,
      client TEXT,
      contract_value REAL DEFAULT 0,
      budget REAL DEFAULT 0,
      billed REAL DEFAULT 0,
      received REAL DEFAULT 0,
      cost REAL DEFAULT 0,
      status TEXT DEFAULT 'Active',
      start_date TEXT,
      end_date TEXT,
      manager TEXT,
      notes TEXT
    );

    CREATE TABLE IF NOT EXISTS assets(
      id INTEGER PRIMARY KEY,
      asset_id TEXT UNIQUE,
      type TEXT,
      description TEXT,
      owner_type TEXT,
      owner_name TEXT,
      plate_serial TEXT,
      customer TEXT,
      monthly_rent REAL DEFAULT 0,
      fuel REAL DEFAULT 0,
      maintenance REAL DEFAULT 0,
      other_cost REAL DEFAULT 0,
      insurance_expiry TEXT,
      registration_expiry TEXT,
      status TEXT,
      notes TEXT
    );

    CREATE TABLE IF NOT EXISTS receivables(
      id INTEGER PRIMARY KEY,
      invoice_no TEXT UNIQUE,
      client TEXT,
      project TEXT,
      invoice_date TEXT,
      due_date TEXT,
      amount REAL,
      received REAL DEFAULT 0,
      status TEXT
    );

    CREATE TABLE IF NOT EXISTS receivable_payments(
      id INTEGER PRIMARY KEY,
      invoice_no TEXT,
      payment_date TEXT,
      amount REAL DEFAULT 0,
      payment_method TEXT,
      reference TEXT,
      attachment_name TEXT,
      attachment_type TEXT,
      attachment_blob BLOB,
      created_by TEXT,
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS manpower(
      id INTEGER PRIMARY KEY,
      employee_code TEXT UNIQUE,
      name TEXT,
      category TEXT,
      passport_no TEXT UNIQUE,
      mobile TEXT,
      nationality TEXT,
      recruitment_source TEXT,
      ol_issue_date TEXT,
      ol_signed_date TEXT,
      visa_status TEXT,
      visa_type TEXT,
      visa_no TEXT,
      visa_payer TEXT,
      flight_status TEXT,
      flight_date TEXT,
      arrival_date TEXT,
      flight_payer TEXT,
      commission REAL DEFAULT 0,
      commission_paid_by TEXT,
      employee_status TEXT,
      project TEXT,
      salary REAL DEFAULT 0,
      joining_date TEXT,
      notes TEXT,
      created_at TEXT,
      updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS employee_documents(
      id INTEGER PRIMARY KEY,
      employee_code TEXT,
      doc_type TEXT,
      doc_no TEXT,
      issue_date TEXT,
      expiry_date TEXT,
      file_name TEXT,
      file_type TEXT,
      file_blob BLOB,
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS accommodation(
      id INTEGER PRIMARY KEY,
      employee_code TEXT UNIQUE,
      camp_name TEXT,
      room_no TEXT,
      bed_no TEXT,
      checkin_date TEXT,
      checkout_date TEXT,
      monthly_cost REAL DEFAULT 0,
      status TEXT,
      notes TEXT
    );

    CREATE TABLE IF NOT EXISTS payroll(
      id INTEGER PRIMARY KEY,
      employee_code TEXT,
      pay_month TEXT,
      basic_salary REAL DEFAULT 0,
      overtime REAL DEFAULT 0,
      allowance REAL DEFAULT 0,
      deduction REAL DEFAULT 0,
      net_salary REAL DEFAULT 0,
      paid_amount REAL DEFAULT 0,
      paid_date TEXT,
      payment_ref TEXT,
      status TEXT,
      UNIQUE(employee_code,pay_month)
    );

    CREATE TABLE IF NOT EXISTS expenses(
      id INTEGER PRIMARY KEY,
      expense_no TEXT UNIQUE,
      expense_date TEXT,
      category TEXT,
      project TEXT,
      asset_id TEXT,
      employee_code TEXT,
      vendor TEXT,
      amount REAL,
      payment_method TEXT,
      reference TEXT,
      approved_request_no TEXT,
      attachment_name TEXT,
      attachment_type TEXT,
      attachment_blob BLOB,
      created_by TEXT,
      created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS audit(
      id INTEGER PRIMARY KEY,
      ts TEXT,
      username TEXT,
      action TEXT,
      entity TEXT,
      entity_id TEXT,
      detail TEXT
    );

    CREATE TABLE IF NOT EXISTS login_security(
      username TEXT PRIMARY KEY,
      failed_count INTEGER DEFAULT 0,
      locked_until TEXT,
      last_failed_at TEXT
    );
    """)

    # Migration safety for older live DB
    for table, items in {
        "users":[("must_change_password","INTEGER DEFAULT 0"),("last_password_change","TEXT"),("last_login","TEXT")],
        "requests":[("attachment_name","TEXT"),("attachment_type","TEXT"),("attachment_blob","BLOB")],
        "projects":[("start_date","TEXT"),("end_date","TEXT"),("manager","TEXT"),("notes","TEXT")],
        "assets":[("insurance_expiry","TEXT"),("registration_expiry","TEXT"),("notes","TEXT")],
        "manpower":[("project","TEXT"),("salary","REAL DEFAULT 0"),("joining_date","TEXT")],
        "receivables":[("vat_amount","REAL DEFAULT 0"),("attachment_name","TEXT"),("attachment_type","TEXT"),("attachment_blob","BLOB")]
    }.items():
        for col, ddl in items:
            add_col(c, table, col, ddl)

    bootstrap_pw = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    try:
        if not bootstrap_pw:
            bootstrap_pw = str(st.secrets.get("BOOTSTRAP_ADMIN_PASSWORD", ""))
    except Exception:
        pass
    if not c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        if bootstrap_pw and password_policy_error(bootstrap_pw) is None:
            c.execute(
                "INSERT INTO users(username,name,role,password,must_change_password,created_at) VALUES(?,?,?,?,1,?)",
                ("admin","System Administrator","Admin",hashpw(bootstrap_pw),datetime.now().isoformat())
            )

    # Safe first-login recovery: a changed deployment secret can reset only a
    # newly bootstrapped admin that has never successfully logged in.
    first_admin = c.execute("SELECT last_login FROM users WHERE username='admin'").fetchone()
    if first_admin and not first_admin["last_login"] and bootstrap_pw:
        c.execute("UPDATE users SET password=?,must_change_password=1 WHERE username='admin'",(hashpw(bootstrap_pw),))
        c.execute("DELETE FROM login_security WHERE username='admin'")

    c.execute("UPDATE users SET role='Admin' WHERE username='admin' AND name='System Administrator' AND role='Partner'")
    c.execute("UPDATE users SET role='Accountant' WHERE role='Accounts'")
    c.execute("UPDATE users SET must_change_password=1 WHERE username='admin' AND last_password_change IS NULL")
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('manager_limit','10000')")
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('partner_votes_required','1')")
    c.commit()
    c.close()

def audit(action, entity, eid, detail=""):
    c=conn()
    c.execute(
        "INSERT INTO audit(ts,username,action,entity,entity_id,detail) VALUES(?,?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), st.session_state.get("username","system"),
         action, entity, str(eid), detail)
    )
    c.commit(); c.close()

def setting(k, default=""):
    c=conn(); r=c.execute("SELECT value FROM settings WHERE key=?",(k,)).fetchone(); c.close()
    return r["value"] if r else default

def set_setting(k,v):
    c=conn()
    c.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (k,str(v))
    )
    c.commit(); c.close()
    audit("UPDATE_SETTING","settings",k,str(v))

def role():
    return st.session_state.get("role","")

def can(*roles):
    return role() in roles

def money(x):
    return f"AED {float(x or 0):,.2f}"

def _utcnow():
    return datetime.utcnow()

def _parse_dt(v):
    try: return datetime.fromisoformat(v) if v else None
    except Exception: return None

def check_session_security():
    if not st.session_state.get("logged"):
        return
    now=_utcnow()
    last=st.session_state.get("last_activity")
    if last and (now-last).total_seconds() > SESSION_TIMEOUT_MINUTES*60:
        try: audit("SESSION_TIMEOUT","user",st.session_state.get("username",""))
        except Exception: pass
        st.session_state.clear()
        st.warning("Session expired for security. Please log in again.")
        st.rerun()
    st.session_state.last_activity=now

def login_lock_info(username):
    c=conn(); r=c.execute("SELECT failed_count,locked_until FROM login_security WHERE username=?",(username,)).fetchone(); c.close()
    if not r: return 0,None
    return int(r["failed_count"] or 0), _parse_dt(r["locked_until"])

def record_failed_login(username):
    now=_utcnow(); count,locked=login_lock_info(username)
    count += 1
    lock_until = now + timedelta(minutes=LOCK_MINUTES) if count >= MAX_FAILED_LOGINS else None
    c=conn(); c.execute("INSERT INTO login_security(username,failed_count,locked_until,last_failed_at) VALUES(?,?,?,?) ON CONFLICT(username) DO UPDATE SET failed_count=excluded.failed_count,locked_until=excluded.locked_until,last_failed_at=excluded.last_failed_at",(username,count,lock_until.isoformat() if lock_until else None,now.isoformat())); c.commit(); c.close()
    return count,lock_until

def clear_failed_login(username):
    c=conn(); c.execute("DELETE FROM login_security WHERE username=?",(username,)); c.commit(); c.close()

def login():
    st.caption("🔐 LLCC Secure Access")
    st.title("Lulu Line Control Center")
    st.caption("Secure internal control • role-based access • audit trail")
    c=conn(); user_count=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]; c.close()
    if user_count == 0:
        st.error("Initial Admin setup required. In Streamlit App Settings → Secrets, add BOOTSTRAP_ADMIN_PASSWORD with a strong 12+ character password, then reboot the app.")
        st.stop()
    with st.form("login"):
        u=st.text_input("Username").strip()
        p=st.text_input("Password",type="password")
        ok=st.form_submit_button("Login",use_container_width=True)
    if ok:
        count, locked_until = login_lock_info(u)
        now=_utcnow()
        if locked_until and locked_until > now:
            mins=max(1,int((locked_until-now).total_seconds()//60)+1)
            st.error(f"Account temporarily locked after repeated failed logins. Try again in about {mins} minute(s).")
            return
        c=conn(); r=c.execute("SELECT * FROM users WHERE username=? AND active=1",(u,)).fetchone(); c.close()
        if r and checkpw(p,r["password"]):
            clear_failed_login(u)
            # Upgrade old password hashes after a successful login.
            if not r["password"].startswith("pbkdf2_sha256$"):
                c=conn(); c.execute("UPDATE users SET password=?,last_login=? WHERE username=?",(hashpw(p),datetime.now().isoformat(),u)); c.commit(); c.close()
            else:
                c=conn(); c.execute("UPDATE users SET last_login=? WHERE username=?",(datetime.now().isoformat(),u)); c.commit(); c.close()
            st.session_state.update(logged=True,username=r["username"],name=r["name"],role=r["role"],last_activity=_utcnow(),must_change_password=bool(r["must_change_password"]))
            audit("LOGIN","user",r["username"],f"role={r['role']}")
            st.rerun()
        count,lock_until=record_failed_login(u or "<blank>")
        try: audit("LOGIN_FAILED","user",u or "<blank>",f"attempt={count}")
        except Exception: pass
        if lock_until:
            st.error(f"Too many failed attempts. Login locked for {LOCK_MINUTES} minutes.")
        else:
            st.error(f"Invalid login. {MAX_FAILED_LOGINS-count} attempt(s) remaining before temporary lock.")

def employee_choices(active_only=False):
    c=conn()
    q="SELECT employee_code,name,category,passport_no,employee_status FROM manpower"
    if active_only:
        q += " WHERE employee_status='Arrived / Active'"
    q += " ORDER BY name,employee_code"
    rows=c.execute(q).fetchall()
    c.close()
    return rows

def employee_select(label="Employee", key=None, active_only=False):
    rows=employee_choices(active_only)
    if not rows:
        st.info("No manpower records available yet.")
        return None
    labels=[f"{r['employee_code']} — {r['name']} — {r['category']}" for r in rows]
    picked=st.selectbox(label, labels, key=key)
    idx=labels.index(picked)
    return rows[idx]

def approved_request_choices():
    c=conn()
    rows=c.execute("SELECT req_no,category,beneficiary,amount FROM requests WHERE status='Approved' ORDER BY id DESC").fetchall()
    c.close()
    return rows

def project_choices():
    c=conn(); rows=c.execute("SELECT code,name,client FROM projects ORDER BY code").fetchall(); c.close()
    return rows

def asset_choices():
    c=conn(); rows=c.execute("SELECT asset_id,description,plate_serial FROM assets ORDER BY asset_id").fetchall(); c.close()
    return rows

def make_backup_zip():
    c=conn()
    c.execute("PRAGMA wal_checkpoint(FULL)")
    tables=[r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        for t in tables:
            df=pd.read_sql_query(f'SELECT * FROM "{t}"',c)
            # Never export password hashes in CSV backup.
            if t=="users" and "password" in df.columns:
                df=df.drop(columns=["password"])
            # Large BLOB columns are intentionally excluded from CSV; raw DB backup is separate.
            blob_cols=[col for col in df.columns if col.endswith("_blob")]
            if blob_cols:
                df=df.drop(columns=blob_cols)
            z.writestr(f"{t}.csv",df.to_csv(index=False))
    c.close()
    bio.seek(0)
    return bio.getvalue()

MIGRATION_TABLES = [
    "users", "settings", "requests", "partner_votes", "projects", "assets",
    "receivables", "receivable_payments", "manpower", "employee_documents",
    "accommodation", "payroll", "expenses", "audit", "login_security",
]

def restore_sqlite_backup(uploaded_bytes):
    if not is_postgres(DATABASE_URL):
        raise RuntimeError("Managed PostgreSQL is not connected.")
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        tmp.write(uploaded_bytes)
        tmp.flush()
        src = sqlite3.connect(f"file:{tmp.name}?mode=ro", uri=True)
        src.row_factory = sqlite3.Row
        if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            src.close()
            raise ValueError("The uploaded SQLite backup failed its integrity check.")
        source_tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        dst = conn()
        try:
            business = [t for t in MIGRATION_TABLES if t not in {"users", "settings", "audit", "login_security"}]
            existing = sum(dst.execute(f'SELECT COUNT(*) AS n FROM "{t}"').fetchone()["n"] for t in business)
            if existing:
                raise ValueError("Restore stopped: the managed database already contains ERP records.")
            restored = {}
            for table in MIGRATION_TABLES:
                if table not in source_tables:
                    continue
                rows = src.execute(f'SELECT * FROM "{table}"').fetchall()
                if not rows:
                    restored[table] = 0
                    continue
                columns = list(rows[0].keys())
                # Audit IDs may already be in use by the new managed database;
                # let PostgreSQL assign fresh IDs so every old audit row survives.
                if table == "audit" and "id" in columns:
                    columns.remove("id")
                names = ",".join(f'"{col}"' for col in columns)
                marks = ",".join("?" for _ in columns)
                if table == "users":
                    # Preserve the current managed-database password and login
                    # security fields; restore identity and role metadata only.
                    conflict = (" ON CONFLICT(username) DO UPDATE SET name=excluded.name,"
                                "role=excluded.role,active=excluded.active")
                elif table == "settings":
                    conflict = " ON CONFLICT(key) DO UPDATE SET value=excluded.value"
                else:
                    conflict = " ON CONFLICT DO NOTHING"
                dst.executemany(
                    f'INSERT INTO "{table}" ({names}) VALUES ({marks}){conflict}',
                    [tuple(row[col] for col in columns) for row in rows],
                )
                restored[table] = len(rows)
            for table in MIGRATION_TABLES:
                cols = dst.execute(f'PRAGMA table_info({table})').fetchall()
                if any(col["name"] == "id" for col in cols):
                    dst.execute(
                        "SELECT setval(pg_get_serial_sequence(?, 'id'), "
                        f'COALESCE((SELECT MAX(id) FROM "{table}"), 1), true)',
                        (table,),
                    )
            dst.commit()
            return restored
        except Exception:
            dst.rollback()
            raise
        finally:
            dst.close()
            src.close()

def sqlite_backup_already_restored():
    c = conn()
    found = c.execute(
        "SELECT 1 FROM audit WHERE action='RESTORE' AND entity='database' LIMIT 1"
    ).fetchone()
    c.close()
    return bool(found)

# -----------------------------
# Dashboard
# -----------------------------

def dashboard():
    c=conn()
    req=pd.read_sql_query("SELECT * FROM requests",c)
    prj=pd.read_sql_query("SELECT * FROM projects",c)
    ast=pd.read_sql_query("SELECT * FROM assets",c)
    rec=pd.read_sql_query("SELECT * FROM receivables",c)
    man=pd.read_sql_query("SELECT * FROM manpower",c)
    pay=pd.read_sql_query("SELECT * FROM payroll",c)
    docs=pd.read_sql_query("SELECT * FROM employee_documents",c)
    exp=pd.read_sql_query("SELECT * FROM expenses",c)
    c.close()

    r=role()
    today=pd.Timestamp(date.today())
    alerts=[]

    if r in ["Admin","Partner","Manager"]:
        pending=0 if req.empty else len(req[req.status.str.contains("Pending",na=False)])
        total_rec=0 if rec.empty else float((rec.amount-rec.received).sum())
        proj_profit=0 if prj.empty else float((prj.billed-prj.cost).sum())
        fleet_profit=0 if ast.empty else float((ast.monthly_rent-ast.fuel-ast.maintenance-ast.other_cost).sum())
        a,b,c1,d=st.columns(4)
        a.metric("Pending Approvals",pending); b.metric("Receivable",money(total_rec)); c1.metric("Project Margin to Date",money(proj_profit)); d.metric("Fleet Monthly Net",money(fleet_profit))
    elif r=="Accountant":
        total_rec=0 if rec.empty else float((rec.amount-rec.received).sum())
        total_exp=0 if exp.empty else float(exp.amount.sum())
        unpaid=0 if pay.empty else len(pay[pay.status!="Paid"])
        mine=0 if req.empty else len(req[(req.created_by==st.session_state.username)&(req.status.str.contains("Pending",na=False))])
        a,b,c1,d=st.columns(4)
        a.metric("Receivable",money(total_rec)); b.metric("Expenses Recorded",money(total_exp)); c1.metric("Payroll Pending",unpaid); d.metric("My Pending Requests",mine)
    elif r=="PRO":
        visa_pending=0 if man.empty else int((man.visa_status=="Pending").sum())
        mine=0 if req.empty else len(req[(req.created_by==st.session_state.username)&(req.status.str.contains("Pending",na=False))])
        dsoon=0
        if not docs.empty:
            dt=pd.to_datetime(docs.expiry_date,errors="coerce")
            dsoon=int(((dt.notna()) & ((dt-today).dt.days.between(0,30))).sum())
        a,b,c1=st.columns(3); a.metric("Visa Pending",visa_pending); b.metric("Documents Expiring 30d",dsoon); c1.metric("My Pending Requests",mine)
    elif r=="HR":
        total=0 if man.empty else len(man); active=0 if man.empty else int((man.employee_status=="Arrived / Active").sum()); visa=0 if man.empty else int((man.visa_status=="Issued").sum())
        a,b,c1=st.columns(3); a.metric("Manpower Records",total); b.metric("Active",active); c1.metric("Visa Issued",visa)
    elif r=="Project":
        activep=0 if prj.empty else int((prj.status=="Active").sum()); totalp=0 if prj.empty else len(prj)
        a,b=st.columns(2); a.metric("Projects",totalp); b.metric("Active Projects",activep)
    elif r=="Fleet":
        total=0 if ast.empty else len(ast); rented=0 if ast.empty else int((ast.status=="Rented").sum())
        a,b=st.columns(2); a.metric("Fleet / Assets",total); b.metric("Rented",rented)

    if r in ["Admin","Partner","Manager","HR"]:
        st.subheader("Manpower Snapshot")
        total=0 if man.empty else len(man); signed=0 if man.empty else int(man.ol_signed_date.fillna("").ne("").sum()); visa=0 if man.empty else int((man.visa_status=="Issued").sum()); flight=0 if man.empty else int((man.flight_status=="Booked").sum()); active=0 if man.empty else int((man.employee_status=="Arrived / Active").sum())
        m1,m2,m3,m4,m5=st.columns(5); m1.metric("Total",total); m2.metric("Signed OL",signed); m3.metric("Visa Issued",visa); m4.metric("Flight Booked",flight); m5.metric("Active",active)

    st.subheader("Risk / Attention")
    if r in ["Admin","Partner","Manager","Accountant"] and not rec.empty:
        rec["due"]=pd.to_datetime(rec.due_date,errors="coerce")
        overdue=rec[(rec.amount>rec.received)&(rec.due<today)]
        if len(overdue): alerts.append(f"{len(overdue)} overdue receivable(s), outstanding {money((overdue.amount-overdue.received).sum())}.")
    if r in ["Admin","Partner","Manager"] and not req.empty:
        hi=req[(req.amount>float(setting("manager_limit","10000")))&(req.status.str.contains("Pending",na=False))]
        if len(hi): alerts.append(f"{len(hi)} high-value request(s) still pending partner control.")
    if r in ["Admin","Partner","Manager","Fleet"] and not ast.empty:
        for col,label in [("insurance_expiry","insurance"),("registration_expiry","registration")]:
            dt=pd.to_datetime(ast[col],errors="coerce"); soon=ast[(dt.notna()) & ((dt-today).dt.days.between(0,30))]
            if len(soon): alerts.append(f"{len(soon)} asset {label} expiry item(s) due within 30 days.")
    if r in ["Admin","Partner","Manager","HR","PRO"] and not man.empty:
        visa_pending=int((man.visa_status=="Pending").sum())
        if visa_pending: alerts.append(f"{visa_pending} manpower visa(s) pending.")
    if r in ["Admin","Partner","Manager","HR","PRO"] and not docs.empty:
        dt=pd.to_datetime(docs.expiry_date,errors="coerce"); expired=docs[dt.notna() & (dt<today)]; soon=docs[dt.notna() & ((dt-today).dt.days.between(0,30))]
        if len(expired): alerts.append(f"{len(expired)} employee document(s) expired.")
        if len(soon): alerts.append(f"{len(soon)} employee document(s) expire within 30 days.")
    if r in ["Admin","Partner","Manager","Accountant"] and not pay.empty:
        unpaid=pay[pay.status!="Paid"]
        if len(unpaid): alerts.append(f"{len(unpaid)} payroll record(s) not fully paid.")

    if alerts:
        for x in alerts: st.warning(x)
    else: st.success("No current rule-based exception detected.")


def new_request():
    st.subheader("New Request")
    all_cats=["Payment","Purchase","PRO / Government Fee","Vehicle / Machinery","Project Expense","Loan / Finance","Major Decision","Other"]
    if role()=="PRO": cats=["PRO / Government Fee"]
    elif role()=="Fleet": cats=["Vehicle / Machinery","Purchase","Other"]
    elif role()=="Project": cats=["Project Expense","Purchase","Other"]
    else: cats=all_cats

    with st.form("req"):
        cat=st.selectbox("Category",cats)
        project=st.text_input("Project / Cost Code")
        ben=st.text_input("Beneficiary / Vendor / Government Entity")
        amt=st.number_input("Amount (AED)",min_value=0.0,step=100.0)
        desc=st.text_area("Purpose / Description")
        ev=st.text_input("Evidence / Invoice / Reference")
        attachment=st.file_uploader("Attach Bill / Invoice / Photo / PDF",type=["pdf","jpg","jpeg","png","webp"])
        submit=st.form_submit_button("Submit Request",use_container_width=True)

    if submit:
        if amt<=0 or not desc.strip(): st.error("Amount and description are required."); return
        c=conn()
        dup=c.execute("SELECT id,req_no FROM requests WHERE beneficiary=? AND amount=? AND description=? AND status!='Rejected'",(ben.strip(),amt,desc.strip())).fetchone()
        if dup: c.close(); st.error(f"Possible duplicate blocked: matches {dup['req_no']}."); return
        n=c.execute("SELECT COALESCE(MAX(id),0)+1 n FROM requests").fetchone()["n"]
        no=f"LL-REQ-{datetime.now():%Y%m}-{n:05d}"; limit=float(setting("manager_limit","10000"))
        if cat=="PRO / Government Fee": status="Pending Manager Verification"
        elif amt<=limit and cat not in ["Loan / Finance","Major Decision","Vehicle / Machinery"]: status="Pending Manager Approval"
        else: status="Pending Manager Review + Partner Vote"
        c.execute("""INSERT INTO requests(req_no,created_at,created_by,category,project,beneficiary,amount,description,evidence,status,updated_at,attachment_name,attachment_type,attachment_blob) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (no,datetime.now().isoformat(timespec="seconds"),st.session_state.username,cat,project,ben,amt,desc,ev,status,datetime.now().isoformat(timespec="seconds"),attachment.name if attachment else None,attachment.type if attachment else None,attachment.getvalue() if attachment else None))
        rid=c.execute("SELECT last_insert_rowid() id").fetchone()["id"]; c.commit(); c.close(); audit("CREATE","request",rid,no); st.success(f"Created {no} — {status}")

    c=conn(); mine=pd.read_sql_query("SELECT req_no,created_at,category,beneficiary,amount,status FROM requests WHERE created_by=? ORDER BY id DESC LIMIT 25",c,params=(st.session_state.username,)); c.close()
    if len(mine): st.subheader("My Recent Requests"); st.dataframe(mine,use_container_width=True,hide_index=True)


def show_attachment(r,keyprefix):
    if r["attachment_blob"] and r["attachment_name"]:
        st.download_button(
            "Download Attachment",
            data=bytes(r["attachment_blob"]),
            file_name=r["attachment_name"],
            mime=r["attachment_type"] or "application/octet-stream",
            key=f"{keyprefix}_{r['id']}"
        )

def approvals():
    if not can("Admin","Partner","Manager"):
        st.error("You do not have approval access.")
        return

    c=conn()
    rows=c.execute("SELECT * FROM requests WHERE status LIKE 'Pending%' ORDER BY id DESC").fetchall()
    c.close()

    st.subheader("Pending Approvals")
    if not rows:
        st.success("Nothing pending.")
        return

    limit=float(setting("manager_limit","10000"))
    votes_required=int(float(setting("partner_votes_required","1")))

    for r in rows:
        with st.expander(f"{r['req_no']} • {r['category']} • {money(r['amount'])} • {r['status']}"):
            st.write(r["description"])
            st.caption(f"Created by: {r['created_by']} | Beneficiary: {r['beneficiary']} | Project: {r['project']} | Evidence: {r['evidence']}")
            show_attachment(r,"att")

            if role() in ["Manager","Admin"]:
                if st.button("Manager Approve / Verify",key=f"ma{r['id']}"):
                    needs_partner = (
                        r["amount"]>limit or
                        r["category"] in ["Loan / Finance","Major Decision","Vehicle / Machinery"] or
                        "Partner Vote" in r["status"]
                    )
                    ns="Pending Partner Vote" if needs_partner else "Approved"
                    c=conn()
                    c.execute(
                        "UPDATE requests SET manager_decision='Approved',manager_by=?,status=?,updated_at=? WHERE id=?",
                        (st.session_state.username,ns,datetime.now().isoformat(timespec="seconds"),r["id"])
                    )
                    c.commit(); c.close()
                    audit("MANAGER_APPROVE","request",r["id"],ns)
                    st.rerun()

                if st.button("Reject",key=f"mr{r['id']}"):
                    c=conn()
                    c.execute(
                        "UPDATE requests SET manager_decision='Rejected',manager_by=?,status='Rejected',updated_at=? WHERE id=?",
                        (st.session_state.username,datetime.now().isoformat(timespec="seconds"),r["id"])
                    )
                    c.commit(); c.close()
                    audit("MANAGER_REJECT","request",r["id"])
                    st.rerun()

            if role() in ["Partner","Admin"] and r["status"]=="Pending Partner Vote":
                c=conn()
                existing=c.execute("SELECT vote FROM partner_votes WHERE request_id=? AND partner_username=?",(r["id"],st.session_state.username)).fetchone()
                approved_votes=c.execute("SELECT COUNT(*) n FROM partner_votes WHERE request_id=? AND vote='Approve'",(r["id"],)).fetchone()["n"]
                rejected_votes=c.execute("SELECT COUNT(*) n FROM partner_votes WHERE request_id=? AND vote='Reject'",(r["id"],)).fetchone()["n"]
                c.close()

                st.write(f"Partner votes: Approve {approved_votes} / Required {votes_required} | Reject {rejected_votes}")
                if existing:
                    st.info(f"Your vote: {existing['vote']}")
                else:
                    x,y=st.columns(2)
                    if x.button("Vote Approve",key=f"pva{r['id']}"):
                        c=conn()
                        c.execute("INSERT INTO partner_votes(request_id,partner_username,vote,voted_at) VALUES(?,?,?,?)",
                                  (r["id"],st.session_state.username,"Approve",datetime.now().isoformat(timespec="seconds")))
                        new_count=c.execute("SELECT COUNT(*) n FROM partner_votes WHERE request_id=? AND vote='Approve'",(r["id"],)).fetchone()["n"]
                        if new_count>=votes_required:
                            c.execute("UPDATE requests SET status='Approved',updated_at=? WHERE id=?",(datetime.now().isoformat(timespec="seconds"),r["id"]))
                        c.commit(); c.close()
                        audit("PARTNER_VOTE_APPROVE","request",r["id"])
                        st.rerun()

                    if y.button("Vote Reject",key=f"pvr{r['id']}"):
                        c=conn()
                        c.execute("INSERT INTO partner_votes(request_id,partner_username,vote,voted_at) VALUES(?,?,?,?)",
                                  (r["id"],st.session_state.username,"Reject",datetime.now().isoformat(timespec="seconds")))
                        c.execute("UPDATE requests SET status='Rejected',updated_at=? WHERE id=?",(datetime.now().isoformat(timespec="seconds"),r["id"]))
                        c.commit(); c.close()
                        audit("PARTNER_VOTE_REJECT","request",r["id"])
                        st.rerun()

# -----------------------------
# Projects
# -----------------------------
def projects():
    st.subheader("Projects")
    if can("Admin","Partner","Manager","Project"):
        with st.expander("Add / Update Project"):
            with st.form("proj"):
                p1,p2,p3=st.columns(3)
                code=p1.text_input("Project Code")
                name=p2.text_input("Project Name")
                client=p3.text_input("Client")
                p4,p5,p6=st.columns(3)
                start=p4.date_input("Start Date",value=None)
                end=p5.date_input("Expected End Date",value=None)
                manager=p6.text_input("Project Manager")
                cv=st.number_input("Contract Value",0.0)
                budget=st.number_input("Budget",0.0)
                billed=st.number_input("Billed",0.0)
                received=st.number_input("Received",0.0)
                cost=st.number_input("Cost to Date",0.0)
                status=st.selectbox("Status",["Active","On Hold","Completed","Closed"])
                notes=st.text_area("Notes")
                go=st.form_submit_button("Save")
            if go and code:
                c=conn()
                c.execute(
                    """INSERT INTO projects(code,name,client,contract_value,budget,billed,received,cost,status,start_date,end_date,manager,notes)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(code) DO UPDATE SET
                       name=excluded.name,client=excluded.client,contract_value=excluded.contract_value,budget=excluded.budget,
                       billed=excluded.billed,received=excluded.received,cost=excluded.cost,status=excluded.status,
                       start_date=excluded.start_date,end_date=excluded.end_date,manager=excluded.manager,notes=excluded.notes""",
                    (code,name,client,cv,budget,billed,received,cost,status,str(start) if start else "",str(end) if end else "",manager,notes)
                )
                c.commit(); c.close()
                audit("UPSERT","project",code)
                st.rerun()

    c=conn(); df=pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC",c); c.close()
    if len(df):
        df["Profit_to_Date"]=df["billed"]-df["cost"]
        df["Outstanding"]=df["billed"]-df["received"]
        df["Budget_Variance"]=df["budget"]-df["cost"]
        st.dataframe(df,use_container_width=True,hide_index=True)
    else:
        st.info("No projects yet.")

# -----------------------------
# Fleet
# -----------------------------
def fleet():
    st.subheader("Fleet & Machinery")
    if can("Admin","Partner","Manager","Fleet"):
        with st.expander("Add / Update Asset"):
            with st.form("asset"):
                aid=st.text_input("Asset ID")
                typ=st.selectbox("Type",["Car","Pickup","Machinery","Equipment","Other"])
                desc=st.text_input("Description")
                own=st.selectbox("Ownership",["Company","Partner/Investor Personal"])
                owner=st.text_input("Owner Name (if personal)")
                ps=st.text_input("Plate / Serial")
                cust=st.text_input("Rented To / Customer")
                rent=st.number_input("Monthly Rental Income",0.0)
                fuel=st.number_input("Fuel",0.0)
                maint=st.number_input("Maintenance",0.0)
                other=st.number_input("Other Cost",0.0)
                insurance=st.date_input("Insurance Expiry",value=None)
                registration=st.date_input("Registration Expiry",value=None)
                status=st.selectbox("Status",["Available","Rented","In Use","Maintenance","Inactive"])
                notes=st.text_area("Notes")
                go=st.form_submit_button("Save")
            if go and aid:
                c=conn()
                c.execute(
                    """INSERT INTO assets(asset_id,type,description,owner_type,owner_name,plate_serial,customer,monthly_rent,fuel,maintenance,other_cost,insurance_expiry,registration_expiry,status,notes)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(asset_id) DO UPDATE SET
                       type=excluded.type,description=excluded.description,owner_type=excluded.owner_type,owner_name=excluded.owner_name,
                       plate_serial=excluded.plate_serial,customer=excluded.customer,monthly_rent=excluded.monthly_rent,fuel=excluded.fuel,
                       maintenance=excluded.maintenance,other_cost=excluded.other_cost,insurance_expiry=excluded.insurance_expiry,
                       registration_expiry=excluded.registration_expiry,status=excluded.status,notes=excluded.notes""",
                    (aid,typ,desc,own,owner,ps,cust,rent,fuel,maint,other,str(insurance) if insurance else "",str(registration) if registration else "",status,notes)
                )
                c.commit(); c.close()
                audit("UPSERT","asset",aid)
                st.rerun()

    c=conn(); df=pd.read_sql_query("SELECT * FROM assets ORDER BY id DESC",c); c.close()
    if len(df):
        df["Monthly_Net"]=df.monthly_rent-df.fuel-df.maintenance-df.other_cost
        st.dataframe(df,use_container_width=True,hide_index=True)
    else:
        st.info("No assets yet.")

# -----------------------------
# Manpower
# -----------------------------

def manpower():
    if not can("Admin","Partner","Manager","HR"):
        st.error("Manpower access restricted.")
        return

    st.subheader("Manpower Control")
    c=conn(); df=pd.read_sql_query("SELECT * FROM manpower ORDER BY id DESC",c); c.close()

    total=len(df)
    ol_issued=0 if df.empty else int(df.ol_issue_date.fillna("").ne("").sum())
    ol_signed=0 if df.empty else int(df.ol_signed_date.fillna("").ne("").sum())
    visa_issued=0 if df.empty else int((df.visa_status=="Issued").sum())
    flight_booked=0 if df.empty else int((df.flight_status=="Booked").sum())
    active=0 if df.empty else int((df.employee_status=="Arrived / Active").sum())

    a,b,c1,d,e=st.columns(5)
    a.metric("Total Records",total); b.metric("OL Issued",ol_issued); c1.metric("Signed OL",ol_signed); d.metric("Visa Issued",visa_issued); e.metric("Flight Booked",flight_booked)
    st.caption(f"Arrived / Active: {active}")

    mode=st.radio("Action",["➕ New Employee","✏️ Edit Existing","🔎 Search / View"],horizontal=True)

    selected=None
    defaults={}
    if mode=="✏️ Edit Existing":
        selected=employee_select("Select Employee to Edit",key="emp_edit_pick")
        if selected:
            c=conn()
            r=c.execute("SELECT * FROM manpower WHERE employee_code=?",(selected["employee_code"],)).fetchone()
            c.close()
            defaults=dict(r)

    if mode in ["➕ New Employee","✏️ Edit Existing"]:
        with st.form("manpower_form"):
            x1,x2,x3=st.columns(3)
            code=x1.text_input("Employee / Candidate Code",value=defaults.get("employee_code",""),disabled=(mode=="✏️ Edit Existing"))
            name=x2.text_input("Full Name",value=defaults.get("name",""))
            cats=["Helper","Mason","Carpenter","Steel Fixer","Scaffolder","Welder","Pipe Fitter","Piping Fitter","Fabricator","E&I Technician","Instrument Technician","Instrument Fitter","Electrical Technician","Driver","Other"]
            cat_default=defaults.get("category","Helper")
            category=x3.selectbox("Category",cats,index=cats.index(cat_default) if cat_default in cats else 0)

            y1,y2,y3=st.columns(3)
            passport=y1.text_input("Passport No.",value=defaults.get("passport_no",""))
            mobile=y2.text_input("Mobile",value=defaults.get("mobile",""))
            nationality=y3.text_input("Nationality",value=defaults.get("nationality",""))
            source=st.text_input("Recruitment Source / Agency",value=defaults.get("recruitment_source",""))
            project=st.text_input("Assigned Project / Client",value=defaults.get("project",""))
            salary=st.number_input("Monthly Salary (AED)",min_value=0.0,step=100.0,value=float(defaults.get("salary") or 0))

            def _d(v):
                try: return pd.to_datetime(v).date() if v else None
                except: return None

            joining=st.date_input("Joining Date",value=_d(defaults.get("joining_date")))
            z1,z2=st.columns(2)
            ol_issue=z1.date_input("Offer Letter Issue Date",value=_d(defaults.get("ol_issue_date")))
            ol_signed=z2.date_input("Signed Offer Letter Received Date",value=_d(defaults.get("ol_signed_date")))

            visa_opts=["Not Applied","Pending","Issued","Rejected","Cancelled"]
            visa_status=st.selectbox("Visa Status",visa_opts,index=visa_opts.index(defaults.get("visa_status","Not Applied")) if defaults.get("visa_status","Not Applied") in visa_opts else 0)
            visa_type_opts=["","Employment","Visit","E-Visa","Other"]
            vt=defaults.get("visa_type","")
            visa_type=st.selectbox("Visa Type",visa_type_opts,index=visa_type_opts.index(vt) if vt in visa_type_opts else 0)
            visa_no=st.text_input("Visa No. / UID / Reference",value=defaults.get("visa_no",""))
            payer_opts=["","Company","Employee / Self","Agency","Partner / Investor","Other"]
            vp=defaults.get("visa_payer","")
            visa_payer=st.selectbox("Visa Paid By",payer_opts,index=payer_opts.index(vp) if vp in payer_opts else 0)

            f1,f2,f3=st.columns(3)
            flight_opts=["Not Booked","Pending","Booked","Completed","Cancelled"]
            fs=defaults.get("flight_status","Not Booked")
            flight_status=f1.selectbox("Flight Status",flight_opts,index=flight_opts.index(fs) if fs in flight_opts else 0)
            flight_date=f2.date_input("Flight Date",value=_d(defaults.get("flight_date")))
            arrival_date=f3.date_input("Arrival Date",value=_d(defaults.get("arrival_date")))
            fp=defaults.get("flight_payer","")
            flight_payer=st.selectbox("Flight Paid By",payer_opts,index=payer_opts.index(fp) if fp in payer_opts else 0)

            q1,q2=st.columns(2)
            commission=q1.number_input("Recruitment Commission (AED)",min_value=0.0,step=100.0,value=float(defaults.get("commission") or 0))
            cp=defaults.get("commission_paid_by","")
            commission_paid_by=q2.selectbox("Commission Paid By",payer_opts,index=payer_opts.index(cp) if cp in payer_opts else 0)

            status_opts=["Candidate","OL Issued","OL Signed","Visa Process","Ready to Travel","Arrived / Active","On Hold","Rejected","Left / Inactive"]
            es=defaults.get("employee_status","Candidate")
            emp_status=st.selectbox("Employee Status",status_opts,index=status_opts.index(es) if es in status_opts else 0)
            notes=st.text_area("Notes",value=defaults.get("notes",""))
            save=st.form_submit_button("Save Record",use_container_width=True)

        if save:
            final_code = defaults.get("employee_code","") if mode=="✏️ Edit Existing" else code.strip()
            passport=passport.strip().upper(); name=name.strip()
            if not final_code or not name or not passport:
                st.error("Code, Full Name and Passport No. are required.")
            else:
                c=conn()
                dup=c.execute("SELECT employee_code,name FROM manpower WHERE passport_no=? AND employee_code<>?",(passport,final_code)).fetchone()
                if dup:
                    c.close()
                    st.error(f"Duplicate passport blocked. Already used for {dup['employee_code']} - {dup['name']}.")
                else:
                    now=datetime.now().isoformat(timespec="seconds")
                    try:
                        c.execute(
                            """INSERT INTO manpower(employee_code,name,category,passport_no,mobile,nationality,recruitment_source,ol_issue_date,ol_signed_date,visa_status,visa_type,visa_no,visa_payer,flight_status,flight_date,arrival_date,flight_payer,commission,commission_paid_by,employee_status,project,salary,joining_date,notes,created_at,updated_at)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                               ON CONFLICT(employee_code) DO UPDATE SET
                               name=excluded.name,category=excluded.category,passport_no=excluded.passport_no,mobile=excluded.mobile,
                               nationality=excluded.nationality,recruitment_source=excluded.recruitment_source,ol_issue_date=excluded.ol_issue_date,
                               ol_signed_date=excluded.ol_signed_date,visa_status=excluded.visa_status,visa_type=excluded.visa_type,visa_no=excluded.visa_no,
                               visa_payer=excluded.visa_payer,flight_status=excluded.flight_status,flight_date=excluded.flight_date,
                               arrival_date=excluded.arrival_date,flight_payer=excluded.flight_payer,commission=excluded.commission,
                               commission_paid_by=excluded.commission_paid_by,employee_status=excluded.employee_status,project=excluded.project,
                               salary=excluded.salary,joining_date=excluded.joining_date,notes=excluded.notes,updated_at=excluded.updated_at""",
                            (final_code,name,category,passport,mobile,nationality,source,str(ol_issue) if ol_issue else "",str(ol_signed) if ol_signed else "",
                             visa_status,visa_type,visa_no,visa_payer,flight_status,str(flight_date) if flight_date else "",str(arrival_date) if arrival_date else "",
                             flight_payer,commission,commission_paid_by,emp_status,project,salary,str(joining) if joining else "",notes,
                             defaults.get("created_at") or now,now)
                        )
                        c.commit(); c.close()
                        audit("UPSERT","manpower",final_code,f"{name} | {passport}")
                        st.success("Manpower record saved.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        c.close()
                        st.error("Duplicate Employee Code or Passport No. blocked.")

    if mode=="🔎 Search / View":
        search=st.text_input("Search by Name / Employee Code / Passport / Mobile")
        out=df.copy()
        if search.strip() and len(out):
            s=search.strip().lower()
            mask=out.astype(str).apply(lambda col: col.str.lower().str.contains(s,na=False)).any(axis=1)
            out=out[mask]
        cols=["employee_code","name","category","passport_no","mobile","nationality","project","salary","ol_issue_date","ol_signed_date","visa_status","visa_type","flight_status","flight_date","arrival_date","commission","employee_status"]
        st.dataframe(out[cols],use_container_width=True,hide_index=True)

    if len(df):
        st.subheader("Quick Views")
        view=st.selectbox("Show",["All","OL Issued","Signed OL Received","Visa Pending","Visa Issued","Flight Booked","Arrived / Active"])
        out=df.copy()
        if view=="OL Issued": out=out[out.ol_issue_date.fillna("").ne("")]
        elif view=="Signed OL Received": out=out[out.ol_signed_date.fillna("").ne("")]
        elif view=="Visa Pending": out=out[out.visa_status.eq("Pending")]
        elif view=="Visa Issued": out=out[out.visa_status.eq("Issued")]
        elif view=="Flight Booked": out=out[out.flight_status.eq("Booked")]
        elif view=="Arrived / Active": out=out[out.employee_status.eq("Arrived / Active")]

        cols=["employee_code","name","category","passport_no","mobile","nationality","project","salary","ol_issue_date","ol_signed_date","visa_status","visa_type","flight_status","flight_date","arrival_date","commission","employee_status"]
        st.dataframe(out[cols],use_container_width=True,hide_index=True)

        st.subheader("Category Summary")
        summary=df.groupby("category",dropna=False).agg(
            Total=("employee_code","count"),
            OL_Issued=("ol_issue_date",lambda s:s.fillna("").ne("").sum()),
            Signed_OL=("ol_signed_date",lambda s:s.fillna("").ne("").sum()),
            Visa_Issued=("visa_status",lambda s:(s=="Issued").sum()),
            Flight_Booked=("flight_status",lambda s:(s=="Booked").sum()),
            Active=("employee_status",lambda s:(s=="Arrived / Active").sum())
        ).reset_index()
        st.dataframe(summary,use_container_width=True,hide_index=True)




def pro_visa_desk():
    if not can("Admin","Partner","Manager","PRO"):
        st.error("PRO / Visa Desk access restricted.")
        return

    st.subheader("PRO / Visa Desk")
    st.caption("Limited operational view for visa processing. Salary and recruitment commission are not shown.")

    c=conn()
    rows=c.execute("""SELECT employee_code,name,category,passport_no,nationality,mobile,
                             visa_status,visa_type,visa_no,visa_payer,employee_status,arrival_date
                      FROM manpower ORDER BY name,employee_code""").fetchall()
    c.close()

    if not rows:
        st.info("No manpower records available yet.")
        return

    labels=[f"{r['employee_code']} — {r['name']} — {r['category']}" for r in rows]
    picked=st.selectbox("Select Employee",labels,key="pro_emp_pick")
    r=rows[labels.index(picked)]

    st.caption(f"{r['name']} | {r['category']} | Passport: {r['passport_no']} | Nationality: {r['nationality'] or '-'}")

    visa_opts=["Not Applied","Pending","Issued","Rejected","Cancelled"]
    visa_type_opts=["","Employment","Visit","E-Visa","Other"]
    payer_opts=["","Company","Employee / Self","Agency","Partner / Investor","Other"]

    with st.form("pro_visa_form"):
        v1,v2=st.columns(2)
        vs=v1.selectbox("Visa Status",visa_opts,index=visa_opts.index(r["visa_status"]) if r["visa_status"] in visa_opts else 0)
        vt=v2.selectbox("Visa Type",visa_type_opts,index=visa_type_opts.index(r["visa_type"]) if r["visa_type"] in visa_type_opts else 0)
        vno=st.text_input("Visa No. / UID / Reference",value=r["visa_no"] or "")
        vp=st.selectbox("Visa Paid By",payer_opts,index=payer_opts.index(r["visa_payer"]) if r["visa_payer"] in payer_opts else 0)
        go=st.form_submit_button("Save Visa Update",use_container_width=True)

    if go:
        c=conn()
        c.execute("""UPDATE manpower
                     SET visa_status=?,visa_type=?,visa_no=?,visa_payer=?,updated_at=?
                     WHERE employee_code=?""",
                  (vs,vt,vno.strip(),vp,datetime.now().isoformat(timespec="seconds"),r["employee_code"]))
        c.commit(); c.close()
        audit("UPDATE_VISA","manpower",r["employee_code"],f"{vs} | {vt}")
        st.success("Visa record updated.")
        st.rerun()

    df=pd.DataFrame([dict(x) for x in rows])
    st.subheader("Visa Processing View")
    show=["employee_code","name","category","passport_no","nationality","visa_status","visa_type","visa_no","employee_status","arrival_date"]
    st.dataframe(df[show],use_container_width=True,hide_index=True)

def employee_documents():
    if not can("Admin","Partner","Manager","HR","PRO"):
        st.error("Employee document access restricted.")
        return

    st.subheader("Employee Documents")
    emp=employee_select("Select Employee",key="doc_emp")
    if not emp:
        return
    st.caption(f"{emp['name']} | {emp['category']} | Passport: {emp['passport_no']}")

    with st.form("emp_doc"):
        doc_type=st.selectbox("Document Type",["Passport","Emirates ID","Visa","Offer Letter","Signed Offer Letter","Labour Card / Work Permit","Employment Contract","Medical","Insurance","ILOE","Driving Licence","Certificate","Other"])
        doc_no=st.text_input("Document No.")
        issue=st.date_input("Issue Date",value=None)
        expiry=st.date_input("Expiry Date",value=None)
        upload=st.file_uploader("Attach Document",type=["pdf","jpg","jpeg","png","webp"])
        go=st.form_submit_button("Save Document")

    if go:
        c=conn()
        dup=c.execute(
            "SELECT id FROM employee_documents WHERE employee_code=? AND doc_type=? AND COALESCE(doc_no,'')=COALESCE(?, '')",
            (emp["employee_code"],doc_type,doc_no.strip())
        ).fetchone()
        if dup:
            c.close()
            st.error("Duplicate document blocked for this employee.")
        else:
            c.execute(
                """INSERT INTO employee_documents(employee_code,doc_type,doc_no,issue_date,expiry_date,file_name,file_type,file_blob,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (emp["employee_code"],doc_type,doc_no.strip(),str(issue) if issue else "",str(expiry) if expiry else "",
                 upload.name if upload else None,upload.type if upload else None,upload.getvalue() if upload else None,datetime.now().isoformat(timespec="seconds"))
            )
            c.commit(); c.close()
            audit("CREATE","employee_document",emp["employee_code"],doc_type)
            st.success("Document saved.")
            st.rerun()

    c=conn()
    rows=c.execute("SELECT * FROM employee_documents WHERE employee_code=? ORDER BY id DESC",(emp["employee_code"],)).fetchall()
    c.close()

    st.subheader("Document List")
    if rows:
        today=date.today()
        for r in rows:
            status="Available"
            if r["expiry_date"]:
                try:
                    days=(pd.to_datetime(r["expiry_date"]).date()-today).days
                    if days<0: status="Expired"
                    elif days<=30: status=f"Expiring in {days} days"
                except: pass
            label=f"{r['doc_type']} • {r['doc_no'] or '-'} • {status}"
            with st.expander(label):
                st.write("Issue Date:",r["issue_date"] or "-")
                st.write("Expiry Date:",r["expiry_date"] or "-")
                if r["file_blob"] and r["file_name"]:
                    st.download_button("View / Download",data=bytes(r["file_blob"]),file_name=r["file_name"],mime=r["file_type"] or "application/octet-stream",key=f"doc{r['id']}")
    else:
        st.info("No documents saved for this employee.")



def accommodation():
    if not can("Admin","Partner","Manager","HR"):
        st.error("Accommodation access restricted.")
        return

    st.subheader("Accommodation")
    emp=employee_select("Select Employee",key="acc_emp")
    if not emp:
        return
    st.caption(f"{emp['name']} | {emp['category']}")

    c=conn()
    existing=c.execute("SELECT * FROM accommodation WHERE employee_code=?",(emp["employee_code"],)).fetchone()
    c.close()
    ex=dict(existing) if existing else {}

    def _d(v):
        try: return pd.to_datetime(v).date() if v else None
        except: return None

    with st.form("acc"):
        camp=st.text_input("Camp / Accommodation Name",value=ex.get("camp_name",""))
        room=st.text_input("Room No.",value=ex.get("room_no",""))
        bed=st.text_input("Bed No.",value=ex.get("bed_no",""))
        checkin=st.date_input("Check-in Date",value=_d(ex.get("checkin_date")))
        checkout=st.date_input("Check-out Date",value=_d(ex.get("checkout_date")))
        cost=st.number_input("Monthly Cost (AED)",min_value=0.0,value=float(ex.get("monthly_cost") or 0))
        status_opts=["Active","Reserved","Checked Out","Cancelled"]
        sv=ex.get("status","Active")
        status=st.selectbox("Status",status_opts,index=status_opts.index(sv) if sv in status_opts else 0)
        notes=st.text_area("Notes",value=ex.get("notes",""))
        go=st.form_submit_button("Save")

    if go:
        c=conn()
        if status in ["Active","Reserved"] and camp.strip() and room.strip() and bed.strip():
            clash=c.execute(
                "SELECT employee_code FROM accommodation WHERE camp_name=? AND room_no=? AND bed_no=? AND status IN ('Active','Reserved') AND employee_code<>?",
                (camp.strip(),room.strip(),bed.strip(),emp["employee_code"])
            ).fetchone()
            if clash:
                c.close()
                st.error(f"Bed already occupied/reserved by {clash['employee_code']}.")
                return
        c.execute(
            """INSERT INTO accommodation(employee_code,camp_name,room_no,bed_no,checkin_date,checkout_date,monthly_cost,status,notes)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(employee_code) DO UPDATE SET camp_name=excluded.camp_name,room_no=excluded.room_no,bed_no=excluded.bed_no,
               checkin_date=excluded.checkin_date,checkout_date=excluded.checkout_date,monthly_cost=excluded.monthly_cost,status=excluded.status,notes=excluded.notes""",
            (emp["employee_code"],camp.strip(),room.strip(),bed.strip(),str(checkin) if checkin else "",str(checkout) if checkout else "",cost,status,notes)
        )
        c.commit(); c.close()
        audit("UPSERT","accommodation",emp["employee_code"])
        st.success("Accommodation saved.")
        st.rerun()

    c=conn(); df=pd.read_sql_query("SELECT * FROM accommodation ORDER BY camp_name,room_no,bed_no",c); c.close()
    if len(df):
        st.subheader("Occupancy")
        st.dataframe(df,use_container_width=True,hide_index=True)
    else:
        st.info("No accommodation records yet.")



def payroll():
    if not can("Admin","Partner","Manager","Accountant"):
        st.error("Payroll access restricted.")
        return

    st.subheader("Payroll")
    emp=employee_select("Select Employee",key="pay_emp")
    if not emp:
        return
    st.caption(f"{emp['name']} | {emp['category']}")

    with st.form("payroll"):
        month=st.text_input("Pay Month (YYYY-MM)",value=datetime.now().strftime("%Y-%m"))
        basic_default=0.0
        c=conn()
        mr=c.execute("SELECT salary FROM manpower WHERE employee_code=?",(emp["employee_code"],)).fetchone()
        c.close()
        if mr and mr["salary"]:
            basic_default=float(mr["salary"])
        basic=st.number_input("Basic Salary",min_value=0.0,value=basic_default)
        ot=st.number_input("Overtime",min_value=0.0)
        allowance=st.number_input("Allowance",min_value=0.0)
        deduction=st.number_input("Deduction",min_value=0.0)
        net_preview=basic+ot+allowance-deduction
        st.info(f"Net Salary: {money(net_preview)}")
        paid=st.number_input("Paid Amount",min_value=0.0)
        paid_date=st.date_input("Paid Date",value=None)
        ref=st.text_input("Payment Reference")
        go=st.form_submit_button("Save Payroll")

    if go:
        if not month.strip():
            st.error("Pay Month is required.")
        else:
            try:
                datetime.strptime(month.strip(),"%Y-%m")
            except:
                st.error("Pay Month must be YYYY-MM.")
                return

            net=basic+ot+allowance-deduction
            status="Paid" if paid>=net and net>0 else ("Part Paid" if paid>0 else "Unpaid")
            c=conn()
            c.execute(
                """INSERT INTO payroll(employee_code,pay_month,basic_salary,overtime,allowance,deduction,net_salary,paid_amount,paid_date,payment_ref,status)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(employee_code,pay_month) DO UPDATE SET
                   basic_salary=excluded.basic_salary,overtime=excluded.overtime,allowance=excluded.allowance,deduction=excluded.deduction,
                   net_salary=excluded.net_salary,paid_amount=excluded.paid_amount,paid_date=excluded.paid_date,payment_ref=excluded.payment_ref,status=excluded.status""",
                (emp["employee_code"],month.strip(),basic,ot,allowance,deduction,net,paid,str(paid_date) if paid_date else "",ref,status)
            )
            c.commit(); c.close()
            audit("UPSERT","payroll",f"{emp['employee_code']}-{month}",status)
            st.success("Payroll saved / updated. Duplicate month is not created.")
            st.rerun()

    c=conn()
    df=pd.read_sql_query(
        """SELECT p.*,m.name,m.category FROM payroll p
           LEFT JOIN manpower m ON m.employee_code=p.employee_code
           ORDER BY pay_month DESC,p.id DESC""",c
    )
    c.close()
    if len(df):
        st.dataframe(df,use_container_width=True,hide_index=True)
    else:
        st.info("No payroll records yet.")


def expenses():
    if not can("Admin","Partner","Manager","Accountant"):
        st.error("Expense access restricted."); return

    st.subheader("Expenses Register")
    projects=project_choices(); assets=asset_choices(); emps=employee_choices(); approved=approved_request_choices()
    proj_labels=[""]+[f"{x['code']} — {x['name']}" for x in projects]
    asset_labels=[""]+[f"{x['asset_id']} — {x['description']}" for x in assets]
    emp_labels=[""]+[f"{x['employee_code']} — {x['name']}" for x in emps]
    req_labels=[""]+[f"{x['req_no']} — {x['category']} — {money(x['amount'])}" for x in approved]

    with st.form("expense"):
        edate=st.date_input("Expense Date")
        category=st.selectbox("Category",["Project","Salary","Visa / PRO","Flight","Vehicle Fuel","Vehicle Maintenance","Accommodation","Office","Purchase","Other"])
        proj_pick=st.selectbox("Project / Cost Code (if applicable)",proj_labels)
        asset_pick=st.selectbox("Asset (if applicable)",asset_labels)
        emp_pick=st.selectbox("Employee (if applicable)",emp_labels)
        vendor=st.text_input("Vendor / Payee")
        amount=st.number_input("Amount (AED)",min_value=0.0)
        method=st.selectbox("Payment Method",["Bank Transfer","Cash","Card","Cheque","Government Portal","Other"])
        ref=st.text_input("Reference / Invoice No.")
        req_pick=st.selectbox("Approved Request (if required)",req_labels)
        upload=st.file_uploader("Attach Receipt / Invoice",type=["pdf","jpg","jpeg","png","webp"])
        go=st.form_submit_button("Save Expense")

    if go:
        if amount<=0: st.error("Amount is required."); return
        project=proj_pick.split(" — ",1)[0] if proj_pick else ""; asset=asset_pick.split(" — ",1)[0] if asset_pick else ""; emp=emp_pick.split(" — ",1)[0] if emp_pick else ""; req=req_pick.split(" — ",1)[0] if req_pick else ""
        c=conn()
        # Strict duplicate protection: reference-based first; otherwise likely duplicate on same date/vendor/amount/category.
        if ref.strip():
            dup=c.execute("SELECT expense_no FROM expenses WHERE LOWER(TRIM(reference))=LOWER(TRIM(?)) AND amount=? AND LOWER(TRIM(vendor))=LOWER(TRIM(?))",(ref.strip(),amount,vendor.strip())).fetchone()
        else:
            dup=c.execute("SELECT expense_no FROM expenses WHERE expense_date=? AND amount=? AND category=? AND LOWER(TRIM(vendor))=LOWER(TRIM(?))",(str(edate),amount,category,vendor.strip())).fetchone()
        if dup: c.close(); st.error(f"Possible duplicate expense blocked: {dup['expense_no']}."); return
        if req:
            valid=c.execute("SELECT req_no FROM requests WHERE req_no=? AND status='Approved'",(req,)).fetchone()
            if not valid: c.close(); st.error("Selected request is not approved."); return
        n=c.execute("SELECT COALESCE(MAX(id),0)+1 n FROM expenses").fetchone()["n"]; eno=f"EXP-{datetime.now():%Y%m}-{n:05d}"
        c.execute("""INSERT INTO expenses(expense_no,expense_date,category,project,asset_id,employee_code,vendor,amount,payment_method,reference,approved_request_no,attachment_name,attachment_type,attachment_blob,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (eno,str(edate),category,project,asset,emp,vendor.strip(),amount,method,ref.strip(),req,upload.name if upload else None,upload.type if upload else None,upload.getvalue() if upload else None,st.session_state.username,datetime.now().isoformat(timespec="seconds")))
        c.commit(); c.close(); audit("CREATE","expense",eno,category); st.success(f"Saved {eno}"); st.rerun()

    c=conn(); df=pd.read_sql_query("SELECT expense_no,expense_date,category,project,asset_id,employee_code,vendor,amount,payment_method,reference,approved_request_no,created_by FROM expenses ORDER BY id DESC",c); c.close()
    if len(df):
        st.metric("Total Expenses Recorded",money(df.amount.sum())); st.dataframe(df,use_container_width=True,hide_index=True)
    else: st.info("No expenses yet.")


def finance():
    if not can("Admin","Partner","Manager","Accountant"):
        st.error("Finance access restricted."); return

    st.subheader("Receivables")
    with st.expander("Add / Update Invoice"):
        with st.form("rec"):
            inv=st.text_input("Invoice No.")
            client=st.text_input("Client")
            project=st.text_input("Project / Cost Code")
            idate=st.date_input("Invoice Date")
            due=st.date_input("Due Date")
            amt=st.number_input("Invoice Total Amount (AED)",min_value=0.0)
            vat=st.number_input("VAT Included in Total (AED)",min_value=0.0)
            invoice_file=st.file_uploader("Attach Invoice / Supporting PDF",type=["pdf","jpg","jpeg","png","webp"])
            go=st.form_submit_button("Save Invoice")
        if go:
            if not inv.strip() or not client.strip() or amt<=0:
                st.error("Invoice No., Client and Total Amount are required.")
            else:
                c=conn()
                existing=c.execute("SELECT received FROM receivables WHERE invoice_no=?",(inv.strip(),)).fetchone()
                legacy_received=float(existing["received"] or 0) if existing else 0.0
                c.execute("""INSERT INTO receivables(invoice_no,client,project,invoice_date,due_date,amount,received,status,vat_amount,attachment_name,attachment_type,attachment_blob)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(invoice_no) DO UPDATE SET client=excluded.client,project=excluded.project,invoice_date=excluded.invoice_date,due_date=excluded.due_date,amount=excluded.amount,vat_amount=excluded.vat_amount,
                    attachment_name=COALESCE(excluded.attachment_name,receivables.attachment_name),attachment_type=COALESCE(excluded.attachment_type,receivables.attachment_type),attachment_blob=COALESCE(excluded.attachment_blob,receivables.attachment_blob)""",
                    (inv.strip(),client.strip(),project.strip(),str(idate),str(due),amt,legacy_received,"Open",vat,invoice_file.name if invoice_file else None,invoice_file.type if invoice_file else None,invoice_file.getvalue() if invoice_file else None))
                c.commit(); c.close(); audit("UPSERT","receivable",inv.strip()); st.success("Invoice saved."); st.rerun()

    c=conn(); invs=c.execute("SELECT * FROM receivables ORDER BY id DESC").fetchall(); c.close()
    if not invs:
        st.info("No receivables yet."); return

    labels=[f"{r['invoice_no']} — {r['client']} — {money(r['amount'])}" for r in invs]
    pick=st.selectbox("Select Invoice for Payment / Details",labels)
    row=invs[labels.index(pick)]
    c=conn(); payments=c.execute("SELECT * FROM receivable_payments WHERE invoice_no=? ORDER BY payment_date,id",(row['invoice_no'],)).fetchall(); c.close()
    paid_new=sum(float(x['amount'] or 0) for x in payments); legacy=float(row['received'] or 0); total_received=legacy+paid_new; outstanding=max(float(row['amount'] or 0)-total_received,0)
    status="Paid" if outstanding<=0 and float(row['amount'] or 0)>0 else ("Part Paid" if total_received>0 else "Unpaid")
    a,b,c1=st.columns(3); a.metric("Invoice Total",money(row['amount'])); b.metric("Received",money(total_received)); c1.metric("Outstanding",money(outstanding))
    st.caption(f"Status: {status} | Due: {row['due_date']} | VAT included: {money(row['vat_amount'] if 'vat_amount' in row.keys() else 0)}")
    if row['attachment_blob'] and row['attachment_name']:
        st.download_button("View / Download Invoice",data=bytes(row['attachment_blob']),file_name=row['attachment_name'],mime=row['attachment_type'] or 'application/octet-stream')

    with st.expander("Record Payment"):
        with st.form("rec_payment"):
            pdate=st.date_input("Payment Date")
            pamount=st.number_input("Payment Amount (AED)",min_value=0.0,max_value=max(outstanding,0.0) if outstanding>0 else 0.0)
            method=st.selectbox("Payment Method",["Bank Transfer","Cheque","Cash","Card","Other"])
            pref=st.text_input("Payment Reference")
            proof=st.file_uploader("Attach Payment Proof",type=["pdf","jpg","jpeg","png","webp"])
            pgo=st.form_submit_button("Save Payment")
        if pgo:
            if pamount<=0: st.error("Payment amount is required.")
            elif pref.strip() and any((x['reference'] or '').strip().lower()==pref.strip().lower() for x in payments): st.error("Duplicate payment reference blocked.")
            else:
                c=conn(); c.execute("""INSERT INTO receivable_payments(invoice_no,payment_date,amount,payment_method,reference,attachment_name,attachment_type,attachment_blob,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (row['invoice_no'],str(pdate),pamount,method,pref.strip(),proof.name if proof else None,proof.type if proof else None,proof.getvalue() if proof else None,st.session_state.username,datetime.now().isoformat(timespec='seconds')))
                new_received=legacy+paid_new+pamount; new_status='Paid' if new_received>=float(row['amount']) else 'Part Paid'
                c.execute("UPDATE receivables SET status=? WHERE invoice_no=?",(new_status,row['invoice_no'])); c.commit(); c.close(); audit('CREATE','receivable_payment',row['invoice_no'],money(pamount)); st.success('Payment recorded.'); st.rerun()

    if payments:
        st.subheader("Payment History")
        pdf=pd.DataFrame([dict(x) for x in payments])
        show=[c for c in ['payment_date','amount','payment_method','reference','created_by','created_at'] if c in pdf.columns]
        st.dataframe(pdf[show],use_container_width=True,hide_index=True)

    c=conn(); df=pd.read_sql_query("SELECT * FROM receivables ORDER BY id DESC",c); paydf=pd.read_sql_query("SELECT invoice_no,SUM(amount) payment_received FROM receivable_payments GROUP BY invoice_no",c); c.close()
    if len(paydf): df=df.merge(paydf,on='invoice_no',how='left')
    else: df['payment_received']=0.0
    df['payment_received']=df['payment_received'].fillna(0); df['Total_Received']=df['received'].fillna(0)+df['payment_received']; df['Outstanding']=(df.amount-df.Total_Received).clip(lower=0); df['Payment_Status']=df.apply(lambda x:'Paid' if x.Outstanding<=0 and x.amount>0 else ('Part Paid' if x.Total_Received>0 else 'Unpaid'),axis=1); df['Days_Overdue']=(pd.Timestamp(date.today())-pd.to_datetime(df.due_date)).dt.days.clip(lower=0)
    cols=['invoice_no','client','project','invoice_date','due_date','amount','vat_amount','Total_Received','Outstanding','Payment_Status','Days_Overdue']
    st.subheader("Receivable Register"); st.dataframe(df[[x for x in cols if x in df.columns]],use_container_width=True,hide_index=True)


def my_account():
    st.subheader("My Account")
    st.write("Name:",st.session_state.name)
    st.write("Role:",st.session_state.role)
    with st.form("pw_self"):
        old=st.text_input("Current Password",type="password")
        new=st.text_input("New Password",type="password")
        confirm=st.text_input("Confirm New Password",type="password")
        go=st.form_submit_button("Change My Password")
    if go:
        err=password_policy_error(new)
        if err:
            st.error(err)
            return
        if new!=confirm:
            st.error("New passwords do not match.")
            return
        c=conn(); rr=c.execute("SELECT password FROM users WHERE username=?",(st.session_state.username,)).fetchone()
        if rr and checkpw(old,rr["password"]):
            c.execute("UPDATE users SET password=?,must_change_password=0,last_password_change=? WHERE username=?",(hashpw(new),datetime.now().isoformat(),st.session_state.username))
            c.commit(); c.close()
            st.session_state.must_change_password=False
            audit("PASSWORD_CHANGE","user",st.session_state.username)
            st.success("Password changed securely.")
            st.rerun()
        else:
            c.close()
            st.error("Current password incorrect.")

# -----------------------------
# Admin
# -----------------------------
def admin():
    if role()!="Admin":
        st.error("System Administrator access only."); return

    st.subheader("System Administration & Security")
    c1,c2=st.columns(2)
    with c1:
        st.write("Current manager approval limit:",money(setting("manager_limit","10000")))
        nl=st.number_input("Manager Limit (AED)",min_value=1000.0,max_value=15000.0,value=float(setting("manager_limit","10000")),step=500.0)
        if st.button("Save Manager Limit"): set_setting("manager_limit",nl); st.success("Updated.")
    with c2:
        votes=int(float(setting("partner_votes_required","1")))
        nv=st.number_input("Partner Votes Required",min_value=1,max_value=10,value=votes,step=1)
        if st.button("Save Voting Rule"): set_setting("partner_votes_required",nv); st.success("Updated.")

    st.divider(); st.write("Create User")
    with st.form("usr"):
        u=st.text_input("Username"); n=st.text_input("Name"); r=st.selectbox("Role",["Admin","Partner","Manager","Accountant","PRO","HR","Project","Fleet"]); p=st.text_input("Temporary Password",type="password"); go=st.form_submit_button("Create User")
    if go:
        err=password_policy_error(p)
        if err: st.error(err)
        elif not u.strip() or not n.strip(): st.error("Username and name are required.")
        else:
            try:
                c=conn(); c.execute("INSERT INTO users(username,name,role,password,must_change_password,created_at) VALUES(?,?,?,?,1,?)",(u.strip(),n.strip(),r,hashpw(p),datetime.now().isoformat())); c.commit(); c.close(); audit("CREATE","user",u,r); st.success("User created."); st.rerun()
            except Exception: st.error("Could not create user. Username may already exist.")

    st.subheader("Users")
    c=conn(); users=c.execute("SELECT username,name,role,active,created_at FROM users ORDER BY id").fetchall(); c.close()
    udf=pd.DataFrame([dict(x) for x in users]); st.dataframe(udf,use_container_width=True,hide_index=True)
    other=[x for x in users if x['username']!=st.session_state.username]
    if other:
        labels=[f"{x['username']} — {x['name']} — {x['role']} — {'Active' if x['active'] else 'Disabled'}" for x in other]
        picked=st.selectbox("Manage User",labels); ur=other[labels.index(picked)]
        if ur['active']:
            if st.button("Disable Selected User"):
                c=conn(); c.execute("UPDATE users SET active=0 WHERE username=?",(ur['username'],)); c.commit(); c.close(); audit('DISABLE','user',ur['username']); st.success('User disabled.'); st.rerun()
        else:
            if st.button("Enable Selected User"):
                c=conn(); c.execute("UPDATE users SET active=1 WHERE username=?",(ur['username'],)); c.commit(); c.close(); audit('ENABLE','user',ur['username']); st.success('User enabled.'); st.rerun()

        role_options=["Admin","Partner","Manager","Accountant","PRO","HR","Project","Fleet"]
        new_role=st.selectbox("Change Selected User Role",role_options,index=role_options.index(ur["role"]) if ur["role"] in role_options else 0,key="change_role")
        if st.button("Apply Role Change"):
            c=conn(); c.execute("UPDATE users SET role=? WHERE username=?",(new_role,ur["username"])); c.commit(); c.close()
            audit("ROLE_CHANGE","user",ur["username"],f"{ur['role']} -> {new_role}")
            st.success("Role updated.")
            st.rerun()

        c=conn(); lockrow=c.execute("SELECT failed_count,locked_until FROM login_security WHERE username=?",(ur["username"],)).fetchone(); c.close()
        if lockrow and (lockrow["failed_count"] or lockrow["locked_until"]):
            st.warning(f"Login security: failed attempts={lockrow['failed_count'] or 0}, locked until={lockrow['locked_until'] or '-'}")
            if st.button("Unlock / Clear Failed Login Counter"):
                c=conn(); c.execute("DELETE FROM login_security WHERE username=?",(ur["username"],)); c.commit(); c.close()
                audit("UNLOCK_USER","user",ur["username"])
                st.success("Login lock cleared.")
                st.rerun()

    st.divider(); st.subheader("Role Access Matrix")
    matrix=pd.DataFrame([
        ["Admin","Full system + security + users + audit"],
        ["Partner","Operational overview + approvals + finance + manpower"],
        ["Manager","Operational control + approvals"],
        ["Accountant","Finance + Expenses + Payroll + requests"],
        ["PRO","PRO/Visa Desk + Employee Documents + government requests"],
        ["HR","Manpower + Employee Documents + Accommodation + requests"],
        ["Project","Projects + project requests"],
        ["Fleet","Fleet & Machinery + vehicle/purchase requests"],
    ],columns=["Role","Access"])
    st.dataframe(matrix,use_container_width=True,hide_index=True)

    st.divider(); st.subheader("Password Reset")
    reset_users=[x for x in users if x['username']!=st.session_state.username]
    if reset_users:
        rlabels=[f"{x['username']} — {x['name']} — {x['role']}" for x in reset_users]
        rp=st.selectbox("Reset Password For",rlabels,key="reset_user_pick")
        ru=reset_users[rlabels.index(rp)]
        with st.form("admin_reset_pw"):
            temp=st.text_input("New Temporary Password",type="password")
            confirm=st.text_input("Confirm Temporary Password",type="password")
            do_reset=st.form_submit_button("Reset Password")
        if do_reset:
            err=password_policy_error(temp)
            if err: st.error(err)
            elif temp!=confirm: st.error("Passwords do not match.")
            else:
                c=conn(); c.execute("UPDATE users SET password=?,must_change_password=1,last_password_change=? WHERE username=?",(hashpw(temp),datetime.now().isoformat(),ru['username'])); c.execute("DELETE FROM login_security WHERE username=?",(ru['username'],)); c.commit(); c.close(); audit("ADMIN_PASSWORD_RESET","user",ru['username']); st.success("Temporary password reset. User must change it at next login.")

    st.divider(); st.subheader("Backup & Export")
    if is_postgres(DATABASE_URL):
        st.success("Managed PostgreSQL persistent storage is connected.")
        if sqlite_backup_already_restored():
            st.info("Existing SQLite backup has already been restored. Repeat restore is locked for safety.")
        else:
            restore_file=st.file_uploader("Restore Existing SQLite Backup",type=["db","sqlite","sqlite3"],key="sqlite_restore")
            if restore_file and st.button("Restore Backup to Managed Database",type="primary"):
                try:
                    counts=restore_sqlite_backup(restore_file.getvalue())
                    audit("RESTORE","database","postgresql",str(counts))
                    st.success("Backup restored safely. No existing ERP records were overwritten.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Restore stopped safely: {exc}")
    else:
        st.warning("Current Community Cloud storage is not a production-grade permanent database. Download backups regularly until a managed cloud database is connected.")
    if not is_postgres(DATABASE_URL) and Path(DB).exists():
        c=conn(); c.execute('PRAGMA wal_checkpoint(FULL)'); c.close()
        st.download_button("Download Full SQLite Backup",data=Path(DB).read_bytes(),file_name=f"Lulu_Line_Backup_{date.today()}.db",mime="application/octet-stream")
    st.download_button("Download CSV Backup ZIP",data=make_backup_zip(),file_name=f"Lulu_Line_CSV_Backup_{date.today()}.zip",mime="application/zip")

    st.divider(); st.subheader("Audit Trail")
    c=conn(); adf=pd.read_sql_query("SELECT ts,username,action,entity,entity_id,detail FROM audit ORDER BY id DESC LIMIT 1000",c); c.close(); st.dataframe(adf,use_container_width=True,hide_index=True)


def pages_for_role():
    r=role()
    if r=="Admin":
        return ["Dashboard","New Request","Approvals","Projects","Fleet & Machinery","Manpower","Employee Documents","Accommodation","Finance","Expenses","Payroll","Admin & Security","My Account"]
    if r=="Partner":
        return ["Dashboard","New Request","Approvals","Projects","Fleet & Machinery","Manpower","Employee Documents","Accommodation","Finance","Expenses","Payroll","My Account"]
    if r=="Manager":
        return ["Dashboard","New Request","Approvals","Projects","Fleet & Machinery","Manpower","Employee Documents","Accommodation","Finance","Expenses","Payroll","My Account"]
    if r=="Accountant":
        return ["Dashboard","New Request","Finance","Expenses","Payroll","My Account"]
    if r=="PRO":
        return ["Dashboard","New Request","PRO / Visa Desk","Employee Documents","My Account"]
    if r=="HR":
        return ["Dashboard","New Request","Manpower","Employee Documents","Accommodation","My Account"]
    if r=="Project":
        return ["Dashboard","New Request","Projects","My Account"]
    if r=="Fleet":
        return ["Dashboard","New Request","Fleet & Machinery","My Account"]
    return ["Dashboard","My Account"]

# -----------------------------
# Start app
# -----------------------------
init()

if not st.session_state.get("logged"):
    login()
    st.stop()

check_session_security()

# Temporary passwords must be changed before any operational module is available.
if st.session_state.get("must_change_password"):
    st.warning("Security requirement: change your temporary password before using the system.")
    st.title(COMPANY)
    my_account()
    st.stop()

st.sidebar.caption("🔐 LLCC Secure Access")
st.sidebar.write(st.session_state.name)
st.sidebar.caption(f"Role: {st.session_state.role}")

page=st.sidebar.radio("Menu",pages_for_role())

if st.sidebar.button("Logout"):
    audit("LOGOUT","user",st.session_state.username)
    st.session_state.clear()
    st.rerun()

st.title(COMPANY)

routes={
    "Dashboard":dashboard,
    "New Request":new_request,
    "Approvals":approvals,
    "Projects":projects,
    "Fleet & Machinery":fleet,
    "Manpower":manpower,
    "PRO / Visa Desk":pro_visa_desk,
    "Employee Documents":employee_documents,
    "Accommodation":accommodation,
    "Finance":finance,
    "Expenses":expenses,
    "Payroll":payroll,
    "Admin & Security":admin,
    "My Account":my_account
}
routes[page]()
