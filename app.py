import streamlit as st
import os
import json
import pandas as pd
import io
from src.ingestion.universal_parser import parse_user_driven_excel
from src.ingestion.parsers.master_parser import ingest_master_list_excel
from src.pipeline import run_resolution_pipeline
from src.core.config import config

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
    
    master_file = st.file_uploader("Upload Master Accounts (Excel)", type=["xlsx"])
    if master_file:
        st.session_state.master_file_bytes = master_file.getvalue()
        st.session_state.master_file_name = master_file.name
    elif st.session_state.master_file_name:
        st.success(f"Loaded: {st.session_state.master_file_name}")
        
    manifest_file = st.file_uploader("Upload Shipping Manifest (Excel)", type=["xlsx"])
    if manifest_file:
        st.session_state.manifest_file_bytes = manifest_file.getvalue()
        st.session_state.manifest_file_name = manifest_file.name
    elif st.session_state.manifest_file_name:
        st.success(f"Loaded: {st.session_state.manifest_file_name}")


# ==========================================
# SECTION 2: DATA CONFIGURATION & MAPPING
# ==========================================
elif menu == "2. Data Configuration":
    st.header("⚙️ 2. Data Configuration & Mapping")
    
    # 1. Master List Config
    if st.session_state.master_file_bytes:
        st.subheader("Master List Column Mapping")
        try:
            master_io = io.BytesIO(st.session_state.master_file_bytes)
            df_master_preview = pd.read_excel(master_io, nrows=3)
            master_cols = [str(c) for c in df_master_preview.columns.tolist()]
            
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
                        alias_col=st.session_state.master_alias_col if st.session_state.master_alias_col != "None" else None
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
                            st.toast(f"🧠 Running AI Resolution on {data['count']} ambiguous records using {st.session_state.adv_llm_model}...")
                        elif status == "pipeline_complete":
                            ui_placeholder.empty()

                    results = run_resolution_pipeline(
                        records=bl_level_records, 
                        master_json_path=master_json_path,
                        ui_callback=pipeline_update_hook
                    )
                    
                    # Store results in session_state
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

    # --- DISPLAY RESULTS ---
    if st.session_state.get('pipeline_ran', False):
        st.header("📊 Pipeline Analytics")
        
        # Metrics Dashboard
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Unique BLs", len(st.session_state.bl_level_records))
        col2.metric("🟢 Exact Matches", len(st.session_state.exact_matches))
        col3.metric("🔴 Auto-Rejected (Junk)", len(st.session_state.auto_rejected))
        col4.metric("🟡 Sent to AI Queue", len(st.session_state.candidates), help="Ambiguous names requiring Vector Search/LLM.")

        st.divider()

        # 1. Final
        st.subheader("Final Decisions")
        final_json = [json.loads(d.model_dump_json()) for d in st.session_state.final_decisions]
        if final_json:
            st.dataframe(final_json, use_container_width=True)
            
            # --- Excel Generation ---
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
            
            st.download_button(
                label="📥 Download Excel Report",
                data=buffer.getvalue(),
                file_name="resolution_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
        else:
            st.info("No decisions available.")

        # 2. Deterministic
        st.subheader("Deterministic Decisions")
        deterministic = st.session_state.exact_matches + st.session_state.auto_rejected
        if deterministic:
            det_json = [json.loads(d.model_dump_json()) for d in deterministic]
            st.dataframe(det_json, use_container_width=True)
        else:
            st.info("No deterministic decisions available.")
        
        # 3. Ambiguous
        st.subheader("Ambiguous Records")
        if st.session_state.candidates:
            candidates_json = [json.loads(c.model_dump_json()) for c in st.session_state.candidates]
            st.dataframe(candidates_json, use_container_width=True)
        else:
            st.info("No ambiguous records.")
            
        # 4. AI Result
        st.subheader("AI Results")
        if st.session_state.get('llm_decisions'):
            llm_json = [json.loads(d.model_dump_json()) for d in st.session_state.llm_decisions]
            st.dataframe(llm_json, use_container_width=True)
        else:
            st.info("No AI results available.")