"""
Monitor Page - Track jobs, files, and extracted series data

Two tabs:
1. Job Status - Monitor all extraction jobs
2. File Details - View files and their extracted series
"""

import streamlit as st
import sys
from pathlib import Path
from datetime import datetime
import time
import json

from processor.db import (
    get_job_status,
    list_jobs,
    list_files,
    get_series,
    get_series_parameters
)

st.set_page_config(
    page_title="Monitor - Pricebook AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Header
st.title("📊 Monitor Extraction Status")
st.markdown("Track extraction jobs and view extracted data")
st.markdown("---")

# Create tabs
tab1, tab2 = st.tabs(["🔄 Job Status", "📁 File Details"])

# ============================================================================
# TAB 1: JOB STATUS
# ============================================================================
with tab1:
    st.subheader("📋 Extraction Jobs")
    
    # Controls
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        auto_refresh = st.checkbox("Auto-refresh (10s)", value=False, key="job_auto_refresh")
    with col2:
        limit = st.number_input("Jobs to show", min_value=5, max_value=100, value=20, step=5)
    with col3:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    
    # Auto refresh
    if auto_refresh:
        time.sleep(10)
        st.rerun()
    
    st.markdown("---")
    
    # Search specific job
    # Auto-expand if last_job_id is set
    should_expand = bool("last_job_id" in st.session_state and st.session_state.get("last_job_id"))
    
    with st.expander("🔍 Search Specific Job", expanded=should_expand):
        col1, col2 = st.columns([4, 1])
        with col1:
            search_job_id = st.text_input(
                "Job ID",
                value=st.session_state.get("last_job_id", ""),
                placeholder="Enter job ID to search"
            )
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            search_btn = st.button("Search", use_container_width=True)
        
        # Auto-search if last_job_id was just set by View button
        should_search = search_btn or (should_expand and search_job_id)
        
        if should_search and search_job_id:
            with st.spinner("Fetching job..."):
                result = get_job_status(search_job_id)
                
                if result["status"] == "success":
                    job = result["data"]
                    
                    # Status badge
                    status = job.get("status", "unknown")
                    if status == "completed":
                        st.success(f"✅ Status: **{status.upper()}**")
                    elif status == "running":
                        st.info(f"⏳ Status: **{status.upper()}**")
                    elif status == "failed":
                        st.error(f"❌ Status: **{status.upper()}**")
                    else:
                        st.warning(f"⚠️ Status: **{status.upper()}**")
                    
                    # Job metrics
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Job ID", job.get("job_id", "N/A")[:12] + "...")
                    with col2:
                        st.metric("File ID", job.get("file_id", "N/A")[:12] + "...")
                    with col3:
                        st.metric("Session", job.get("session_id", "N/A")[:15] + "...")
                    with col4:
                        created = job.get("created_at", "")
                        if created:
                            try:
                                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                                st.metric("Started", dt.strftime("%H:%M:%S"))
                            except:
                                st.metric("Started", "N/A")
                    
                    # Workflow state
                    if job.get("state"):
                        state = job["state"]
                        
                        st.markdown("#### 📊 Workflow Progress")
                        
                        # Metrics
                        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
                        with metric_col1:
                            st.metric("Series", state.get("series_count", 0))
                        with metric_col2:
                            d = state.get("door_count", 0)
                            f = state.get("frame_count", 0)
                            h = state.get("hardware_count", 0)
                            st.metric("Categories", f"D:{d} F:{f} H:{h}")
                        with metric_col3:
                            st.metric("Parameters", state.get("total_parameters_extracted", 0))
                        with metric_col4:
                            st.metric("Optional", state.get("total_optional_parameters_extracted", 0))
                        
                        # Node status
                        st.markdown("#### 🔄 Node Progress")
                        nodes = {
                            "Upload": state.get("upload_status", "pending"),
                            "Extract": state.get("extraction_status", "pending"),
                            "Categorize": state.get("categorization_status", "pending"),
                            "Summaries": state.get("summary_extraction_status", "pending"),
                            "Parameters": state.get("parameter_extraction_status", "pending"),
                            "Optional": state.get("optional_parameter_extraction_status", "pending"),
                            "Save": state.get("save_status", "pending")
                        }
                        
                        cols = st.columns(7)
                        for idx, (name, status) in enumerate(nodes.items()):
                            with cols[idx]:
                                if status == "completed":
                                    st.success(f"✅\n{name}")
                                elif status in ["running", "in_progress"]:
                                    st.info(f"⏳\n{name}")
                                elif status == "failed":
                                    st.error(f"❌\n{name}")
                                else:
                                    st.caption(f"⚪\n{name}")
                    
                    # Full data
                    with st.expander("📄 View Full Job Data"):
                        st.json(job)
                    
                    # Clear button
                    st.markdown("---")
                    if st.button("✖️ Clear Search", use_container_width=False):
                        st.session_state["last_job_id"] = ""
                        st.rerun()
                else:
                    st.error(f"❌ {result['error']}")
    
    st.markdown("---")
    
    # All jobs table
    st.markdown("#### 📋 All Jobs")
    
    with st.spinner("Loading jobs..."):
        result = list_jobs(limit=limit)
        
        if result["status"] == "success":
            jobs = result["data"]
            
            if jobs:
                st.caption(f"Showing {len(jobs)} job(s)")
                
                # Table header
                header_cols = st.columns([2, 2, 2, 1.5, 1, 1])
                with header_cols[0]:
                    st.markdown("**Job ID**")
                with header_cols[1]:
                    st.markdown("**Filename**")
                with header_cols[2]:
                    st.markdown("**Manufacturer / Brand**")
                with header_cols[3]:
                    st.markdown("**File ID**")
                with header_cols[4]:
                    st.markdown("**Status**")
                with header_cols[5]:
                    st.markdown("**Actions**")
                
                st.markdown("---")
                
                # Job rows
                for idx, job in enumerate(jobs):
                    # Skip if not a dict
                    if not isinstance(job, dict):
                        st.warning(f"Skipping invalid job entry at index {idx}: {type(job)}")
                        continue
                    
                    cols = st.columns([2, 2, 2, 1.5, 1, 1])
                    
                    with cols[0]:
                        job_id = job.get("job_id", "N/A")
                        st.code(str(job_id), language=None)
                    with cols[1]:
                        filename = job.get("filename", "N/A")
                        st.text(str(filename))
                    with cols[2]:
                        manufacturer = job.get("manufacturer", "N/A")
                        brand = job.get("brand", "N/A")
                        st.text(f"{manufacturer} / {brand}")
                    with cols[3]:
                        file_id = job.get("file_id", "N/A")
                        st.code(str(file_id), language=None)
                    with cols[4]:
                        status = job.get("status", "unknown")
                        if status == "completed":
                            st.success("✅ Done")
                        elif status == "running":
                            st.info("⏳ Run")
                        elif status == "failed":
                            st.error("❌ Fail")
                        else:
                            st.warning(status[:6])
                    with cols[5]:
                        if st.button("👁️", key=f"view_{job.get('job_id', idx)}", use_container_width=True, help="View details"):
                            st.session_state["last_job_id"] = job.get("job_id")
                            st.rerun()
                    
                    st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)
            else:
                st.info("No jobs found")
        else:
            st.error(f"❌ Failed to load jobs: {result['error']}")

