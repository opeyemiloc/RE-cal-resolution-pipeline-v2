import streamlit as st
import os
import json
import pandas as pd
import io
from src.ingestion.universal_parser import parse_user_driven_excel
from src.ingestion.parsers.master_parser import ingest_master_list_excel
from src.pipeline import run_resolution_pipeline
from src.core.config import config
from src.workspace import create_empty_workspace_template, load_workspace, update_workspace, create_master_template, create_manifest_template

# --- PAGE SETUP ---
st.set_page_config(page_title="Logistics AI Matcher", page_icon="🚢", layout="wide")

st.title("🚢 AI Logistics Name Matcher")
st.markdown("""
Upload a **Master Accounts List** and a **Shipping Manifest (e.g., MSC, Hapag-Lloyd)**. 
The system will automatically extract, clean, route, and match the consignee names!
""")

# --- SESSION STATE INITIALIZATION ---
if 'master_file_bytes' not in st.session_state:
    st.session_state.master_file_bytes = None
    st.session_state.master_file_name = None
if 'manifest_file_bytes' not in st.session_state:
    st.session_state.manifest_file_bytes = None
    st.session_state.manifest_file_name = None
if 'workspace_bytes' not in st.session_state:
    st.session_state.workspace_bytes = None
if 'workspace_name' not in st.session_state:
    st.session_state.workspace_name = None
if 'workspace_aliases' not in st.session_state:
    st.session_state.workspace_aliases = {}
    
if 'vessel_name' not in st.session_state:
    st.session_state.vessel_name = ""
if 'eta' not in st.session_state:
    import datetime
    st.session_state.eta = datetime.date.today()
    
# Config state
if 'sheet_name' not in st.session_state: st.session_state.sheet_name = 0
if 'header_row_index' not in st.session_state: st.session_state.header_row_index = 0
if 'skip_sub_header' not in st.session_state: st.session_state.skip_sub_header = False
if 'bl_col' not in st.session_state: st.session_state.bl_col = ""
if 'container_col' not in st.session_state: st.session_state.container_col = ""
if 'consignee_col' not in st.session_state: st.session_state.consignee_col = ""
if 'notify_col' not in st.session_state: st.session_state.notify_col = ""
if 'product_col' not in st.session_state: st.session_state.product_col = ""
if 'salvage_notify' not in st.session_state: st.session_state.salvage_notify = True
if 'strip_bank_prefixes' not in st.session_state: st.session_state.strip_bank_prefixes = True

if 'master_name_col' not in st.session_state: st.session_state.master_name_col = ""
if 'master_alias_col' not in st.session_state: st.session_state.master_alias_col = ""
if 'master_sheet_name' not in st.session_state: st.session_state.master_sheet_name = 0
if 'master_header_row_index' not in st.session_state: st.session_state.master_header_row_index = 0

# Advanced Config State
if 'adv_vector_threshold' not in st.session_state: st.session_state.adv_vector_threshold = config['thresholds']['vector_quality_threshold']
if 'adv_top_k' not in st.session_state: st.session_state.adv_top_k = config['thresholds'].get('vector_k_candidates', 3)
if 'adv_suffix_words' not in st.session_state: st.session_state.adv_suffix_words = ", ".join(config['business_logic']['suffix_words'])
if 'adv_junk_patterns' not in st.session_state: st.session_state.adv_junk_patterns = ", ".join(config['business_logic']['junk_patterns'])
if 'adv_bank_keywords' not in st.session_state: st.session_state.adv_bank_keywords = ", ".join(config['business_logic']['bank_keywords'])
if 'adv_llm_model' not in st.session_state: st.session_state.adv_llm_model = config['llm'].get('gemini', {}).get('model_name', 'gemini-3.6-flash')

# Navigation state
if 'current_page' not in st.session_state:
    st.session_state.current_page = "1. File Uploads"

def set_page(page_name):
    st.session_state.current_page = page_name

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.title("Navigation")
    
    st.button("📁 1. File Uploads", 
              use_container_width=True, 
              type="primary" if st.session_state.current_page == "1. File Uploads" else "secondary",
              on_click=set_page, args=("1. File Uploads",))
              
    st.button("⚙️ 2. Data Configuration", 
              use_container_width=True, 
              type="primary" if st.session_state.current_page == "2. Data Configuration" else "secondary",
              on_click=set_page, args=("2. Data Configuration",))
              
    st.button("🚀 3. Run Pipeline", 
              use_container_width=True, 
              type="primary" if st.session_state.current_page == "3. Run Pipeline" else "secondary",
              on_click=set_page, args=("3. Run Pipeline",))
              
    st.button("🛠️ 4. Advanced Settings", 
              use_container_width=True, 
              type="primary" if st.session_state.current_page == "4. Advanced Settings" else "secondary",
              on_click=set_page, args=("4. Advanced Settings",))

