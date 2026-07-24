import streamlit as st
import os
import json
import pandas as pd
import io
from src.ingestion.universal_parser import parse_user_driven_excel
from src.ingestion.parsers.master_parser import ingest_master_list_excel
from src.resolution.exact_matcher import process_exact_matches
from src.resolution.candidate_generator import find_top_candidates
from src.resolution.pre_processor import should_reject, create_rejection_decision
from src.resolution.llm_resolver import resolve_candidates
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

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.title("Navigation")
    menu = st.radio(
        "Menu",
        ["1. File Uploads", "2. Data Configuration", "3. Run Pipeline"]
    )

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
    
    if not st.session_state.manifest_file_bytes:
        st.warning("⚠️ Please upload a Shipping Manifest in the 'File Uploads' section first.")
    else:
        st.subheader("Structural Configuration")
        col_s1, col_s2, col_s3 = st.columns(3)
        
        manifest_io = io.BytesIO(st.session_state.manifest_file_bytes)
        excel_file = pd.ExcelFile(manifest_io)
        
        with col_s1:
            st.session_state.sheet_name = st.selectbox("Target Sheet", excel_file.sheet_names, index=excel_file.sheet_names.index(st.session_state.sheet_name) if st.session_state.sheet_name in excel_file.sheet_names else 0)
        with col_s2:
            st.session_state.header_row_index = int(st.number_input("Header Row Index (0-indexed)", min_value=0, value=st.session_state.header_row_index))
        with col_s3:
            st.write("")
            st.write("")
            st.session_state.skip_sub_header = st.checkbox("Skip Sub-header Row", value=st.session_state.skip_sub_header)
        
        st.divider()
        st.subheader("Dynamic Column Mapping")
        try:
            manifest_io.seek(0)
            df_preview = pd.read_excel(manifest_io, sheet_name=st.session_state.sheet_name, header=st.session_state.header_row_index, nrows=5)
            columns = [str(c) for c in df_preview.columns.tolist()]
            
            st.write("**Live Preview:**")
            st.dataframe(df_preview.head(3), use_container_width=True)
            
            # Helper to safely get index
            def get_idx(options, val):
                return options.index(val) if val in options else 0

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
                    # 1. Save uploaded files to the input directory temporarily
                    os.makedirs(config['paths']['input_dir'], exist_ok=True)
                    
                    master_path = os.path.join(config['paths']['input_dir'], st.session_state.master_file_name)
                    manifest_path = os.path.join(config['paths']['input_dir'], st.session_state.manifest_file_name)
                    
                    with open(master_path, "wb") as f:
                        f.write(st.session_state.master_file_bytes)
                    with open(manifest_path, "wb") as f:
                        f.write(st.session_state.manifest_file_bytes)

                    # 2. Run Master Parser
                    master_json_path = config['paths']['master_json']
                    ingest_master_list_excel(master_path, master_json_path)

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

                    # 4. Run Exact Matcher
                    exact_matches, unmatched_records = process_exact_matches(bl_level_records, master_json_path)

                    # 5. Run Pre-Processor (Junk Filter)
                    to_vector_search = []
                    auto_rejected = []
                    for record in unmatched_records:
                        if should_reject(record.messy_party_name):
                            auto_rejected.append(create_rejection_decision(record.messy_party_name))
                        else:
                            to_vector_search.append(record)

                    # 6. Run Vector Search
                    candidates, _ = find_top_candidates(to_vector_search, master_json_path)

                    # --- DYNAMIC UI PREVIEW ---
                    ui_placeholder = st.empty()
                    with ui_placeholder.container():
                        st.info("✅ Deterministic matching complete! AI Resolution starting...")
                        st.subheader("Deterministic Decisions")
                        deterministic = exact_matches + auto_rejected
                        if deterministic:
                            st.dataframe([json.loads(d.model_dump_json()) for d in deterministic], use_container_width=True)
                        st.subheader("Ambiguous Records (Waiting for AI Queue)")
                        if candidates:
                            st.dataframe([json.loads(c.model_dump_json()) for c in candidates], use_container_width=True)

                    # 7. Run LLM Resolution
                    llm_decisions = []
                    if candidates:
                        with st.spinner(f"🧠 Running AI Resolution on {len(candidates)} ambiguous records... (This may take a moment due to API rate limits)"):
                            llm_decisions = resolve_candidates(candidates)

                    # Clear the preview so the final results can render natively below
                    ui_placeholder.empty()

                    # Combine Results
                    final_decisions = exact_matches + auto_rejected + llm_decisions
                    
                    # Store results in session_state
                    st.session_state.bl_level_records = bl_level_records
                    st.session_state.exact_matches = exact_matches
                    st.session_state.auto_rejected = auto_rejected
                    st.session_state.candidates = candidates
                    st.session_state.llm_decisions = llm_decisions
                    st.session_state.final_decisions = final_decisions
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
            
            # Download Button
            json_str = json.dumps(final_json, indent=2)
            st.download_button(
                label="📥 Download JSON Results",
                data=json_str,
                file_name="pipeline_results.json",
                mime="application/json",
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