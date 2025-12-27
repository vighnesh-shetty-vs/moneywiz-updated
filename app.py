import streamlit as st
import pandas as pd
import hashlib
import os
import time
from sqlalchemy import text
from datetime import datetime

# --- DATABASE SETUP ---
conn = st.connection("my_database", type="sql")

# --- HELPER FUNCTIONS ---
def get_choices(df, column, defaults):
    """Safely extracts unique values for dropdowns from the dataframe."""
    if df is not None and not df.empty and column in df.columns:
        choices = sorted(df[column].dropna().unique().tolist())
        return choices if choices else defaults
    return defaults

def sync_data_from_excel():
    """Reads, normalizes, and migrates Excel data to SQL automatically."""
    if os.path.exists("customers.xlsx"):
        try:
            df = pd.read_excel("customers.xlsx")
            df.columns = df.columns.str.strip()
            cols_to_normalize = ["Salesperson", "RegionManager", "Region", "StoreLocation"]
            for col in cols_to_normalize:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip().str.lower()
            
            # Use append to preserve manually added data
            df.to_sql("sales", conn.engine, if_exists="append", index=False)
            
            default_pw = hashlib.sha256("password123".encode()).hexdigest()
            with conn.session as s:
                for col, role in [("Salesperson", "Salesperson"), ("RegionManager", "Region Manager")]:
                    if col in df.columns:
                        for user in df[col].dropna().unique():
                            s.execute(text("INSERT OR IGNORE INTO users VALUES (:u, :p, :r)"), 
                                      {"u": str(user), "p": default_pw, "r": role})
                s.commit()
        except Exception as e:
            st.error(f"Automatic Sync Error: {e}")