menu = st.session_state.current_page

# Helper to safely get index
def get_idx(options, val):
    return options.index(val) if val in options else 0

# ==========================================
# SECTION 1: FILE UPLOADS
# ==========================================
if menu == "1. File Uploads":
    st.header("📁 1. File Uploads")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("1. Master List")
        master_file = st.file_uploader("Upload Master Accounts (Excel)", type=["xlsx"])
        if master_file:
            st.session_state.master_file_bytes = master_file.getvalue()
            st.session_state.master_file_name = master_file.name
        elif st.session_state.master_file_name:
            st.success(f"Loaded: {st.session_state.master_file_name}")
        st.markdown("<br>", unsafe_allow_html=True)
        st.download_button(
            label="📥 Download Multi-User Master Template",
            data=create_master_template(),
            file_name="Master_Accounts_Template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Download an example multi-tab master accounts file (OPE, MICHEAL, NNEOMA)."
        )
            
    with col2:
        st.subheader("2. Shipping Manifest")
        manifest_file = st.file_uploader("Upload Shipping Manifest (Excel)", type=["xlsx"])
        if manifest_file:
            st.session_state.manifest_file_bytes = manifest_file.getvalue()
            st.session_state.manifest_file_name = manifest_file.name
        elif st.session_state.manifest_file_name:
            st.success(f"Loaded: {st.session_state.manifest_file_name}")
        st.markdown("<br>", unsafe_allow_html=True)
        st.download_button(
            label="📥 Download Multi-Carrier Manifest Template",
            data=create_manifest_template(),
            file_name="Multi_Carrier_Manifest_Template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Download an example multi-carrier manifest file (MSC, Hapag-Lloyd, ONE)."
        )

    with col3:
        st.subheader("3. Portable Workspace (Optional)")
        workspace_file = st.file_uploader("Upload Workspace (Excel)", type=["xlsx"])
        if workspace_file:
            st.session_state.workspace_bytes = workspace_file.getvalue()
            st.session_state.workspace_name = workspace_file.name
            
            # Extract aliases and settings automatically
            aliases, settings, _ = load_workspace(st.session_state.workspace_bytes, target_user=str(st.session_state.master_sheet_name))
            st.session_state.workspace_aliases = aliases
            if settings:
                if "vector_threshold" in settings: st.session_state.adv_vector_threshold = float(settings["vector_threshold"])
                if "top_k" in settings: st.session_state.adv_top_k = int(settings["top_k"])
                if "suffix_words" in settings: st.session_state.adv_suffix_words = str(settings["suffix_words"])
                if "junk_patterns" in settings: st.session_state.adv_junk_patterns = str(settings["junk_patterns"])
                if "bank_keywords" in settings: st.session_state.adv_bank_keywords = str(settings["bank_keywords"])
                if "llm_model" in settings: st.session_state.adv_llm_model = str(settings["llm_model"])
                st.toast("✅ Workspace loaded successfully! Settings and Aliases applied.")
                
        elif st.session_state.workspace_name:
            st.success(f"Loaded: {st.session_state.workspace_name}")
            st.info(f"Active Aliases: {len(st.session_state.workspace_aliases)}")
            
        st.markdown("<br>", unsafe_allow_html=True)
        st.download_button(
            label="📥 Download Empty Workspace Template",
            data=create_empty_workspace_template(),
            file_name="Workspace_Template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Download a clean workspace file to start saving aliases and settings."
        )

    st.divider()
    st.subheader("4. Shipment Details (Used for Export)")
    col_sd1, col_sd2 = st.columns(2)
    with col_sd1:
        st.session_state.vessel_name = st.text_input("Vessel Name", value=st.session_state.vessel_name)
    with col_sd2:
        st.session_state.eta = st.date_input("ETA", value=st.session_state.eta)


