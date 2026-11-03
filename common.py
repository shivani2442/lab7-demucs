"""Redis and RustFS connections shared by the API and worker."""
import logging
import os
import platform

import boto3
import redis
from botocore.config import Config
from botocore.exceptions import ClientError

QUEUE = "toWorker"
INPUT_BUCKET = "queue"
OUTPUT_BUCKET = "output"
MODELS = {"mdx_extra_q", "htdemucs"}
DEFAULT_MODEL = "mdx_extra_q"
TRACKS = {"bass.mp3", "drums.mp3", "vocals.mp3", "other.mp3"}


def redis_client():
    return redis.Redis(host=os.getenv("REDIS_HOST", "localhost"),
                       port=int(os.getenv("REDIS_PORT", "6379")), db=0,
                       socket_connect_timeout=5, decode_responses=True)


def storage_client():
    return boto3.client(
        "s3", endpoint_url=os.getenv("RUSTFS_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "rustfs-lab-user"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "replace-this-demo-secret"),
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      connect_timeout=5, read_timeout=60,
                      request_checksum_calculation="when_required",
                      response_checksum_validation="when_required"))


def ensure_buckets(storage):
    for bucket in (INPUT_BUCKET, OUTPUT_BUCKET):
        try:
            storage.head_bucket(Bucket=bucket)
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            try:
                storage.create_bucket(Bucket=bucket)
            except ClientError as create_exc:
                if create_exc.response["Error"]["Code"] != "BucketAlreadyOwnedByYou":
                    raise


def log_info(client, component, message):
    logging.info("%s: %s", component, message)
    try:
        client.lpush("logging", f"{platform.node()}.{component}.info:{message}")
        client.ltrim("logging", 0, 999)
    except redis.RedisError:
        logging.exception("Could not send log message to Redis")
