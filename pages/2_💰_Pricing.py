"""
Pricebook AI - Configuration Validation & Pricing

Validate product configurations and get pricing directly
"""

import streamlit as st
import sys
import json
import asyncio
from pathlib import Path

from processor.agent_factory import get_validation_agent
from processor.db import get_db

# Page config
st.set_page_config(
    page_title="Pricing - Pricebook AI",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Header
st.title("💰 Configuration Validation & Pricing")
st.markdown("Validate product configurations and calculate pricing")
st.markdown("---")

agent = get_validation_agent()


# ------------------------------------------------------------------
# Helper: run async in streamlit
# ------------------------------------------------------------------
def run_async(coro):
    """Run an async coroutine from synchronous Streamlit code."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ------------------------------------------------------------------
# Helper: fetch manufacturers / brands / series from DB
# ------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_all_manufacturers():
    """Return sorted list of unique manufacturer names."""
    try:
        db = get_db()
        return sorted(db.get_collection("series").distinct("manufacturer"))
    except Exception:
        return []


@st.cache_data(ttl=60)
def get_brands_for_manufacturer(manufacturer: str):
    """Return sorted list of unique brands for a manufacturer."""
    try:
        db = get_db()
        brands = db.get_collection("series").distinct("brand", {"manufacturer": manufacturer})
        # Filter out None / empty
        return sorted([b for b in brands if b])
    except Exception:
        return []


@st.cache_data(ttl=60)
def get_series_for_manufacturer_brand(manufacturer: str, brand: str = None):
    """Return list of series dicts (name, category) for the given manufacturer/brand."""
    try:
        db = get_db()
        query = {"manufacturer": manufacturer}
        if brand:
            query["brand"] = brand
        cursor = db.get_collection("series").find(
            query, {"series_name": 1, "category": 1, "brand": 1, "_id": 0}
        ).sort("series_name", 1)
        return list(cursor)
    except Exception:
        return []


# Tabs
tab1, tab2 = st.tabs(["📝 Single Configuration", "📋 Available Series"])

# ============================================
# TAB 1: SINGLE CONFIGURATION VALIDATION
# ============================================

with tab1:
    st.subheader("Validate Configuration")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("### Product Information")

        # --- Manufacturer dropdown ---
        manufacturers = get_all_manufacturers()
        manufacturer = st.selectbox(
            "Manufacturer *",
            options=[""] + manufacturers,
            format_func=lambda x: "Select a manufacturer..." if x == "" else x,
        )

        # --- Brand dropdown (depends on manufacturer) ---
        brand = None
        if manufacturer:
            brands = get_brands_for_manufacturer(manufacturer)
            if brands:
                brand_selection = st.selectbox(
                    "Brand (optional)",
                    options=[""] + brands,
                    format_func=lambda x: "All brands" if x == "" else x,
                )
                brand = brand_selection if brand_selection else None
            else:
                st.caption("No brands found for this manufacturer")

        # --- Series dropdown (depends on manufacturer + brand) ---
        series_name = None
        if manufacturer:
            series_list = get_series_for_manufacturer_brand(manufacturer, brand)
            if series_list:
                series_options = [s["series_name"] for s in series_list]
                series_labels = [
                    f"{s['series_name']}  ({s.get('category', '')})" for s in series_list
                ]

                selected_idx = st.selectbox(
                    "Series Name *",
                    options=range(len(series_options)),
                    format_func=lambda i: series_labels[i],
                )
                series_name = series_options[selected_idx]
            else:
                st.warning("No series found for this manufacturer/brand combination")

    with col2:
        st.markdown("### Input Method")
        input_method = st.radio(
            "How would you like to input specifications?",
            ["Form", "JSON"],
            horizontal=True,
        )

    specifications = {}

    if input_method == "Form":
        st.markdown("### Specifications")
        st.info("Add configuration parameters and their values below")

        # Dynamic parameter input
        if "param_count" not in st.session_state:
            st.session_state.param_count = 3

        for i in range(st.session_state.param_count):
            col_param, col_value, col_remove = st.columns([2, 2, 1])
            with col_param:
                param_name = st.text_input(
                    f"Parameter {i+1}",
                    key=f"param_name_{i}",
                    placeholder="e.g., Gauge",
                )
            with col_value:
                param_value = st.text_input(
                    f"Value {i+1}",
                    key=f"param_value_{i}",
                    placeholder="e.g., 18ga",
                )
            with col_remove:
                if st.button("🗑️", key=f"remove_{i}"):
                    st.session_state.param_count -= 1
                    st.rerun()

            if param_name and param_value:
                specifications[param_name] = param_value

        if st.button("➕ Add Parameter"):
            st.session_state.param_count += 1
            st.rerun()

    else:  # JSON input
        st.markdown("### Specifications (JSON)")
        json_input = st.text_area(
            "Enter specifications as JSON",
            value='{\n  "Gauge": "18ga",\n  "Frame Configuration": "Single",\n  "Width": "3\'0\\"",\n  "Height": "7\'0\\"",\n  "Jamb Depth": "4 3/4\\""\n}',
            height=200
        )
        
        try:
            specifications = json.loads(json_input)
            st.success(f"✅ Valid JSON with {len(specifications)} specifications")
        except json.JSONDecodeError as e:
            st.error(f"❌ Invalid JSON: {e}")
    
    # Validate button
    st.markdown("---")
    if st.button("🔍 Validate Configuration", type="primary", use_container_width=True):
        if not manufacturer or not series_name:
            st.error("❌ Manufacturer and Series Name are required")
        elif not specifications:
            st.error("❌ At least one specification is required")
        else:
            with st.spinner("Validating configuration with AI agents (this may take a moment)..."):
                try:
                    result = run_async(
                        agent.validate_configuration(
                            manufacturer=manufacturer,
                            brand=brand if brand else None,
                            series_name=series_name,
                            specifications=specifications,
                        )
                    )

                    # Display results
                    st.markdown("---")
                    st.markdown("## Validation Results")

                    # Confidence & reasoning bar (always shown)
                    confidence = result.get("confidence", 0.0)
                    reasoning = result.get("reasoning", "")

                    if confidence > 0:
                        conf_pct = int(confidence * 100)
                        st.progress(confidence, text=f"AI Confidence: {conf_pct}%")

                    if reasoning:
                        with st.expander("🧠 AI Reasoning", expanded=False):
                            st.write(reasoning)

                    if result.get("is_valid"):
                        # ---- VALID CONFIGURATION ----
                        st.success("✅ Configuration is valid!")

                        # Price metrics
                        col_price1, col_price2, col_price3 = st.columns(3)
                        with col_price1:
                            st.metric("Total Price", f"${result.get('total_price', 0):.2f}")
                        with col_price2:
                            st.metric("Base Price", f"${result.get('base_price', 0):.2f}")
                        with col_price3:
                            st.metric("Optional Price", f"${result.get('optional_price', 0):.2f}")

                        # Matched specifications
                        matched = result.get("matched_specifications", [])
                        if matched:
                            st.markdown("### Matched Specifications")
                            for spec in matched:
                                with st.container():
                                    cols = st.columns([2, 2, 2, 1, 2])
                                    with cols[0]:
                                        st.write(f"**{spec.get('user_spec', '')}**")
                                    with cols[1]:
                                        st.write(f"→ {spec.get('matched_parameter', '')}")
                                    with cols[2]:
                                        st.write(spec.get("matched_option", ""))
                                    with cols[3]:
                                        price = spec.get("price_impact", 0)
                                        if price > 0:
                                            st.write(f"+${price:.2f}")
                                        elif price < 0:
                                            st.write(f"-${abs(price):.2f}")
                                        else:
                                            st.write("Included")
                                    with cols[4]:
                                        if spec.get("is_optional"):
                                            st.write("🔧 Optional")
                                        else:
                                            st.write("📦 Base")

                        # Price breakdown
                        breakdown = result.get("price_breakdown", [])
                        if breakdown:
                            st.markdown("### Price Breakdown")
                            for item in breakdown:
                                with st.container():
                                    col_param, col_sel, col_price, col_type = st.columns([3, 3, 2, 2])
                                    with col_param:
                                        st.write(f"**{item.get('parameter', '')}**")
                                    with col_sel:
                                        st.write(item.get("selection", ""))
                                    with col_price:
                                        price = item.get("price_impact", 0)
                                        if price > 0:
                                            st.write(f"+${price:.2f}")
                                        elif price < 0:
                                            st.write(f"-${abs(price):.2f}")
                                        else:
                                            st.write("Included")
                                    with col_type:
                                        if item.get("is_optional"):
                                            st.write("🔧 Optional")
                                        else:
                                            st.write("📦 Base")

                        # Notes
                        if result.get("notes"):
                            st.markdown("### Notes")
                            for note in result["notes"]:
                                st.info(note)

                        # Warnings
                        if result.get("warnings"):
                            st.markdown("### Warnings")
                            for warning in result["warnings"]:
                                st.warning(warning)

                        # Export
                        st.markdown("---")
                        st.download_button(
                            "📥 Download Configuration",
                            data=json.dumps(result, indent=2, default=str),
                            file_name=f"{manufacturer}_{series_name}_config.json",
                            mime="application/json",
                        )

                    else:
                        # ---- INVALID CONFIGURATION ----
                        st.error("❌ Configuration is invalid")

                        error_type = result.get("error_type", "Unknown error")
                        st.warning(f"**Error Type:** {error_type}")

                        # Errors
                        if result.get("errors"):
                            st.markdown("### Errors")
                            for error in result["errors"]:
                                st.error(error)

                        # Missing required parameters
                        if result.get("missing_required"):
                            st.markdown("### Missing Required Parameters")
                            for missing in result["missing_required"]:
                                param = missing.get("parameter", missing) if isinstance(missing, dict) else missing
                                with st.expander(f"⚠️ {param}"):
                                    options = missing.get("available_options", []) if isinstance(missing, dict) else []
                                    if options:
                                        st.write("**Available Options:**")
                                        st.write(", ".join(str(o) for o in options[:20]))
                                    else:
                                        st.write("No options listed")

                        # Invalid selections
                        if result.get("invalid_selections"):
                            st.markdown("### Invalid Selections")
                            for invalid in result["invalid_selections"]:
                                label = invalid.get("user_spec", invalid.get("parameter", ""))
                                with st.expander(f"❌ {label}"):
                                    st.write(f"**Your Value:** {invalid.get('user_value', invalid.get('provided_value', ''))}")
                                    reason = invalid.get("reason", "")
                                    if reason:
                                        st.write(f"**Reason:** {reason}")
                                    suggestions = invalid.get("suggestions", invalid.get("valid_options", []))
                                    if suggestions:
                                        st.write("**Suggestions:**")
                                        st.write(", ".join(str(s) for s in suggestions[:20]))

                        # Warnings
                        if result.get("warnings"):
                            st.markdown("### Warnings")
                            for warning in result["warnings"]:
                                st.warning(warning)

                        # Series-not-found suggestions
                        if result.get("suggestions"):
                            st.markdown("### Did you mean?")
                            for suggestion in result["suggestions"]:
                                st.info(
                                    f"📋 {suggestion.get('series_name')} ({suggestion.get('category')})"
                                )

                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    st.exception(e)

# ============================================
# TAB 2: AVAILABLE SERIES
# ============================================

with tab2:
    st.subheader("Browse Available Series")
    st.markdown("Find available series for configuration")

    col1, col2 = st.columns(2)

    with col1:
        tab2_manufacturers = get_all_manufacturers()
        search_manufacturer = st.selectbox(
            "Manufacturer",
            options=[""] + tab2_manufacturers,
            format_func=lambda x: "Select a manufacturer..." if x == "" else x,
            key="tab2_manufacturer",
        )
    with col2:
        search_brand = None
        if search_manufacturer:
            tab2_brands = get_brands_for_manufacturer(search_manufacturer)
            if tab2_brands:
                tab2_brand_sel = st.selectbox(
                    "Brand (optional)",
                    options=[""] + tab2_brands,
                    format_func=lambda x: "All brands" if x == "" else x,
                    key="tab2_brand",
                )
                search_brand = tab2_brand_sel if tab2_brand_sel else None

    if st.button("🔍 Search Series", type="primary"):
        if search_manufacturer:
            with st.spinner("Searching..."):
                try:
                    result = run_async(
                        agent.get_available_configurations(
                            manufacturer=search_manufacturer,
                            brand=search_brand,
                        )
                    )
                    
                    configurations = result.get("configurations", [])
                    
                    if configurations:
                        st.success(f"Found {len(configurations)} series")
                        
                        for config in configurations:
                            with st.expander(
                                f"📋 {config['series_name']} - {config['category']} ({config['parameter_count']} parameters)"
                            ):
                                st.write(f"**Series ID:** `{config['series_id']}`")
                                st.write(f"**Brand:** {config.get('brand', 'N/A')}")
                                st.write(f"**Category:** {config['category']}")
                                
                                if config.get("parameters"):
                                    st.markdown("**Sample Parameters:**")
                                    for param in config["parameters"]:
                                        param_type = "Numeric" if param.get("is_numeric") else "Options"
                                        st.write(f"- {param['name']} ({param_type}, {param['option_count']} options)")
                    else:
                        st.warning("No series found for this manufacturer")
                
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    st.exception(e)
        else:
            st.error("Manufacturer is required")
    
    # Quick stats from database
    st.markdown("---")
    st.markdown("### Database Statistics")
    
    try:
        db = get_db()
        series_collection = db.get_collection("series")
        
        total_series = series_collection.count_documents({})
        
        # Count by category
        pipeline = [
            {"$group": {"_id": "$category", "count": {"$sum": 1}}}
        ]
        category_counts = list(series_collection.aggregate(pipeline))
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Series", total_series)
        
        for idx, cat in enumerate(category_counts[:3]):
            with [col2, col3, col4][idx]:
                st.metric(cat["_id"], cat["count"])
    
    except Exception as e:
        st.warning(f"Could not load database statistics: {e}")