# ==========================================
# SECTION 2: DATA CONFIGURATION & MAPPING
# ==========================================
elif menu == "2. Data Configuration":
    st.header("⚙️ 2. Data Configuration & Mapping")
    
    # 1. Master List Config
    if not st.session_state.master_file_bytes:
        st.warning("⚠️ Please upload a Master Accounts List in the 'File Uploads' section.")
    else:
        st.subheader("Master Accounts Structural Configuration")
        col_ms1, col_ms2, col_ms3 = st.columns(3)
        
        master_io = io.BytesIO(st.session_state.master_file_bytes)
        master_excel = pd.ExcelFile(master_io)
        
        with col_ms1:
            st.session_state.master_sheet_name = st.selectbox("Master Target Sheet", master_excel.sheet_names, index=get_idx(master_excel.sheet_names, st.session_state.master_sheet_name))
            if st.session_state.workspace_bytes:
                st.session_state.workspace_aliases, _, _ = load_workspace(st.session_state.workspace_bytes, target_user=str(st.session_state.master_sheet_name))
        with col_ms2:
            st.session_state.master_header_row_index = int(st.number_input("Master Header Row Index (0-indexed)", min_value=0, value=st.session_state.master_header_row_index))
        with col_ms3:
            st.write("")
            
        st.divider()
        st.subheader("Master List Column Mapping")
        try:
            master_io.seek(0)
            df_master_preview = pd.read_excel(master_io, sheet_name=st.session_state.master_sheet_name, header=st.session_state.master_header_row_index, nrows=5)
            master_cols = [str(c) for c in df_master_preview.columns.tolist()]
            
            st.write("**Live Preview:**")
            st.dataframe(df_master_preview.head(3), use_container_width=True)
            
            col_ma1, col_ma2 = st.columns(2)
            with col_ma1:
                st.session_state.master_name_col = st.selectbox("Account Name Column (Required)", [""] + master_cols, index=get_idx([""] + master_cols, st.session_state.master_name_col))
            with col_ma2:
                st.session_state.master_alias_col = st.selectbox("Alias Name Column (Optional)", ["None"] + master_cols, index=get_idx(["None"] + master_cols, st.session_state.master_alias_col))
        except Exception as e:
            st.error(f"Error reading master list preview: {e}")
            
        st.divider()

    # 2. Manifest Config
    if not st.session_state.manifest_file_bytes:
        st.warning("⚠️ Please upload a Shipping Manifest in the 'File Uploads' section.")
    else:
        st.subheader("Manifest Structural Configuration")
        col_s1, col_s2, col_s3 = st.columns(3)
        
        manifest_io = io.BytesIO(st.session_state.manifest_file_bytes)
        excel_file = pd.ExcelFile(manifest_io)
        
        with col_s1:
            st.session_state.sheet_name = st.selectbox("Target Sheet", excel_file.sheet_names, index=get_idx(excel_file.sheet_names, st.session_state.sheet_name))
        with col_s2:
            st.session_state.header_row_index = int(st.number_input("Header Row Index (0-indexed)", min_value=0, value=st.session_state.header_row_index))
        with col_s3:
            st.write("")
            st.write("")
            st.session_state.skip_sub_header = st.checkbox("Skip Sub-header Row", value=st.session_state.skip_sub_header)
        
        st.divider()
        st.subheader("Manifest Column Mapping")
        try:
            manifest_io.seek(0)
            df_preview = pd.read_excel(manifest_io, sheet_name=st.session_state.sheet_name, header=st.session_state.header_row_index, nrows=5)
            columns = [str(c) for c in df_preview.columns.tolist()]
            
            st.write("**Live Preview:**")
            st.dataframe(df_preview.head(3), use_container_width=True)

            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                st.session_state.bl_col = st.selectbox("🔴 Bill of Lading (Required)", [""] + columns, index=get_idx([""] + columns, st.session_state.bl_col))
            with col_m2:
                st.session_state.container_col = st.selectbox("🔴 Container Number (Required)", [""] + columns, index=get_idx([""] + columns, st.session_state.container_col))
            with col_m3:
                st.session_state.consignee_col = st.selectbox("🔴 Consignee Name (Required)", [""] + columns, index=get_idx([""] + columns, st.session_state.consignee_col))
                
            col_m4, col_m5 = st.columns(2)
            with col_m4:
                st.session_state.notify_col = st.selectbox("🟡 Notify Party (Optional)", ["None"] + columns, index=get_idx(["None"] + columns, st.session_state.notify_col))
            with col_m5:
                st.session_state.product_col = st.selectbox("🟡 Product/Cargo (Optional)", ["None"] + columns, index=get_idx(["None"] + columns, st.session_state.product_col))
        except Exception as e:
            st.error(f"Error reading preview: {e}")

        st.divider()
        st.subheader("Business Logic Toggles")
        st.session_state.salvage_notify = st.checkbox("Fallback to Notify Party if Consignee is empty", value=st.session_state.salvage_notify)
        st.session_state.strip_bank_prefixes = st.checkbox("Clean bank prefixes ('TO THE ORDER OF...')", value=st.session_state.strip_bank_prefixes)


