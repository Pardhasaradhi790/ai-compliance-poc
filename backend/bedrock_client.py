import boto3

runtime = boto3.client("bedrock-agent-runtime")
control = boto3.client("bedrock-agent")


def start_kb_ingestion_job(knowledge_base_id: str, data_source_id: str) -> str:
    """Start a knowledge base ingestion job for syncing new documents."""
    resp = control.start_ingestion_job(
        knowledgeBaseId=knowledge_base_id,
        dataSourceId=data_source_id
    )
    return resp["ingestionJob"]["ingestionJobId"]


def retrieve_and_generate_answer(question: str, kb_id: str, model_arn: str, top_k: int = 8):
    """
    Retrieve relevant chunks from the Bedrock knowledge base and generate an answer.
    NOTE: generationConfiguration and responseConfiguration are not yet supported
    by boto3 -> removed to prevent ParamValidationError.
    """
    cfg = {
        "type": "KNOWLEDGE_BASE",
        "knowledgeBaseConfiguration": {
            "knowledgeBaseId": kb_id,
            "modelArn": model_arn,
            "retrievalConfiguration": {
                "vectorSearchConfiguration": {
                    "numberOfResults": top_k,
                    "overrideSearchType": "HYBRID"
                }
            }
        }
    }

    resp = runtime.retrieve_and_generate(
        input={"text": question},
        retrieveAndGenerateConfiguration=cfg
    )

    return resp
