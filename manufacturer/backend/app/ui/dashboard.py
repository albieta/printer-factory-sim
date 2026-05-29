import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Configuration
API_BASE_URL = "http://localhost:8000/api"

# Page config
st.set_page_config(
    page_title="3D Printer Production Simulator",
    page_icon="🏭",
    layout="wide"
)

# Helper functions
@st.cache_data(ttl=5)
def fetch_data(endpoint, params=None):
    """Fetch data from API with caching"""
    try:
        response = requests.get(f"{API_BASE_URL}{endpoint}", params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"API Error: {e}")
        return None


def post_data(endpoint, data=None):
    """Post data to API"""
    try:
        response = requests.post(f"{API_BASE_URL}{endpoint}", json=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"API Error: {e}")
        return None


# Navigation
st.sidebar.title("🏭 Navigation")
page = st.sidebar.radio("Go to", [
    "Overview",
    "Orders",
    "Inventory",
    "Suppliers",
    "Production",
    "Reports",
    "Settings"
])

# Main content
st.title("🏭 3D Printer Production Simulator")

if page == "Overview":
    st.header("Overview")
    
    # Fetch simulation status
    status = fetch_data("/simulation/status")
    
    if status:
        # KPI Cards
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Current Date", status.get("current_date", "N/A"))
        col2.metric("Pending Orders", status.get("pending_orders", 0))
        col3.metric("Completed Orders", status.get("completed_orders", 0))
        col4.metric("Total Events", status.get("total_events", 0))
    
    # Advance Day Button
    st.subheader("Simulation Control")
    if st.button("📅 Advance Day", type="primary"):
        result = post_data("/simulation/advance-day")
        if result:
            st.success(f"Day advanced to {result.get('sim_date')}")
            st.info(f"Orders created: {result.get('orders_created')}, Completed: {result.get('orders_completed')}")
            # Clear cache to refresh data
            st.cache_data.clear()
    
    # Charts
    st.subheader("Production Metrics")
    
    # Fetch events for charting
    events = fetch_data("/events", params={"limit": 500})
    
    if events:
        # Convert to DataFrame
        df_events = pd.DataFrame(events)
        df_events['sim_date'] = pd.to_datetime(df_events['sim_date'])
        
        # Orders Created vs Completed over time
        orders_created = df_events[df_events['event_type'] == 'ORDER_CREATED'].groupby('sim_date').size().reset_index(name='count')
        orders_completed = df_events[df_events['event_type'] == 'ORDER_COMPLETED'].groupby('sim_date').size().reset_index(name='count')
        
        if not orders_created.empty or not orders_completed.empty:
            fig = go.Figure()
            
            if not orders_created.empty:
                fig.add_trace(go.Scatter(
                    x=orders_created['sim_date'],
                    y=orders_created['count'],
                    mode='lines+markers',
                    name='Orders Created',
                    line=dict(color='blue')
                ))
            
            if not orders_completed.empty:
                fig.add_trace(go.Scatter(
                    x=orders_completed['sim_date'],
                    y=orders_completed['count'],
                    mode='lines+markers',
                    name='Orders Completed',
                    line=dict(color='green')
                ))
            
            fig.update_layout(
                title="Orders Created vs Completed Over Time",
                xaxis_title="Date",
                yaxis_title="Count",
                hovermode='x unified'
            )
            st.plotly_chart(fig, use_container_width=True)
    
    # Recent Events
    st.subheader("Recent Events")
    if events:
        df_recent = pd.DataFrame(events[:20])
        st.dataframe(df_recent[['event_type', 'sim_date', 'details']], use_container_width=True)

elif page == "Orders":
    st.header("Manufacturing Orders")
    
    # Fetch orders
    orders = fetch_data("/orders/mfg")
    
    if orders:
        # Display orders in table
        df_orders = pd.DataFrame(orders)
        
        # Filter by status
        status_filter = st.selectbox("Filter by Status", ["All", "PENDING", "RELEASED", "COMPLETED", "BLOCKED"])
        
        if status_filter != "All":
            df_orders = df_orders[df_orders['status'] == status_filter]
        
        st.dataframe(df_orders, use_container_width=True)
        
        # Release orders
        st.subheader("Release Orders to Production")
        pending_orders = [o for o in orders if o['status'] == 'PENDING']
        
        if pending_orders:
            selected_orders = st.multiselect(
                "Select orders to release",
                [f"{o['id']} - {o['product_id']} (Qty: {o['quantity']})" for o in pending_orders]
            )
            
            if st.button("Release Selected Orders"):
                order_ids = [o['id'] for o in pending_orders if f"{o['id']} - {o['product_id']} (Qty: {o['quantity']})" in selected_orders]
                result = post_data("/orders/mfg/release", {"order_ids": order_ids})
                if result:
                    st.success(f"Released {len(result.get('successful', []))} orders")
                    if result.get('failed'):
                        for failure in result['failed']:
                            st.warning(f"Failed: {failure['order_id']} - {failure['reason']}")
                    st.cache_data.clear()
        else:
            st.info("No pending orders")