# ==========================================
# SECTION 4: ADVANCED SETTINGS
# ==========================================
elif menu == "4. Advanced Settings":
    st.header("🛠️ 4. Advanced Settings (Control Center)")
    
    tab1, tab2, tab3 = st.tabs(["🎯 Matching & Threshold Tuning", "🧹 Business Logic & Cleaning", "🤖 LLM Settings"])
    
    with tab1:
        st.subheader("Entity Resolution Thresholds")
        st.session_state.adv_vector_threshold = st.slider(
            "Vector Similarity Score Threshold", 
            min_value=0.0, max_value=1.0, 
            value=float(st.session_state.adv_vector_threshold), 
            step=0.05, 
            help="Controls FAISS strictness. Lower is stricter. Candidates with distance > threshold are rejected."
        )
        st.session_state.adv_top_k = st.number_input(
            "Top-K Candidates", 
            min_value=1, max_value=10, 
            value=int(st.session_state.adv_top_k), 
            help="How many candidate matches are retrieved from the Master List for LLM evaluation."
        )
        
    with tab2:
        st.subheader("Dynamic Cleaning Rules")
        st.info("Enter comma-separated values.")
        st.session_state.adv_suffix_words = st.text_area(
            "Custom Suffix Removal List", 
            value=st.session_state.adv_suffix_words, 
            help="Legal suffixes stripped during normalization (e.g. LTD, PLC, INC, LIMITED, ENTERPRISES)."
        )
        st.session_state.adv_junk_patterns = st.text_area(
            "Custom Junk Phrase Filter", 
            value=st.session_state.adv_junk_patterns, 
            help="Phrases that trigger automatic 'Junk/Unusable Name' rejection (e.g., TO ORDER, SAME AS NOTIFY)."
        )
        st.session_state.adv_bank_keywords = st.text_area(
            "Custom Bank Prefix Cleaning", 
            value=st.session_state.adv_bank_keywords, 
            help="Banking phrases to strip out before matching (e.g., TO THE ORDER OF, LETTER OF CREDIT)."
        )
        
    with tab3:
        st.subheader("AI Model Selection")
        model_options = ["gemini-3.6-flash", "gemini-3.5-flash"]
        format_mapping = {
            "gemini-3.6-flash": "Gemini 3.6 Flash",
            "gemini-3.5-flash": "Gemini 3.5 Flash"
        }
        st.session_state.adv_llm_model = st.selectbox(
            "Select LLM", 
            model_options, 
            format_func=lambda x: format_mapping.get(x, x),
            index=get_idx(model_options, st.session_state.adv_llm_model)
        )


