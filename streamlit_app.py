"""
Single Page Streamlit App combining:
1. Process PDF (Upload)
2. View Processed PDF
3. Validate Price data
"""

import streamlit as st
import sys
import json
import asyncio
from pathlib import Path

from processor.utils import run_async
from processor.agent_factory import get_validation_agent
from processor.db import (
    get_all_manufacturers,
    get_brands_for_manufacturer,
    get_series_for_manufacturer_brand,
    get_series_parameters,
    check_health,
    get_job_status,
    list_files
)


# Page config
st.set_page_config(
    page_title="Pricebook AI Core",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Hide the sidebar completely
st.markdown(
    """
    <style>
        [data-testid="collapsedControl"] {
            display: none;
        }
        [data-testid="stSidebar"] {
            display: none;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# Initialize agent
agent = get_validation_agent()

st.title("🤖 Pricebook AI Application")
st.markdown("A unified interface to process, view, and validate pricing data.")
st.markdown("---")

# ==========================================
# Section 1: Processed PDFs
# ==========================================
st.header("1. Processed PDFs Data")
with st.container():
    files_result = list_files()
    if files_result.get("status") == "success":
        files = files_result.get("data", [])
        
        # Filter for completed files
        completed_files = [f for f in files if f.get("extraction_status", f.get("status")) == "completed"]
        
        if completed_files:
            table_data = []
            for file in completed_files:
                # Format Date
                raw_date = file.get("uploaded_at", "")
                process_date = raw_date
                if raw_date:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                        process_date = dt.strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        pass
                
                table_data.append({
                    "Manufacturer": file.get("manufacturer", "N/A"),
                    "Brand": file.get("brand", "N/A"),
                    "Process Date": process_date,
                    "File Name": file.get("filename", "Unknown")
                })
            
            st.dataframe(
                table_data,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Manufacturer": st.column_config.TextColumn("Manufacturer", width="medium"),
                    "Brand": st.column_config.TextColumn("Brand", width="medium"),
                    "Process Date": st.column_config.TextColumn("Process Date", width="small"),
                    "File Name": st.column_config.TextColumn("File Name", width="large"),
                }
            )
        else:
            st.info("No completed PDFs available yet.")
    else:
        st.error(f"Failed to load processed PDFs: {files_result.get('error')}")

# ==========================================
# Section 2: View Processed PDF
# ==========================================
st.markdown("---")
st.header("2. View Processed PDF Data")

manufacturers = get_all_manufacturers()
view_col1, view_col2, view_col3 = st.columns(3)

with view_col1:
    view_mfg = st.selectbox("Select Manufacturer", options=[""] + manufacturers, key="view_mfg", format_func=lambda x: "Select a manufacturer..." if x == "" else x)

view_brand = None
if view_mfg:
    brands = get_brands_for_manufacturer(view_mfg)
    with view_col2:
        view_brand_sel = st.selectbox("Select Brand (optional)", options=[""] + (brands if brands else []), key="view_brand", format_func=lambda x: "All brands" if x == "" else x)
        view_brand = view_brand_sel if view_brand_sel else None

    series_list = get_series_for_manufacturer_brand(view_mfg, view_brand)
    if series_list:
        with view_col3:
            series_options = [s["series_name"] for s in series_list]
            series_labels = [f"{s['series_name']} ({s.get('category', 'Unknown')})" for s in series_list]
            view_series_idx = st.selectbox("Select Series", options=range(len(series_options)), format_func=lambda i: series_labels[i], key="view_series")
            view_series = series_list[view_series_idx]
        
        # Load parameters explicitly when series selected
        series_id = view_series.get("_id")
        if series_id:
            params_result = get_series_parameters(series_id)
            if params_result["status"] == "success":
                params_data = params_result["data"]
                base_params = params_data.get("parameters", [])
                opt_params = params_data.get("optional_parameters", [])
                
                with st.container(border=True):
                    st.markdown(f"### 📋 Parameters for {view_series['series_name']}")
                    st.markdown("---")
                    
                    # BASE PARAMETERS
                    st.markdown("#### 🔧 Base Parameters")
                    if base_params:
                        for p in base_params:
                            options = p.get("options", [])
                            opt_count = len(options)
                            
                            with st.expander(f"**{p.get('parameter_name', 'Unknown')}** ({opt_count} options)", expanded=False):
                                if options:
                                    st.markdown("**Options:**")
                                    for idx, opt in enumerate(options):
                                        opt_name = opt.get('option_name', opt.get('name', 'N/A'))
                                        st.markdown(f"**{idx + 1}. {opt_name}**")
                                else:
                                    st.info("No options available.")
                    else:
                        st.info("No base parameters extracted.")
                    
                    st.markdown("---")
                    # OPTIONAL PARAMETERS
                    st.markdown("#### ✨ Optional Parameters")
                    if opt_params:
                        for p in opt_params:
                            options = p.get("options", [])
                            opt_count = len(options)
                            
                            with st.expander(f"**{p.get('parameter_name', 'Unknown')}** ({opt_count} options)", expanded=False):
                                if options:
                                    st.markdown("**Options:**")
                                    for idx, opt in enumerate(options):
                                        opt_name = opt.get('option_name', opt.get('name', 'N/A'))
                                        st.markdown(f"**{idx + 1}. {opt_name}**")
                                else:
                                    st.info("No options available.")
                    else:
                        st.info("No optional parameters extracted.")
            else:
                st.error(f"Error loading parameters: {params_result.get('error', 'Unknown')}")
    else:
        with view_col3:
            st.warning("No series found for this combination.")

# ==========================================
# Section 3: Validate Price data
# ==========================================
st.markdown("---")
st.header("3. Validate Price Data")

val_col1, val_col2, val_col3 = st.columns(3)

with val_col1:
    val_mfg = st.selectbox("Select Manufacturer", options=[""] + manufacturers, key="val_mfg_select", format_func=lambda x: "Select a manufacturer..." if x == "" else x)

val_brand = None
if val_mfg:
    brands2 = get_brands_for_manufacturer(val_mfg)
    with val_col2:
        val_brand_sel = st.selectbox("Select Brand (optional)", options=[""] + (brands2 if brands2 else []), key="val_brand_select", format_func=lambda x: "All brands" if x == "" else x)
        val_brand = val_brand_sel if val_brand_sel else None

    val_series_list = get_series_for_manufacturer_brand(val_mfg, val_brand)
    if val_series_list:
        with val_col3:
            val_series_opts = [s["series_name"] for s in val_series_list]
            val_series_labels = [f"{s['series_name']} ({s.get('category', 'Unknown')})" for s in val_series_list]
            val_series_idx = st.selectbox("Select Series", options=range(len(val_series_opts)), format_func=lambda i: val_series_labels[i], key="val_series_select")
            val_series_name = val_series_opts[val_series_idx]
        
        st.markdown(f"### Product Specifications: {val_series_name}")
        
        # State management for parameters count
        if "val_param_count" not in st.session_state:
            st.session_state.val_param_count = 3
            
        val_specs = {}
        for i in range(st.session_state.val_param_count):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                p_name = st.text_input(f"Parameter Name", placeholder=f"Parameter {i+1}", key=f"val_p_name_{i}", label_visibility="collapsed")
            with c2:
                p_val = st.text_input(f"Value", placeholder=f"Value {i+1}", key=f"val_p_val_{i}", label_visibility="collapsed")
            with c3:
                # Add CSS styling implicitly by not needing extra rows
                if st.button("🗑️ Remove", key=f"val_rm_{i}"):
                    st.session_state.val_param_count -= 1
                    st.rerun()
            if p_name and p_val:
                val_specs[p_name] = p_val
                
        if st.button("➕ Add Parameter Row", key="val_add"):
            st.session_state.val_param_count += 1
            st.rerun()
            
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔍 Validate Configuration & Calculate Price", type="primary", use_container_width=True):
            if not val_specs:
                st.error("❌ Please provide at least one specification for validation.")
            else:
                with st.spinner(f"Validating configuration with AI..."):
                    try:
                        result = run_async(
                            agent.validate_configuration(
                                manufacturer=val_mfg,
                                brand=val_brand,
                                series_name=val_series_name,
                                specifications=val_specs
                            )
                        )
                        
                        st.markdown("### Validation Results")
                        
                        confidence = result.get("confidence", 0.0)
                        if confidence > 0:
                            st.progress(confidence, text=f"AI Confidence: {int(confidence * 100)}%")
                        
                        if result.get("is_valid"):
                            st.success("✅ Configuration is Valid")
                            
                            p_c1, p_c2, p_c3 = st.columns(3)
                            p_c1.metric("Total Price", f"${result.get('total_price', 0):.2f}")
                            p_c2.metric("Base Price", f"${result.get('base_price', 0):.2f}")
                            p_c3.metric("Optional Price", f"${result.get('optional_price', 0):.2f}")
                            
                            with st.expander("💰 Price Breakdown", expanded=True):
                                for item in result.get("price_breakdown", []):
                                    prc = item.get('price_impact', 0)
                                    status = "Included" if prc == 0 else f"+${prc:.2f}" if prc > 0 else f"-${abs(prc):.2f}"
                                    type_label = "🔧 Optional" if item.get("is_optional") else "📦 Base"
                                    st.write(f"- {type_label} **{item.get('parameter', '')}** ({item.get('selection', '')}): {status}")
                                    
                            if result.get("warnings"):
                                for warning in result["warnings"]:
                                    st.warning(warning)
                                    
                        else:
                            st.error("❌ Configuration is Invalid")
                            st.write(f"**Error Type:** {result.get('error_type', 'Validation Error')}")
                            
                            if result.get("errors"):
                                for err in result["errors"]:
                                    st.error(err)
                                    
                            invalid = result.get("invalid_selections", [])
                            if invalid:
                                st.markdown("#### Invalid Selections")
                                for inv in invalid:
                                    with st.expander(f"❌ {inv.get('user_spec', inv.get('parameter', ''))}"):
                                        st.write(f"**Your Value:** {inv.get('user_value', '')}")
                                        st.write(f"**Reason:** {inv.get('reason', '')}")
                                        sugg = inv.get("suggestions", inv.get("valid_options", []))
                                        if sugg:
                                            st.write("**Suggestions:**", ", ".join(str(s) for s in sugg[:10]))
                    except Exception as e:
                        st.error(f"Execution Error: {e}")
    else:
        with val_col3:
            st.warning("No series found for validation.")

st.markdown("---")
st.caption("Pricebook AI v1.0.0 • Single Page Unified App")
