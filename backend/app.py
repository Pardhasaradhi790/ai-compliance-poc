import os
import json
import base64
import csv
import io
from typing import List, Optional

import boto3
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mangum import Mangum

from bedrock_client import retrieve_and_generate_answer, start_kb_ingestion_job
from s3_utils import upload_to_s3, presign_s3, read_csv_from_s3

# === Env Vars (configure in Lambda console or IaC) ===
KB_ID = os.getenv("KB_ID", "REPLACE_WITH_KNOWLEDGE_BASE_ID")
MODEL_ARN = os.getenv("MODEL_ARN", "REPLACE_WITH_MODEL_ARN")  # e.g., arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0
RAW_BUCKET = os.getenv("RAW_BUCKET", "REPLACE_WITH_S3_BUCKET_RAW")
EXPORT_BUCKET = os.getenv("EXPORT_BUCKET", "REPLACE_WITH_S3_BUCKET_EXPORTS")
DATA_SOURCE_ID = os.getenv("DATA_SOURCE_ID", "REPLACE_WITH_DATA_SOURCE_ID")  # KB data source ID tied to RAW_BUCKET

app = FastAPI(title="AI Compliance Portal API")

# CORS (adjust for your CloudFront domain in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    question: str
    top_k: Optional[int] = 8

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/ingest/start")
async def ingest_start(file: UploadFile = File(...), framework: Optional[str] = Form(default="generic")):
    # Upload file to RAW bucket under a prefix
    key = f"uploads/{framework}/{file.filename}"
    content = await file.read()
    upload_to_s3(RAW_BUCKET, key, content, content_type=file.content_type or "application/octet-stream")

    # Trigger KB ingestion job (assumes DATA_SOURCE points to RAW_BUCKET)
    job = start_kb_ingestion_job(KB_ID, DATA_SOURCE_ID)
    return {"status": "ingestion_started", "ingestion_job_id": job, "s3_uri": f"s3://{RAW_BUCKET}/{key}"}

@app.post("/ask")
def ask(payload: AskRequest):
    resp = retrieve_and_generate_answer(
        question=payload.question,
        kb_id=KB_ID,
        model_arn=MODEL_ARN,
        top_k=payload.top_k or 8
    )

    # Parse bedrock-agent-runtime response into a friendly shape
    generated_text = resp.get("output", {}).get("text", "") or resp.get("generatedText", "")
    # Citations might be in different structures depending on API version; handle both
    citations = []
    for cit in resp.get("citations", []) or resp.get("additionalModelResponse", {}).get("citations", []) or []:
        for ref in cit.get("retrievedReferences", []):
            citations.append({
                "title": ref.get("content", {}).get("metadata", {}).get("x-amz-bedrock-kb-doc-title") or ref.get("metadata", {}).get("title"),
                "section": ref.get("content", {}).get("metadata", {}).get("section"),
                "page": ref.get("content", {}).get("metadata", {}).get("page"),
                "uri": ref.get("location", {}).get("s3Location", {}).get("uri") or ref.get("location", {}).get("s3Location", {}).get("s3Uri"),
                "snippet": ref.get("content", {}).get("text") or ref.get("content", {}).get("excerpt"),
            })

    return {
        "answer": generated_text,
        "citations": citations,
        "raw": resp
    }

@app.post("/batch")
def batch(file_s3_uri: str = Form(...)):
    # file_s3_uri expected format: s3://bucket/key.csv with columns: question_id,question_text
    rows = read_csv_from_s3(file_s3_uri)
    out_rows = []
    for r in rows:
        qid = r.get("question_id") or r.get("id") or ""
        qtext = r.get("question_text") or r.get("question") or ""
        if not qtext:
            continue
        resp = retrieve_and_generate_answer(qtext, KB_ID, MODEL_ARN, top_k=8)
        generated_text = resp.get("output", {}).get("text", "") or resp.get("generatedText", "")
        citations = []
        for cit in resp.get("citations", []) or resp.get("additionalModelResponse", {}).get("citations", []) or []:
            for ref in cit.get("retrievedReferences", []):
                citations.append({
                    "title": ref.get("content", {}).get("metadata", {}).get("x-amz-bedrock-kb-doc-title") or ref.get("metadata", {}).get("title"),
                    "page": ref.get("content", {}).get("metadata", {}).get("page"),
                })
        out_rows.append({
            "question_id": qid,
            "answer": generated_text,
            "citations": json.dumps(citations)
        })

    # Write to CSV in EXPORT bucket
    out_key = f"batch/results_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.csv"
    csv_buf = io.StringIO()
    w = csv.DictWriter(csv_buf, fieldnames=["question_id","answer","citations"])
    w.writeheader()
    for row in out_rows:
        w.writerow(row)

    upload_to_s3(EXPORT_BUCKET, out_key, csv_buf.getvalue().encode("utf-8"), "text/csv")
    url = presign_s3(EXPORT_BUCKET, out_key, 3600)
    return {"download_url": url, "count": len(out_rows)}

handler = Mangum(app)