# ==========================================
# SECTION 3: RUN PIPELINE
# ==========================================
elif menu == "3. Run Pipeline":
    st.header("🚀 3. Run Pipeline")
    
    if not st.session_state.master_file_bytes or not st.session_state.manifest_file_bytes:
        st.warning("⚠️ Please upload both Excel files in the 'File Uploads' section before running.")
    elif not st.session_state.bl_col or not st.session_state.container_col or not st.session_state.consignee_col:
        st.warning("⚠️ Please map all Required Columns (BL, Container, Consignee) in the 'Data Configuration' section before running.")
    else:
        run_btn = st.button("Run Resolution Pipeline", type="primary", use_container_width=True)
        
        if run_btn:
            with st.spinner("Processing pipeline..."):
                try:
                    # --- INJECT CUSTOM USER CONFIGURATIONS ---
                    config['thresholds']['vector_quality_threshold'] = st.session_state.adv_vector_threshold
                    config['thresholds']['vector_k_candidates'] = st.session_state.adv_top_k
                    config['business_logic']['suffix_words'] = [s.strip() for s in st.session_state.adv_suffix_words.split(",") if s.strip()]
                    config['business_logic']['junk_patterns'] = [s.strip() for s in st.session_state.adv_junk_patterns.split(",") if s.strip()]
                    config['business_logic']['bank_keywords'] = [s.strip() for s in st.session_state.adv_bank_keywords.split(",") if s.strip()]
                    
                    if 'gemini' not in config['llm']: config['llm']['gemini'] = {}
                    
                    config['llm']['gemini']['model_name'] = st.session_state.adv_llm_model
                    config['llm']['provider'] = 'gemini'
                    
                    # 1. Save uploaded files to the input directory temporarily
                    os.makedirs(config['paths']['input_dir'], exist_ok=True)
                    
                    master_path = os.path.join(config['paths']['input_dir'], st.session_state.master_file_name)
                    manifest_path = os.path.join(config['paths']['input_dir'], st.session_state.manifest_file_name)
                    
                    with open(master_path, "wb") as f:
                        f.write(st.session_state.master_file_bytes)
                    with open(manifest_path, "wb") as f:
                        f.write(st.session_state.manifest_file_bytes)

                    # 2. Run Master Parser (With User Mapping)
                    master_json_path = config['paths']['master_json']
                    ingest_master_list_excel(
                        excel_path=master_path, 
                        output_json_path=master_json_path,
                        name_col=st.session_state.master_name_col if st.session_state.master_name_col != "None" else None,
                        alias_col=st.session_state.master_alias_col if st.session_state.master_alias_col != "None" else None,
                        sheet_name=st.session_state.master_sheet_name,
                        header_row_index=st.session_state.master_header_row_index
                    )

                    # 3. Parse Manifest & Extract Unique BLs
                    column_mapping = {
                        "bl_number": st.session_state.bl_col,
                        "container_number": st.session_state.container_col,
                        "consignee_name": st.session_state.consignee_col,
                        "notify_party": st.session_state.notify_col if st.session_state.notify_col != "None" else None,
                        "product_description": st.session_state.product_col if st.session_state.product_col != "None" else None
                    }
                    
                    raw_records = parse_user_driven_excel(
                        file_source=manifest_path,
                        sheet_name=st.session_state.sheet_name,
                        header_row_index=st.session_state.header_row_index,
                        skip_sub_header=st.session_state.skip_sub_header,
                        column_mapping=column_mapping,
                        salvage_notify=st.session_state.salvage_notify,
                        strip_bank_prefixes=st.session_state.strip_bank_prefixes
                    )
                    
                    unique_bls = {r.bill_of_lading: r for r in raw_records if r.bill_of_lading}.values()
                    bl_level_records = list(unique_bls)

                    # --- EXECUTE EXTRACTED PIPELINE ---
                    ui_placeholder = st.empty()
                    
                    def pipeline_update_hook(status: str, data: dict):
                        if status == "deterministic_complete":
                            with ui_placeholder.container():
                                st.info("✅ Deterministic matching complete! AI Resolution starting...")
                                st.subheader("Deterministic Decisions")
                                deterministic = data["exact_matches"] + data["auto_rejected"]
                                if deterministic:
                                    st.dataframe([json.loads(d.model_dump_json()) for d in deterministic], use_container_width=True)
                                st.subheader("Ambiguous Records (Waiting for AI Queue)")
                                if data["candidates"]:
                                    st.dataframe([json.loads(c.model_dump_json()) for c in data["candidates"]], use_container_width=True)
                        elif status == "llm_start":
                            st.toast(f"🧠 Running AI Resolution on {data['count']} ambiguous records...")
                        elif status == "pipeline_complete":
                            ui_placeholder.empty()

                    if st.session_state.workspace_bytes:
                        st.session_state.workspace_aliases, _, _ = load_workspace(st.session_state.workspace_bytes, target_user=str(st.session_state.master_sheet_name))

                    results = run_resolution_pipeline(
                        records=bl_level_records, 
                        master_json_path=master_json_path,
                        custom_aliases=st.session_state.workspace_aliases,
                        ui_callback=pipeline_update_hook
                    )
                    
                    # Store results in session_state
                    st.session_state.raw_records = raw_records
                    st.session_state.bl_level_records = bl_level_records
                    st.session_state.exact_matches = results["exact_matches"]
                    st.session_state.auto_rejected = results["auto_rejected"]
                    st.session_state.candidates = results["candidates"]
                    st.session_state.llm_decisions = results["llm_decisions"]
                    st.session_state.final_decisions = results["final_decisions"]
                    st.session_state.pipeline_ran = True
                    
                    st.success("✅ Pipeline Complete!")
                except Exception as e:
                    st.error(f"Pipeline failed: {str(e)}")

    # --- DISPLAY RESULTS & WORKSPACE LEARNING ---
    if st.session_state.get('pipeline_ran', False):
        st.header("📊 Pipeline Analytics & Active Learning")
        
        # Metrics Dashboard
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Unique BLs", len(st.session_state.bl_level_records))
        col2.metric("🟢 Exact Matches", len(st.session_state.exact_matches))
        col3.metric("🔴 Auto-Rejected (Junk)", len(st.session_state.auto_rejected))
        col4.metric("🤖 AI Matches", len(st.session_state.llm_decisions))
        st.divider()
        res_tab1, res_tab2 = st.tabs(["👀 Resolution Preview & AI Queue", "📈 Interactive Reporting Tab"])
        
        with res_tab1:
            st.subheader("🔍 Click a row in any table below to view its original manifest records")

            def show_drilldown(selection_event, dataframe, key_col):
                if selection_event and selection_event.selection.rows:
                    idx = selection_event.selection.rows[0]
                    messy_name = dataframe.iloc[idx][key_col]
                    matching_records = [r for r in st.session_state.get('raw_records', st.session_state.bl_level_records) if r.messy_party_name == messy_name]
                    df_drill = pd.DataFrame([{
                        "Bill of Lading": r.bill_of_lading,
                        "Container": r.container_number,
                        "Messy Name": r.messy_party_name,
                        "Notify Party": r.notify_party,
                        "Role": r.party_role
                    } for r in matching_records])
                    st.info(f"**Drill Down for:** `{messy_name}`")
                    st.dataframe(df_drill, use_container_width=True)

            # 1. Deterministic
            st.subheader("Deterministic Decisions")
            deterministic = st.session_state.exact_matches + st.session_state.auto_rejected
            if deterministic:
                df_det = pd.DataFrame([json.loads(d.model_dump_json()) for d in deterministic])
                event_det = st.dataframe(df_det, use_container_width=True, selection_mode="single-row", on_select="rerun")
                show_drilldown(event_det, df_det, "original_messy_name")
            else:
                st.info("No deterministic decisions available.")
            
            # 2. Ambiguous
            st.subheader("Ambiguous Records")
            if st.session_state.candidates:
                df_amb = pd.DataFrame([json.loads(c.model_dump_json()) for c in st.session_state.candidates])
                event_amb = st.dataframe(df_amb, use_container_width=True, selection_mode="single-row", on_select="rerun")
                show_drilldown(event_amb, df_amb, "messy_name")
            else:
                st.info("No ambiguous records.")
                
            # 3. AI Results
            st.subheader("AI Results")
            if st.session_state.get('llm_decisions'):
                df_ai = pd.DataFrame([json.loads(d.model_dump_json()) for d in st.session_state.llm_decisions])
                event_ai = st.dataframe(df_ai, use_container_width=True, selection_mode="single-row", on_select="rerun")
                show_drilldown(event_ai, df_ai, "original_messy_name")
            else:
                st.info("No AI results available.")
                df_ai = pd.DataFrame()


            # Generate Base Excel Data
            excel_data = []
            for d in st.session_state.exact_matches:
                excel_data.append({
                    "Original Messy Name": d.original_messy_name,
                    "Resolved Master Name": d.resolved_master_name,
                    "Resolution Type": "Exact Match",
                    "Confidence Score": d.confidence_score,
                    "Reasoning": d.reasoning
                })
            for d in st.session_state.auto_rejected:
                excel_data.append({
                    "Original Messy Name": d.original_messy_name,
                    "Resolved Master Name": d.resolved_master_name,
                    "Resolution Type": "Junk Filter",
                    "Confidence Score": d.confidence_score,
                    "Reasoning": d.reasoning
                })
            for d in st.session_state.llm_decisions:
                excel_data.append({
                    "Original Messy Name": d.original_messy_name,
                    "Resolved Master Name": d.resolved_master_name,
                    "Resolution Type": "AI Model",
                    "Confidence Score": d.confidence_score,
                    "Reasoning": d.reasoning
                })
                
            df_report = pd.DataFrame(excel_data)
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_report.to_excel(writer, index=False, sheet_name='Resolution Results')
            
            # --- HUMAN IN THE LOOP (AI QUEUE) ---
            st.divider()
            st.subheader("⚠️ AI Review Queue")
            st.info("Edit the 'Resolved Master Name' if the AI was wrong. Check 'Approve for Learning' to add the rule to your workspace so the AI remembers it next time!")
            
            if not df_ai.empty:
                df_ai_filtered = df_ai[["original_messy_name", "resolved_master_name", "confidence_score", "reasoning", "matched"]]
                
                # Split into Needs Review vs High Confidence
                df_needs_review = df_ai_filtered[df_ai_filtered["confidence_score"] < 95].copy()
                df_high_conf = df_ai_filtered[df_ai_filtered["confidence_score"] >= 95].copy()
                
                # Setup columns for the data editor
                if not df_needs_review.empty:
                    df_needs_review.insert(0, "✅ Approve for Learning", False)
                    st.markdown("**Needs Review (Confidence < 95%)**")
                    edited_needs_review = st.data_editor(
                        df_needs_review,
                        hide_index=True,
                        disabled=["original_messy_name", "confidence_score", "reasoning", "matched"],
                        use_container_width=True
                    )
                else:
                    edited_needs_review = pd.DataFrame()
                    
                if not df_high_conf.empty:
                    df_high_conf.insert(0, "✅ Approve for Learning", True)
                    st.markdown("**High Confidence (Confidence ≥ 95%)**")
                    edited_high_conf = st.data_editor(
                        df_high_conf,
                        hide_index=True,
                        disabled=["original_messy_name", "confidence_score", "reasoning", "matched"],
                        use_container_width=True
                    )
                else:
                    edited_high_conf = pd.DataFrame()
                    
                # Compile approved aliases
                approved_aliases = {}
                for df_edited in [edited_needs_review, edited_high_conf]:
                    if not df_edited.empty:
                        approved_rows = df_edited[df_edited["✅ Approve for Learning"] == True]
                        for _, row in approved_rows.iterrows():
                            approved_aliases[row["original_messy_name"]] = row["resolved_master_name"]
                
                # Capture current settings
                current_settings = {
                    "vector_threshold": st.session_state.adv_vector_threshold,
                    "top_k": st.session_state.adv_top_k,
                    "suffix_words": st.session_state.adv_suffix_words,
                    "junk_patterns": st.session_state.adv_junk_patterns,
                    "bank_keywords": st.session_state.adv_bank_keywords,
                    "llm_model": st.session_state.adv_llm_model
                }
                
                run_stats = {
                    "Total Records": len(st.session_state.bl_level_records),
                    "Exact Matches": len(st.session_state.exact_matches),
                    "Auto Rejected": len(st.session_state.auto_rejected),
                    "AI Matches": len(st.session_state.llm_decisions)
                }
                
                # Create updated workspace file
                updated_workspace_bytes = update_workspace(
                    st.session_state.workspace_bytes, 
                    approved_aliases, 
                    current_settings, 
                    run_stats,
                    active_user=str(st.session_state.master_sheet_name)
                )
                
                st.divider()
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.download_button(
                        label="📥 Download Excel Report (Current Run)",
                        data=buffer.getvalue(),
                        file_name="resolution_report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                with col_d2:
                    st.download_button(
                        label=f"💾 Save & Download Updated Workspace ({len(approved_aliases)} New Aliases)",
                        data=updated_workspace_bytes,
                        file_name="Workspace_Updated.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        help="Downloads the Portable Brain containing your settings, run history, and the new aliases you approved.",
                        use_container_width=True
                    )
            else:
                st.info("No AI results to review.")
                st.download_button(
                    label="📥 Download Excel Report",
                    data=buffer.getvalue(),
                    file_name="resolution_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )

        with res_tab2:
            st.subheader("📋 Master Account Shipment Reports")
            st.write("Select the accounts below to view their Bills of Lading and drill down into individual container units.")

            # Build mapping of messy_name -> resolved_master_name
            messy_to_master = {}
            for d in st.session_state.exact_matches:
                if d.resolved_master_name:
                    messy_to_master[d.original_messy_name] = d.resolved_master_name
            for d in st.session_state.llm_decisions:
                if d.matched and d.resolved_master_name:
                    messy_to_master[d.original_messy_name] = d.resolved_master_name
            for d in st.session_state.auto_rejected:
                if d.resolved_master_name:
                    messy_to_master[d.original_messy_name] = d.resolved_master_name

            # Group records by resolved master account
            master_groups = {}  # {master_name: {bl_num: [records]}}
            all_recs = st.session_state.get('raw_records', st.session_state.bl_level_records)
            for r in all_recs:
                # Filter out blank/null BLs
                if not r.bill_of_lading or str(r.bill_of_lading).strip() == "" or str(r.bill_of_lading).lower() == "nan":
                    continue
                    
                m_name = messy_to_master.get(r.messy_party_name, "⚠️ Unresolved / Other")
                if m_name not in master_groups:
                    master_groups[m_name] = {}
                bl_val = str(r.bill_of_lading).strip()
                if bl_val not in master_groups[m_name]:
                    master_groups[m_name][bl_val] = []
                master_groups[m_name][bl_val].append(r)

            # 1. Account selection table
            account_rows = []
            for m_name in sorted(master_groups.keys()):
                bl_map = master_groups[m_name]
                tot_containers = sum(len(recs) for recs in bl_map.values())
                account_rows.append({
                    "📊 Include": True if m_name != "⚠️ Unresolved / Other" else False,
                    "Master Account Name": m_name,
                    "Total BLs": len(bl_map),
                    "Total Containers": tot_containers
                })
            
            df_acc_sel = pd.DataFrame(account_rows)
            st.markdown("### 1️⃣ Check Accounts to Include in Report")
            edited_acc_sel = st.data_editor(
                df_acc_sel,
                hide_index=True,
                disabled=["Master Account Name", "Total BLs", "Total Containers"],
                use_container_width=True,
                key="report_acc_selector"
            )
            
            selected_accounts = edited_acc_sel[edited_acc_sel["📊 Include"] == True]["Master Account Name"].tolist()

            st.divider()
            st.markdown("### 2️⃣ BL & Container Units View")
            if not selected_accounts:
                st.info("👆 Please check at least one Master Account in the table above to view its BLs and container units.")
            else:
                for acc_idx, acc in enumerate(selected_accounts):
                    bl_map = master_groups[acc]
                    bl_list = sorted(list(bl_map.keys()))
                    
                    with st.container():
                        st.markdown(f"#### 🏢 **{acc}** (`{len(bl_list)} BLs`, `{sum(len(recs) for recs in bl_map.values())} Containers`)")
                        st.write("Click checkboxes below to filter containers by Bill of Lading:")
                        
                        select_all_key = f"select_all_{acc_idx}"
                        if select_all_key not in st.session_state:
                            st.session_state[select_all_key] = True
                            
                        def toggle_all(acc_idx_inner, bl_list_inner):
                            new_state = not st.session_state[f"select_all_{acc_idx_inner}"]
                            st.session_state[f"select_all_{acc_idx_inner}"] = new_state
                            for b in bl_list_inner:
                                st.session_state[f"rpt_chk_{acc_idx_inner}_{b}"] = new_state

                        st.checkbox("✅ Select All / Unselect All", key=select_all_key, on_change=toggle_all, args=(acc_idx, bl_list))
                        
                        # Horizontal list style of BL checkboxes
                        selected_bls_for_acc = []
                        cols_per_row = 4
                        for i in range(0, len(bl_list), cols_per_row):
                            cols = st.columns(cols_per_row)
                            for j, col in enumerate(cols):
                                if i + j < len(bl_list):
                                    bl_num = bl_list[i + j]
                                    cnt = len(bl_map[bl_num])
                                    chk_key = f"rpt_chk_{acc_idx}_{bl_num}"
                                    if chk_key not in st.session_state:
                                        st.session_state[chk_key] = st.session_state[select_all_key]
                                    with col:
                                        if st.checkbox(f"📄 **{bl_num}** ({cnt} units)", key=chk_key):
                                            selected_bls_for_acc.append(bl_num)
                        
                        # Show container numbers for selected BLs
                        if selected_bls_for_acc:
                            container_rows = []
                            for bl_num in selected_bls_for_acc:
                                for r in bl_map[bl_num]:
                                    container_rows.append({
                                        "Bill of Lading": bl_num,
                                        "Container Number": r.container_number,
                                        "Notify Party": r.notify_party,
                                        "Consignee Name (Messy)": r.messy_party_name,
                                        "Role": r.party_role
                                    })
                            df_containers = pd.DataFrame(container_rows)
                            st.dataframe(df_containers, use_container_width=True)
                        else:
                            st.caption("No BLs selected for this account.")
                        st.divider()

                # Export Selected Report
                export_rows = []
                
                eta_str = st.session_state.eta.strftime("%Y-%m-%d") if hasattr(st.session_state.eta, 'strftime') else str(st.session_state.eta)
                vessel_name_safe = str(st.session_state.vessel_name).strip()
                if not vessel_name_safe:
                    vessel_name_safe = "UNKNOWN_VESSEL"
                    
                file_name_out = f"CAL_{vessel_name_safe.replace(' ', '_')}_{eta_str}.xlsx"

                for acc_idx, acc in enumerate(selected_accounts):
                    for bl_num, recs in master_groups[acc].items():
                        chk_key = f"rpt_chk_{acc_idx}_{bl_num}"
                        if st.session_state.get(chk_key, False):
                            for r in recs:
                                export_rows.append({
                                    "Resolved Master Account": acc,
                                    "Bill of Lading": bl_num,
                                    "Container Number": r.container_number,
                                    "Vessel Name": st.session_state.vessel_name,
                                    "ETA": eta_str,
                                    "Notify Party": r.notify_party,
                                    "Consignee Name (Messy)": r.messy_party_name,
                                    "Role": r.party_role
                                })
                if export_rows:
                    df_export = pd.DataFrame(export_rows)
                    buf_export = io.BytesIO()
                    with pd.ExcelWriter(buf_export, engine='openpyxl') as writer:
                        df_export.to_excel(writer, index=False, sheet_name='Selected Report')
                    st.download_button(
                        label=f"📥 Download Selected Accounts Report ({len(export_rows)} total containers)",
                        data=buf_export.getvalue(),
                        file_name=file_name_out,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        use_container_width=True
                    )