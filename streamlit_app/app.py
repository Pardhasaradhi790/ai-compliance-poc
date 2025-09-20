import streamlit as st
import requests
import pandas as pd
import io
import json

st.set_page_config(page_title="AI Compliance Portal (Streamlit)", layout="wide")

# --- Sidebar: API base URL & quick help ---
st.sidebar.header("Setup")
api_base = st.sidebar.text_input("API Base URL", value="", help="Your API Gateway base URL (e.g., https://xxxxxx.execute-api.us-east-1.amazonaws.com)")
st.sidebar.markdown("""
**How to get it?**
- Deploy the backend (SAM) and copy the output `ApiEndpoint`.
""")
st.sidebar.divider()
st.sidebar.caption("Tip: Upload CCPA/GDPR docs first, start ingestion, then ask questions.")

def require_api():
    if not api_base:
        st.error("Enter your API Base URL in the left sidebar.")
        st.stop()

st.title("AI Compliance Portal")
st.caption("Grounded answers with citations over your compliance documents (CCPA, GDPR, ISO).")

tab_docs, tab_chat, tab_batch = st.tabs(["📄 Documents", "💬 Chat", "🧾 Questionnaire"])

# -----------------------
# Documents tab
# -----------------------
with tab_docs:
    st.subheader("Upload compliance documents (PDF/DOCX/XLSX) and start ingestion")
    require_api()
    doc = st.file_uploader("Choose a file", type=["pdf", "docx", "xlsx", "txt"], accept_multiple_files=False)
    framework = st.text_input("Framework tag (e.g., ccpa, gdpr, iso)", value="ccpa")
    if st.button("Upload & Start Ingestion", type="primary", disabled=not doc):
        if not doc:
            st.warning("Please select a file.")
        else:
            files = {"file": (doc.name, doc.getvalue(), doc.type or "application/octet-stream")}
            data = {"framework": framework or "generic"}
            with st.spinner("Uploading and starting ingestion..."):
                try:
                    r = requests.post(f"{api_base}/ingest/start", files=files, data=data, timeout=120)
                    if r.ok:
                        resp = r.json()
                        st.success("Ingestion started")
                        st.json(resp)
                    else:
                        st.error(f"Error {r.status_code}: {r.text}")
                except Exception as e:
                    st.exception(e)

    st.info("After ingestion finishes in Bedrock KB, your documents become retrievable for Q&A with citations.")

# -----------------------
# Chat tab
# -----------------------
with tab_chat:
    st.subheader("Ask grounded questions with citations")
    require_api()
    col1, col2 = st.columns([3,1])
    with col1:
        q = st.text_input("Your question", value="How do you comply with the CCPA Right to Deletion?")
    with col2:
        top_k = st.number_input("Top-K Results", min_value=1, max_value=20, value=8, step=1)
    if st.button("Ask", type="primary"):
        if not q.strip():
            st.warning("Please enter a question.")
        else:
            payload = {"question": q.strip(), "top_k": int(top_k)}
            with st.spinner("Retrieving and generating answer..."):
                try:
                    r = requests.post(f"{api_base}/ask", json=payload, timeout=120)
                    if r.ok:
                        data = r.json()
                        st.markdown("#### Answer")
                        st.write(data.get("answer") or "(no answer)")
                        cits = data.get("citations") or []
                        if cits:
                            st.markdown("#### Citations")
                            for i, c in enumerate(cits, start=1):
                                title = c.get("title") or "document"
                                page = c.get("page")
                                snippet = c.get("snippet")
                                uri = c.get("uri")
                                with st.expander(f"{i}. {title} {'(p.'+str(page)+')' if page else ''}"):
                                    if snippet:
                                        st.write(snippet)
                                    if uri:
                                        st.code(uri)
                        else:
                            st.info("No citations returned. Either ingestion is still in progress, or the question is out-of-scope.")
                    else:
                        st.error(f"Error {r.status_code}: {r.text}")
                except Exception as e:
                    st.exception(e)

# -----------------------
# Questionnaire tab
# -----------------------
with tab_batch:
    st.subheader("Upload a CSV of questions and get answers as a downloadable file")
    require_api()
    st.caption("CSV must have columns: question_id, question_text")
    choice = st.radio("How do you want to run batch?", ["Upload CSV here", "I already have an S3 URI"], horizontal=True)
    s3_uri = None

    if choice == "Upload CSV here":
        csv_file = st.file_uploader("CSV file", type=["csv"], key="csv_upload")
        if st.button("Run Batch (Upload → Ingest → Answer)"):
            if not csv_file:
                st.warning("Select a CSV file first.")
            else:
                # Upload through /ingest/start to place into RAW bucket; reuse returned s3_uri
                files = {"file": (csv_file.name, csv_file.getvalue(), "text/csv")}
                data = {"framework": "batch"}
                with st.spinner("Uploading CSV to S3 via backend..."):
                    try:
                        r = requests.post(f"{api_base}/ingest/start", files=files, data=data, timeout=120)
                        if not r.ok:
                            st.error(f"Error uploading CSV: {r.status_code} {r.text}")
                        else:
                            s3_uri = r.json().get("s3_uri")
                            st.write("CSV uploaded to:", s3_uri)
                    except Exception as e:
                        st.exception(e)

                if s3_uri:
                    with st.spinner("Running batch answers..."):
                        try:
                            fd = {"file_s3_uri": (None, s3_uri)}
                            b = requests.post(f"{api_base}/batch", files=fd, timeout=300)
                            if b.ok:
                                resp = b.json()
                                st.success("Batch complete")
                                st.json(resp)
                                if "download_url" in resp:
                                    st.markdown(f"[Download results CSV]({resp['download_url']})")
                            else:
                                st.error(f"Batch error {b.status_code}: {b.text}")
                        except Exception as e:
                            st.exception(e)

    else:
        s3_uri_in = st.text_input("Enter S3 URI (e.g., s3://your-raw-bucket/Sample_Questionnaire.csv)")
        if st.button("Run Batch with S3 URI"):
            if not s3_uri_in.strip():
                st.warning("Enter a valid s3:// URI.")
            else:
                with st.spinner("Running batch answers..."):
                    try:
                        fd = {"file_s3_uri": (None, s3_uri_in.strip())}
                        b = requests.post(f"{api_base}/batch", files=fd, timeout=300)
                        if b.ok:
                            resp = b.json()
                            st.success("Batch complete")
                            st.json(resp)
                            if "download_url" in resp:
                                st.markdown(f"[Download results CSV]({resp['download_url']})")
                        else:
                            st.error(f"Batch error {b.status_code}: {b.text}")
                    except Exception as e:
                        st.exception(e)
