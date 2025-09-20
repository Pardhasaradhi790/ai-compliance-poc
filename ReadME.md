# AI Compliance Portal – All-in-One Package

This bundle includes everything you need to build a **compliance Q&A portal** with AWS Bedrock Knowledge Bases, plus a **Streamlit UI** and **dummy docs** to test.

## Folders

- `backend/` — FastAPI app (deployed to AWS Lambda with SAM)
- `infrastructure/` — SAM template to provision API Gateway + Lambda
- `streamlit_app/` — Streamlit UI to run locally
- `docs/` — Detailed documentation PDF
- `dummy_docs/` — Example PDFs (CCPA/GDPR/ISO) and sample questionnaire CSV

---

## Step 1. Install Prerequisites

- Python 3.11
- AWS CLI v2 (`aws --version`)
- AWS SAM CLI (`sam --version`)

## Step 2. Create AWS resources

1. Two S3 buckets (unique names):
   ```bash
   export RAW_BUCKET=ai-portal-raw-$(date +%s)
   export EXPORT_BUCKET=ai-portal-exports-$(date +%s)
   aws s3 mb s3://$RAW_BUCKET
   aws s3 mb s3://$EXPORT_BUCKET
   ```
2. Bedrock Knowledge Base (Console → Bedrock → Knowledge bases → Create):
   - Storage: **OpenSearch Serverless (Vector)**
   - Embeddings: **amazon.titan-embed-text-v2**
   - Data Source: point to `RAW_BUCKET`, prefix `uploads/`
   - Save **KB_ID**  = OUAAXKX49A and
   - DATA_SOURCE_ID = R6HJQ4NV5P
3. Pick a generation model ARN (e.g., Claude 3 Haiku in us-east-1):
   ```
   arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0
   ```

## Step 3. Deploy Backend API

```bash
cd ai-compliance-portal-all-in-one
sam build -t infrastructure/template-sam.yaml
sam deploy --guided
```

Provide:

- RawBucketName → $RAW_BUCKET
- ExportBucketName → $EXPORT_BUCKET
- KnowledgeBaseId → KB_ID
- DataSourceId → DATA_SOURCE_ID
- ModelArn → MODEL_ARN

Note the **ApiEndpoint** printed (your API base URL).

## Step 4. Run the Streamlit UI

```bash
cd ai-compliance-portal-all-in-one
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r streamlit_app/requirements.txt
streamlit run streamlit_app/app.py
```

In the left sidebar, paste the **ApiEndpoint**.

## Step 5. Upload Dummy Docs

```bash
aws s3 cp dummy_docs/CCPA_Privacy_Policy.pdf s3://$RAW_BUCKET/uploads/ccpa/
aws s3 cp dummy_docs/GDPR_Data_Protection.pdf s3://$RAW_BUCKET/uploads/gdpr/
aws s3 cp dummy_docs/ISO27001_Security_Summary.pdf s3://$RAW_BUCKET/uploads/iso/
```

Then trigger ingestion from the Streamlit UI (Documents tab).

## Step 6. Ask Questions

In Streamlit → Chat tab:

- "How do you comply with the CCPA Right to Deletion?"
- "Do you provide GDPR Right to Erasure under Article 17?"
- "What certification do you maintain for information security?"

## Step 7. Batch Questionnaire

Upload the sample:

```bash
aws s3 cp dummy_docs/Sample_Questionnaire.csv s3://$RAW_BUCKET/uploads/batch/
```

Then run batch in Streamlit → Questionnaire tab. You’ll get a presigned download link.

---

## Security Notes

- Use KMS encryption on S3, IAM least privilege, Bedrock Guardrails if needed.
- For production: host Streamlit on ECS/EKS or behind ALB; add Cognito Auth.