elif page == "Inventory":
    st.header("Inventory Management")
    
    # Fetch inventory
    inventory = fetch_data("/inventory")
    capacity = fetch_data("/inventory/capacity")
    
    if inventory and capacity:
        # Capacity gauge
        st.subheader("Warehouse Capacity")
        col1, col2, col3 = st.columns(3)
        col1.metric("Warehouse Capacity", f"{capacity.get('warehouse_capacity', 0):,.0f}")
        col2.metric("Current Usage", f"{capacity.get('current_usage', 0):,.0f}")
        col3.metric("Available", f"{capacity.get('available_capacity', 0):,.0f}")
        
        # Capacity gauge chart
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=capacity.get('usage_percentage', 0),
            title={'text': "Capacity Usage (%)"},
            gauge={'axis': {'range': [0, 100]},
                   'bar': {'color': "blue"},
                   'steps': [
                       {'range': [0, 50], 'color': "lightgreen"},
                       {'range': [50, 80], 'color': "yellow"},
                       {'range': [80, 100], 'color': "red"}
                   ]}
        ))
        st.plotly_chart(fig, use_container_width=True)
        
        # Inventory table
        st.subheader("Stock Levels")
        df_inventory = pd.DataFrame(inventory)
        st.dataframe(df_inventory, use_container_width=True)

elif page == "Suppliers":
    st.header("Supplier Management")
    
    # Fetch suppliers
    suppliers = fetch_data("/suppliers")
    
    if suppliers:
        df_suppliers = pd.DataFrame(suppliers)
        st.dataframe(df_suppliers, use_container_width=True)

elif page == "Production":
    st.header("Production Status")
    
    # Fetch released orders
    orders = fetch_data("/orders/mfg", params={"status": "RELEASED"})
    
    if orders:
        st.subheader("Active Production Orders")
        df_orders = pd.DataFrame(orders)
        st.dataframe(df_orders, use_container_width=True)
    else:
        st.info("No active production orders")

elif page == "Reports":
    st.header("Event Reports")
    
    # Fetch events
    events = fetch_data("/events", params={"limit": 1000})
    
    if events:
        df_events = pd.DataFrame(events)
        
        # Event type breakdown
        st.subheader("Event Type Distribution")
        event_counts = df_events['event_type'].value_counts()
        fig = px.pie(values=event_counts.values, names=event_counts.index, title="Events by Type")
        st.plotly_chart(fig, use_container_width=True)
        
        # Event log
        st.subheader("Event Log")
        st.dataframe(df_events, use_container_width=True)

elif page == "Settings":
    st.header("Settings")
    
    # Fetch config
    config = fetch_data("/config")
    
    if config:
        st.subheader("Simulation Configuration")
        
        with st.form("config_form"):
            warehouse_capacity = st.number_input("Warehouse Capacity", value=config.get('warehouse_capacity', 12000))
            daily_assembly_hours = st.number_input("Daily Assembly Hours", value=config.get('daily_assembly_hours', 8.0))
            demand_mean = st.number_input("Demand Distribution Mean", value=config.get('demand_distribution_mean', 5.0))
            demand_variance = st.number_input("Demand Distribution Variance", value=config.get('demand_distribution_variance', 2.0))
            
            submitted = st.form_submit_button("Save Configuration")
            
            if submitted:
                new_config = {
                    "warehouse_capacity": warehouse_capacity,
                    "daily_assembly_hours": daily_assembly_hours,
                    "demand_distribution_mean": demand_mean,
                    "demand_distribution_variance": demand_variance
                }
                
                response = requests.put(f"{API_BASE_URL}/config", json=new_config)
                if response.status_code == 200:
                    st.success("Configuration saved successfully")
                    st.cache_data.clear()
                else:
                    st.error("Failed to save configuration")
        
        # Reset simulation
        st.subheader("Reset Simulation")
        if st.button("🔄 Reset Simulation"):
            if st.checkbox("I understand this will delete all orders and events"):
                result = post_data("/simulation/reset")
                if result:
                    st.success("Simulation reset successfully")
                    st.cache_data.clear()