# ============================================================================
# TAB 2: FILE DETAILS
# ============================================================================
with tab2:
    st.subheader("📁 Files & Extracted Series")
    
    # Refresh button
    col1, col2, col3 = st.columns([3, 1, 1])
    with col2:
        if st.button("🔄 Refresh Files", use_container_width=True):
            st.rerun()
    
    st.markdown("---")
    
    # Load files
    with st.spinner("Loading files..."):
        files_result = list_files()
        
        if files_result["status"] == "success":
            files = files_result["data"]
            
            if files:
                st.success(f"Found {len(files)} file(s)")
                
                # Table header
                header_cols = st.columns([2.5, 2, 2, 1.5, 1])
                with header_cols[0]:
                    st.markdown("**Filename**")
                with header_cols[1]:
                    st.markdown("**Manufacturer**")
                with header_cols[2]:
                    st.markdown("**Brand**")
                with header_cols[3]:
                    st.markdown("**Status**")
                with header_cols[4]:
                    st.markdown("**Action**")
                
                st.markdown("---")
                
                # Display each file as table row
                for idx, file in enumerate(files):
                    file_id = file.get("file_id", file.get("_id", f"file_{idx}"))
                    
                    cols = st.columns([2.5, 2, 2, 1.5, 1])
                    
                    with cols[0]:
                        st.text(file.get('filename', 'Unknown'))
                    with cols[1]:
                        st.text(file.get('manufacturer', 'N/A'))
                    with cols[2]:
                        st.text(file.get('brand', 'N/A'))
                    with cols[3]:
                        status = file.get("extraction_status", file.get("status", "unknown"))
                        if status == "completed":
                            st.success("✅ Done")
                        elif status == "processing":
                            st.info("⏳ Process")
                        else:
                            st.warning(status[:8])
                    with cols[4]:
                        if st.button("👁️", key=f"view_file_{file_id}", use_container_width=True, help="View details"):
                            st.session_state["selected_file_id"] = file_id
                            st.session_state["selected_file_data"] = file
                            st.rerun()
                    
                    st.markdown("<hr style='margin: 3px 0;'>", unsafe_allow_html=True)
                
                # File details section at bottom
                st.markdown("---")
                st.markdown("---")
                
                # Show file details if a file is selected
                if st.session_state.get("selected_file_id") and st.session_state.get("selected_file_data"):
                    selected_file_id = st.session_state["selected_file_id"]
                    file = st.session_state["selected_file_data"]
                    
                    st.markdown("### 📄 Selected File Details")
                    
                    with st.container():
                        # File basic info
                        st.markdown("#### 📋 File Information")
                        
                        detail_col1, detail_col2 = st.columns([2, 1])
                        
                        with detail_col1:
                            st.write(f"**File ID:** `{selected_file_id}`")
                            st.write(f"**Filename:** {file.get('filename', 'N/A')}")
                            st.write(f"**Manufacturer:** {file.get('manufacturer', 'N/A')}")
                            st.write(f"**Brand:** {file.get('brand', 'N/A')}")
                            
                            status = file.get("extraction_status", file.get("status", "unknown"))
                            if status == "completed":
                                st.success(f"**Status:** ✅ {status}")
                            elif status == "processing":
                                st.info(f"**Status:** ⏳ {status}")
                            else:
                                st.warning(f"**Status:** {status}")
                        
                        with detail_col2:
                            series_count = file.get("series_count", 0)
                            st.metric("Series Count", series_count)
                            
                            # Export to JSON button
                            if st.button("📥 Export to JSON", key="export_file_json", use_container_width=True):
                                st.session_state["export_file_triggered"] = selected_file_id
                            
                            if st.button("✖️ Close Details", key="close_file_details", type="secondary", use_container_width=True):
                                st.session_state["selected_file_id"] = None
                                st.session_state["selected_file_data"] = None
                                st.rerun()
                        
                        # Handle export if triggered
                        if st.session_state.get("export_file_triggered") == selected_file_id:
                            import json
                            from datetime import datetime
                            
                            with st.spinner("Preparing export data..."):
                                export_data = {
                                    "export_timestamp": datetime.now().isoformat(),
                                    "file_info": {
                                        "file_id": selected_file_id,
                                        "filename": file.get('filename', 'N/A'),
                                        "manufacturer": file.get('manufacturer', 'N/A'),
                                        "brand": file.get('brand', 'N/A'),
                                        "status": file.get("extraction_status", file.get("status", "unknown")),
                                        "series_count": file.get("series_count", 0),
                                        "door_count": file.get("door_count", 0),
                                        "frame_count": file.get("frame_count", 0),
                                        "hardware_count": file.get("hardware_count", 0),
                                        "parameter_count": file.get("parameter_count", 0),
                                        "rules": file.get("rules", "")
                                    },
                                    "series": []
                                }
                                
                                # Fetch all series for this file
                                series_result = get_series(file_id=selected_file_id)
                                
                                if series_result["status"] == "success":
                                    series_list = series_result["data"].get("series", [])
                                    
                                    # For each series, fetch parameters
                                    for series in series_list:
                                        series_data = {
                                            "series_id": series.get("_id"),
                                            "series_name": series.get("series_name"),
                                            "category": series.get("category"),
                                            "summary": series.get("summary", ""),
                                            "parameter_count": series.get("parameter_count", 0),
                                            "optional_parameter_count": series.get("optional_parameter_count", 0),
                                            "parameters": [],
                                            "optional_parameters": []
                                        }
                                        
                                        # Fetch parameters for this series
                                        series_id = series.get("_id")
                                        if series_id:
                                            params_result = get_series_parameters(series_id)
                                            if params_result["status"] == "success":
                                                params_data = params_result["data"]
                                                series_data["parameters"] = params_data.get("parameters", [])
                                                series_data["optional_parameters"] = params_data.get("optional_parameters", [])
                                        
                                        export_data["series"].append(series_data)
                                
                                # Create JSON string
                                json_str = json.dumps(export_data, indent=2, ensure_ascii=False)
                                
                                # Create filename
                                safe_filename = file.get('filename', 'export').replace('.pdf', '').replace(' ', '_')
                                download_filename = f"{safe_filename}_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                                
                                # Download button
                                st.download_button(
                                    label="⬇️ Download JSON",
                                    data=json_str,
                                    file_name=download_filename,
                                    mime="application/json",
                                    use_container_width=True,
                                    key="download_json_button"
                                )
                                
                                st.success(f"✅ Export ready! {len(export_data['series'])} series included.")
                                
                                # Clear trigger after showing download button
                                if st.button("Done", key="clear_export_trigger"):
                                    st.session_state["export_file_triggered"] = None
                                    st.rerun()
                        
                        # File stats
                        if file.get("door_count") or file.get("frame_count") or file.get("hardware_count"):
                            st.markdown("#### 📊 Category Breakdown")
                            stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
                            with stat_col1:
                                st.metric("🚪 Doors", file.get("door_count", 0))
                            with stat_col2:
                                st.metric("🖼️ Frames", file.get("frame_count", 0))
                            with stat_col3:
                                st.metric("🔧 Hardware", file.get("hardware_count", 0))
                            with stat_col4:
                                total_params = file.get("parameter_count", 0)
                                st.metric("Parameters", total_params)
                        
                        # Extraction rules
                        if file.get("rules"):
                            st.markdown("#### 📋 Extraction Rules")
                            st.info(file.get("rules"))
                        
                        st.markdown("---")
                        
                        # Series list (only if completed)
                        series_count = file.get("series_count", 0)
                        status = file.get("extraction_status", file.get("status", "unknown"))
                        if status == "completed" and series_count > 0:
                            st.markdown("#### 📋 Extracted Series")
                            
                            if st.button("📥 Load Series for this file", key=f"load_series_{selected_file_id}"):
                                st.session_state[f"series_loaded_{selected_file_id}"] = True
                            
                            # Load series if requested
                            if st.session_state.get(f"series_loaded_{selected_file_id}", False):
                                with st.spinner("Loading series..."):
                                    series_result = get_series(file_id=selected_file_id)
                                    
                                    if series_result["status"] == "success":
                                        series_list = series_result["data"].get("series", [])
                                        
                                        if series_list:
                                            # Series table
                                            for idx, series in enumerate(series_list):
                                                    with st.container():
                                                        st.markdown("---")
                                                        
                                                        # Series header
                                                        col1, col2, col3 = st.columns([3, 1, 1])
                                                        with col1:
                                                            st.markdown(f"### {series.get('series_name', 'Unknown')}")
                                                            st.caption(f"Pages: {series.get('pages', [])}")
                                                        with col2:
                                                            category = series.get('category', 'N/A')
                                                            if category == "DOOR":
                                                                st.info("🚪 DOOR")
                                                            elif category == "FRAME":
                                                                st.info("🖼️ FRAME")
                                                            elif category == "HARDWARE":
                                                                st.info("🔧 HARDWARE")
                                                            else:
                                                                st.caption(category)
                                                        with col3:
                                                            params = series.get("parameter_count", 0)
                                                            optional = series.get("optional_parameter_count", 0)
                                                            st.metric("Parameters", f"{params} + {optional}")
                                                        
                                                        # Summary
                                                        summary = series.get('summary', '')
                                                        if summary:
                                                            st.markdown("**Summary:**")
                                                            # Display summary in a text area for better formatting
                                                            st.text_area(
                                                                "Series Summary",
                                                                value=summary,
                                                                height=100,
                                                                disabled=True,
                                                                label_visibility="collapsed"
                                                            )
                                                        
                                                        # Load parameters for this series
                                                        series_id = series.get('_id')
                                                        if series_id:
                                                            with st.spinner("Loading parameters..."):
                                                                params_result = get_series_parameters(series_id)
                                                                
                                                                # Debug: Show actual response
                                                                if params_result["status"] != "success":
                                                                    st.error(f"Error: {params_result.get('error', 'Unknown error')}")
                                                                    st.json(params_result)
                                                                
                                                                if params_result["status"] == "success":
                                                                    params_data = params_result["data"]
                                                                    base_params = params_data.get("parameters", [])
                                                                    optional_params = params_data.get("optional_parameters", [])
                                                                    
                                                                    # Show base parameters
                                                                    if base_params:
                                                                        st.markdown("**🔧 Parameters:**")
                                                                        
                                                                        for param in base_params:
                                                                            param_name = param.get('parameter_name', 'Unknown')
                                                                            options = param.get('options', [])
                                                                            option_count = len(options) if options else 0
                                                                            
                                                                            with st.expander(f"📋 {param_name} ({option_count} options)", expanded=False):
                                                                                # Show parameter description and notes
                                                                                param_desc = param.get('description', '')
                                                                                param_notes = param.get('notes', param.get('note', ''))
                                                                                
                                                                                if param_desc:
                                                                                    st.markdown(f"**Description:** {param_desc}")
                                                                                if param_notes:
                                                                                    st.markdown(f"**Notes:** {param_notes}")
                                                                                
                                                                                if param_desc or param_notes:
                                                                                    st.markdown("---")
                                                                                
                                                                                if options:
                                                                                    st.markdown("**Options:**")
                                                                                    for idx, opt in enumerate(options):
                                                                                        opt_name = opt.get('option_name', opt.get('name', 'N/A'))
                                                                                        opt_desc = opt.get('description', opt.get('desc', ''))
                                                                                        opt_notes = opt.get('notes', opt.get('note', ''))
                                                                                        
                                                                                        # Build option display
                                                                                        st.markdown(f"**{idx + 1}. {opt_name}**")
                                                                                        
                                                                                        if opt_desc:
                                                                                            st.markdown(f"   *Description:* {opt_desc}")
                                                                                        if opt_notes:
                                                                                            st.markdown(f"   *Notes:* {opt_notes}")
                                                                                        
                                                                                        # Add spacing between options
                                                                                        if idx < len(options) - 1:
                                                                                            st.markdown("")
                                                                                else:
                                                                                    st.info("No options defined")
                                                                
                                                                    # Show optional parameters
                                                                    if optional_params:
                                                                        st.markdown("**✨ Optional Parameters:**")
                                                                        
                                                                        for param in optional_params:
                                                                            param_name = param.get('parameter_name', 'Unknown')
                                                                            options = param.get('options', [])
                                                                            option_count = len(options) if options else 0
                                                                            
                                                                            with st.expander(f"📋 {param_name} ({option_count} options)", expanded=False):
                                                                                # Show parameter description and notes
                                                                                param_desc = param.get('description', '')
                                                                                param_notes = param.get('notes', param.get('note', ''))
                                                                                
                                                                                if param_desc:
                                                                                    st.markdown(f"**Description:** {param_desc}")
                                                                                if param_notes:
                                                                                    st.markdown(f"**Notes:** {param_notes}")
                                                                                
                                                                                if param_desc or param_notes:
                                                                                    st.markdown("---")
                                                                                
                                                                                if options:
                                                                                    st.markdown("**Options:**")
                                                                                    for idx, opt in enumerate(options):
                                                                                        opt_name = opt.get('option_name', opt.get('name', 'N/A'))
                                                                                        opt_desc = opt.get('description', opt.get('desc', ''))
                                                                                        opt_notes = opt.get('notes', opt.get('note', ''))
                                                                                        
                                                                                        # Build option display
                                                                                        st.markdown(f"**{idx + 1}. {opt_name}**")
                                                                                        
                                                                                        if opt_desc:
                                                                                            st.markdown(f"   *Description:* {opt_desc}")
                                                                                        if opt_notes:
                                                                                            st.markdown(f"   *Notes:* {opt_notes}")
                                                                                        
                                                                                        # Add spacing between options
                                                                                        if idx < len(options) - 1:
                                                                                            st.markdown("")
                                                                                else:
                                                                                    st.info("No options defined")
                                                                
                                                                    # Show message if no parameters at all
                                                                    if not base_params and not optional_params:
                                                                        st.info("No parameters found for this series")
                                        else:
                                            st.info("No series found for this file")
                                    else:
                                        st.error(f"Failed to load series: {series_result['error']}")
                        elif status != "completed":
                            st.info("⏳ File is still processing. Series will be available once completed.")
                        else:
                            st.info("No series extracted for this file")
            else:
                st.info("No files found. Upload a PDF to get started.")
        else:
            st.error(f"❌ Failed to load files: {files_result['error']}")

st.markdown("---")
st.caption("Pricebook AI v1.0.0 • Monitor Page")