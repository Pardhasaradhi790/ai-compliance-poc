import boto3
import csv
import io
from urllib.parse import urlparse

s3 = boto3.client("s3")

def upload_to_s3(bucket: str, key: str, content: bytes, content_type: str):
    s3.put_object(Bucket=bucket, Key=key, Body=content, ContentType=content_type)

def presign_s3(bucket: str, key: str, expires: int = 3600) -> str:
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires
    )

def read_csv_from_s3(s3_uri: str):
    parsed = urlparse(s3_uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    obj = s3.get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read().decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(body)))
    return rows
