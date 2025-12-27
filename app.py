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
            
            # CHANGE: Use 'append' instead of 'replace' to keep manually added data
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
    """Initializes the users table and default admin."""
    with conn.session as s:
        s.execute(text("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT);"))
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
            if "synced" not in st.session_state:
                sync_data_from_excel()
                st.session_state.synced = True
            st.rerun()
        else:
            st.sidebar.error("Invalid credentials.")

# --- MAIN APP ---
def main():
    init_db()
    if "logged_in" not in st.session_state: st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        st.title("🧾 Money Wiz CRM")
        login()
        return

    # Fetch df_all
    df_all = conn.query("SELECT * FROM sales", ttl=0)

    st.sidebar.write(f"Logged in: **{st.session_state.username}**")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    user = st.session_state.username
    role = st.session_state.role

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
                qty = c1.number_input("Quantity", min_value=1)
                u_p = c2.number_input("Unit Price", min_value=0.0)
                disc = c2.number_input("Discount", min_value=0.0)
                reg = c2.selectbox("Region", get_choices(df_all, "Region", ["North", "South", "East", "West"]))
                loc = c2.selectbox("Store Location", get_choices(df_all, "StoreLocation", ["Store A", "Store B"]))
                
                # Formula-based Read-Only Total Price
                ship = c3.number_input("Shipping Cost", min_value=0.0)
                calc_total = (qty * u_p) - disc + ship
                c2.number_input("Total Price (Calculated)", value=calc_total, disabled=True)
                
                sys_oid = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                c3.info(f"Generated OrderID: {sys_oid}")
                pay = c3.selectbox("Payment Method", ["Cash", "Card", "Online"])
                prom = c3.text_input("Promotion")
                r_man = c3.selectbox("Region Manager", get_choices(df_all, "RegionManager", ["Admin"]))
                ret_status = c3.text_input("Returned (Status)", value="No") 
                
                if st.form_submit_button("Submit"):
                    with conn.session as s:
                        s.execute(text("""INSERT INTO sales (CustomerName, CustomerType, Product, Quantity, Region, Date, UnitPrice, 
                                       StoreLocation, Discount, Salesperson, TotalPrice, PaymentMethod, Promotion, Returned, 
                                       OrderID, ShippingCost, RegionManager) VALUES (:n, :ct, :p, :q, :r, :d, :up, :sl, :di, :sp, :tp, :pm, :pr, :re, :oid, :sc, :rm)"""),
                                  {"n":name, "ct":c_type, "p":prod, "q":qty, "r":reg.lower(), "d":datetime.now().strftime("%Y-%m-%d"), 
                                   "up":u_p, "sl":loc.lower(), "di":disc, "sp":user, "tp":qty*u_p-disc+ship, "pm":pay, "pr":prom, "re":ret_status, 
                                   "oid":sys_oid, "sc":ship, "rm":r_man.lower()})
                        s.commit()
                    
                    msg = st.empty()
                    msg.success(f"🎉 Customer added! OrderID: {sys_oid}")
                    time.sleep(5)
                    msg.empty()
                    st.rerun()

        with tabs[1]:
            st.subheader("Update All Fields by OrderID")
            search_oid = st.text_input("Enter OrderID to Modify")
            if search_oid:
                record = my_data[my_data["OrderID"].astype(str) == search_oid]
                if not record.empty:
                    with st.form("full_up_form"):
                        u1, u2, u3 = st.columns(3)
                        u_name = u1.text_input("Customer Name", value=record.iloc[0]['CustomerName'])
                        u_ct = u1.selectbox("Customer Type", get_choices(df_all, "CustomerType", ["Retail"]), index=0)
                        u_prod = u1.selectbox("Product", get_choices(df_all, "Product", ["Laptop"]), index=0)
                        u_qty = u1.number_input("Quantity", value=int(record.iloc[0]['Quantity']))
                        u_up = u2.number_input("Unit Price", value=float(record.iloc[0]['UnitPrice']))
                        u_disc = u2.number_input("Discount", value=float(record.iloc[0].get('Discount', 0.0)))
                        u_reg = u2.selectbox("Region", get_choices(df_all, "Region", ["North"]), index=0)
                        u_loc = u2.selectbox("Store Location", get_choices(df_all, "StoreLocation", ["Store A"]), index=0)
                        u_pay = u3.selectbox("Payment Method", ["Cash", "Card", "Online"])
                        u_prom = u3.text_input("Promotion", value=str(record.iloc[0].get('Promotion', '')))
                        u_ret = u3.text_input("Returned (Status)", value=str(record.iloc[0].get('Returned', 'No')))
                        u_ship = u3.number_input("Shipping Cost", value=float(record.iloc[0].get('ShippingCost', 0.0)))
                        
                        # Fix NameError here: using correct u_ variables
                        up_calc_total = (u_qty * u_up) - u_disc + u_ship
                        u2.number_input("Total Price (Calculated)", value=up_calc_total, disabled=True)

                        if st.form_submit_button("Apply Full Update"):
                            with conn.session as s:
                                s.execute(text("""UPDATE sales SET CustomerName=:n, CustomerType=:ct, Product=:p, Quantity=:q, Region=:r, UnitPrice=:up, StoreLocation=:sl, Discount=:di, TotalPrice=:tp, PaymentMethod=:pm, Promotion=:pr, Returned=:re, ShippingCost=:sc WHERE OrderID=:oid AND Salesperson=:u"""),
                                          {"n":u_name, "ct":u_ct, "p":u_prod, "q":u_qty, "r":u_reg.lower(), "up":u_up, "sl":u_loc.lower(), "di":u_disc, "tp":u_qty*u_up - u_disc + u_ship, "pm":u_pay, "pr":u_prom, "re":u_ret, "sc":u_ship, "oid":search_oid, "u":user})
                                s.commit()
                            msg = st.empty()
                            msg.success(f"✅ Order {search_oid} updated successfully!")
                            time.sleep(5)
                            msg.empty()
                            st.rerun()
                else: st.warning("OrderID not found.")

        with tabs[2]:
            st.subheader("Delete Customer Record")
            search_input = st.text_input("Search Customer Name to Delete")
            if search_input:
                matches = my_data[my_data["CustomerName"].str.contains(search_input, case=False, na=False)]
                if not matches.empty:
                    match_list = [f"{row['CustomerName']} | {row['OrderID']} | {row['Product']}" for _, row in matches.iterrows()]
                    selected_match = st.selectbox("Select exact entry", match_list)
                    if st.button("Permanently Delete", type="primary"):
                        target_oid = selected_match.split(" | ")[1]
                        with conn.session as s:
                            s.execute(text("DELETE FROM sales WHERE OrderID=:oid AND Salesperson=:u"), 
                                      {"oid":target_oid, "u":user})
                            s.commit()
                        msg = st.empty()
                        msg.success(f"🗑️ Record {target_oid} deleted!")
                        time.sleep(5)
                        msg.empty()
                        st.rerun()

        with tabs[3]: 
            st.dataframe(my_data)
        
        with tabs[4]: 
            st.subheader("Search Customer Records")
            query = st.text_input("Enter Customer Name")
            if query:
                res = my_data[my_data["CustomerName"].str.contains(query, case=False, na=False)]
                if not res.empty:
                    for idx, row in res.iterrows():
                        with st.expander(f"Details: {row['CustomerName']} (ID: {row['OrderID']})"):
                            st.json(row.to_dict()) 
                else: st.warning("No matches found.")

        with tabs[5]: 
            if not my_data.empty:
                st.subheader("Your Sales Analytics")
                st.bar_chart(my_data.groupby("Product")["TotalPrice"].sum())

    elif role == "Region Manager":
        st.header("📈 Managerial Insights")
        if not df_all.empty:
            m_opt = st.selectbox("Operation", [
                "Region-wise Sale", "Store-wise Sale", "Person-wise Sale", 
                "Max Product per Store", "Salesperson Max Sales", "Store-wise Return"
            ])

            if m_opt == "Region-wise Sale":
                r = st.selectbox("Select Region", df_all["Region"].unique())
                st.bar_chart(df_all[df_all["Region"] == r].groupby("Product")["TotalPrice"].sum())

            elif m_opt == "Store-wise Sale":
                s = st.selectbox("Select Store", df_all["StoreLocation"].unique())
                st.bar_chart(df_all[df_all["StoreLocation"] == s].groupby("Product")["TotalPrice"].sum())

            elif m_opt == "Person-wise Sale":
                p_list = df_all["Salesperson"].dropna().unique()
                p = st.selectbox("Select Salesperson", p_list)
                st.bar_chart(df_all[df_all["Salesperson"] == p].groupby("Product")["TotalPrice"].sum())

            elif m_opt == "Max Product per Store":
                grouped = df_all.groupby(["StoreLocation", "Product"])["TotalPrice"].sum().reset_index()
                idx = grouped.groupby("StoreLocation")["TotalPrice"].idxmax()
                st.bar_chart(grouped.loc[idx].set_index("StoreLocation")["TotalPrice"])

            elif m_opt == "Salesperson Max Sales":
                st.bar_chart(df_all.groupby("Salesperson")["TotalPrice"].sum())

            elif m_opt == "Store-wise Return":
                sr = st.selectbox("Select Store for Returns", df_all["StoreLocation"].dropna().unique())
                st.bar_chart(df_all[df_all["StoreLocation"] == sr].groupby("Product")["Returned"].sum())

if __name__ == "__main__":
    main()