def init_db():
    """Initializes standard SQL tables with full schema."""
    with conn.session as s:
        s.execute(text("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT);"))
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                CustomerName TEXT, CustomerType TEXT, Product TEXT, Quantity INTEGER,
                Region TEXT, Date TEXT, UnitPrice REAL, StoreLocation TEXT,
                Discount REAL, Salesperson TEXT, TotalPrice REAL, PaymentMethod TEXT,
                Promotion TEXT, Returned TEXT, OrderID TEXT, ShippingCost REAL,
                RegionManager TEXT
            );
        """))
        # Ensure Admin is Provisioned
        admin_pw = hashlib.sha256("admin123".encode()).hexdigest()
        s.execute(text("INSERT OR IGNORE INTO users VALUES ('admin', :p, 'Region Manager')"), {"p": admin_pw})
        s.commit()

# --- AUTHENTICATION ---
def login():
    st.sidebar.title("🔐 Login")
    u_input = st.sidebar.text_input("Username").strip().lower()
    p_input = st.sidebar.text_input("Password", type="password")
    
    if st.sidebar.button("Login"):
        hpw = hashlib.sha256(p_input.encode()).hexdigest()
        res = conn.query("SELECT role FROM users WHERE username=:u AND password=:p", 
                         params={"u": u_input, "p": hpw}, ttl=0)
        
        if not res.empty:
            st.session_state.logged_in = True
            st.session_state.username = u_input
            st.session_state.role = res.iloc[0]['role']
            # Always sync on login to ensure data is available
            if "synced" not in st.session_state:
                sync_data_from_excel()
                st.session_state.synced = True
            st.rerun()
        else:
            st.sidebar.error("Invalid credentials.")

# --- MAIN APP ---
def main():
    init_db() # Create tables first
    
    if "logged_in" not in st.session_state: 
        st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        st.title("🧾 Money Wiz CRM")
        login()
        return

    # Fetch data for the session
    df_all = conn.query("SELECT * FROM sales", ttl=0)

    st.sidebar.write(f"Logged in: **{st.session_state.username}**")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    user = st.session_state.username
    role = st.session_state.role

    # --- SALESPERSON WORKSPACE ---
    if role == "Salesperson":
        st.header("👤 Salesperson Workspace")
        my_data = df_all[df_all["Salesperson"].astype(str).str.lower() == user]
        
        tabs = st.tabs(["Add Customer", "Update Record", "Delete Customer", "View All", "Search Customer", "Analytics"])
        
        with tabs[0]: 
            st.subheader("Add New Customer Record")
            with st.form("add_form", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                name = c1.text_input("Customer Name")
                c_type = c1.selectbox("Customer Type", get_choices(df_all, "CustomerType", ["Retail", "Wholesale"]))
                prod = c1.selectbox("Product", get_choices(df_all, "Product", ["Laptop", "Phone", "Tablet"]))
                qty = c1.number_input("Quantity", min_value=1, value=1)
                u_p = c2.number_input("Unit Price", min_value=0.0, value=0.0)
                disc = c2.number_input("Discount", min_value=0.0, value=0.0)
                reg = c2.selectbox("Region", get_choices(df_all, "Region", ["North", "South"]))
                loc = c2.selectbox("Store Location", get_choices(df_all, "StoreLocation", ["Main Store"]))
                
                # Formula Logic
                ship = c3.number_input("Shipping Cost", min_value=0.0, value=0.0)
                calc_total = (qty * u_p) - disc + ship
                c2.number_input("Total Price (Calculated)", value=calc_total, disabled=True)
                
                sys_oid = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                c3.info(f"Generated OrderID: {sys_oid}")
                pay = c3.selectbox("Payment Method", ["Cash", "Card", "Online"])
                prom = c3.text_input("Promotion")
                ret_status = c3.text_input("Returned (Status)", value="No") 
                r_man = c3.selectbox("Region Manager", get_choices(df_all, "RegionManager", ["Admin"]))
                
                if st.form_submit_button("Submit"):
                    with conn.session as s:
                        s.execute(text("""INSERT INTO sales (CustomerName, CustomerType, Product, Quantity, Region, Date, UnitPrice, 
                                       StoreLocation, Discount, Salesperson, TotalPrice, PaymentMethod, Promotion, Returned, 
                                       OrderID, ShippingCost, RegionManager) VALUES (:n, :ct, :p, :q, :r, :d, :up, :sl, :di, :sp, :tp, :pm, :pr, :re, :oid, :sc, :rm)"""),
                                  {"n":name, "ct":c_type, "p":prod, "q":qty, "r":reg.lower(), "d":datetime.now().strftime("%Y-%m-%d"), 
                                   "up":u_p, "sl":loc.lower(), "di":disc, "sp":user, "tp":calc_total, "pm":pay, "pr":prom, "re":ret_status, 
                                   "oid":sys_oid, "sc":ship, "rm":r_man.lower()})
                        s.commit()
                    
                    msg = st.empty()
                    msg.success(f"🎉 Customer added! OrderID: {sys_oid}")
                    time.sleep(5)
                    msg.empty()
                    st.rerun()
        
        # ... (Other salesperson tabs: Update, Delete, View, Search, Analytics)

    # --- REGION MANAGER (ADMIN) WORKSPACE ---
    elif role == "Region Manager":
        st.header("📈 Region Manager Analytics")
        
        # If no data exists, suggest manual sync or wait
        if df_all.empty:
            st.info("The database is currently empty. Run a sync or add records to see analytics.")
            if st.button("Trigger Manual Sync from Excel"):
                sync_data_from_excel()
                st.rerun()
        else:
            # All 6 Original Analytics Reports
            m_opt = st.selectbox("Select Analytics View", [
                "Region-wise Sale", "Store-wise Sale", "Person-wise Sale", 
                "Max Product per Store", "Salesperson Max Sales", "Store-wise Return"
            ])

            if m_opt == "Region-wise Sale":
                r_choice = st.selectbox("Select Region", df_all["Region"].unique())
                st.bar_chart(df_all[df_all["Region"] == r_choice].groupby("Product")["TotalPrice"].sum())

            elif m_opt == "Store-wise Sale":
                s_choice = st.selectbox("Select Store", df_all["StoreLocation"].unique())
                st.bar_chart(df_all[df_all["StoreLocation"] == s_choice].groupby("Product")["TotalPrice"].sum())

            elif m_opt == "Person-wise Sale":
                p_choice = st.selectbox("Select Salesperson", df_all["Salesperson"].unique())
                st.bar_chart(df_all[df_all["Salesperson"] == p_choice].groupby("Product")["TotalPrice"].sum())

            elif m_opt == "Max Product per Store":
                grouped = df_all.groupby(["StoreLocation", "Product"])["TotalPrice"].sum().reset_index()
                idx = grouped.groupby("StoreLocation")["TotalPrice"].idxmax()
                st.bar_chart(grouped.loc[idx].set_index("StoreLocation")["TotalPrice"])

            elif m_opt == "Salesperson Max Sales":
                st.bar_chart(df_all.groupby("Salesperson")["TotalPrice"].sum())

            elif m_opt == "Store-wise Return":
                sr_choice = st.selectbox("Select Store for Returns", df_all["StoreLocation"].unique())
                st.bar_chart(df_all[df_all["StoreLocation"] == sr_choice].groupby("Product")["Returned"].count())

if __name__ == "__main__":
    main()