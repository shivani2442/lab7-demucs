"""Consume Redis jobs, run Demucs, and store four binary MP3 stems in RustFS."""
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import requests
from redis.exceptions import RedisError

from common import (INPUT_BUCKET, MODELS, OUTPUT_BUCKET, QUEUE, TRACKS,
                    ensure_buckets, log_info, redis_client, storage_client)


def process_job(job, queue_client, storage):
    songhash, model = job["hash"], job["model"]
    if not re.fullmatch(r"[0-9a-f]{56}", songhash) or model not in MODELS:
        raise ValueError("Invalid job hash or model")
    log_info(queue_client, "worker", f"Separating {songhash} with {model}")
    ensure_buckets(storage)
    with tempfile.TemporaryDirectory(prefix="demucs-") as directory:
        root = Path(directory)
        source = root / f"{songhash}.mp3"
        storage.download_file(INPUT_BUCKET, source.name, str(source))
        # An argument list avoids interpreting filenames or model names as shell code.
        subprocess.run([
            sys.executable, "-m", "demucs.separate", "--mp3", "-n", model,
            "--device", "cpu", "--segment", "7", "--jobs", "0",
            "--out", str(root / "output"), str(source)
        ], check=True, timeout=7200)
        output = root / "output" / model / songhash
        for track in sorted(TRACKS):
            path = output / track
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(f"Demucs did not produce {track}")
        for track in sorted(TRACKS):
            storage.upload_file(str(output / track), OUTPUT_BUCKET,
                                f"{songhash}-{track}",
                                ExtraArgs={"ContentType": "audio/mpeg"})
    log_info(queue_client, "worker", f"Completed {songhash}")
    callback = job.get("callback")
    if callback:
        try:
            response = requests.post(callback["url"], json=callback.get("data"), timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            log_info(queue_client, "worker", f"Callback for {songhash} failed: {exc}")


def main():
    logging.basicConfig(level=logging.INFO)
    queue_client, storage = redis_client(), storage_client()
    # Limit CPU thread oversubscription on a local single-worker cluster.
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("MKL_NUM_THREADS", "2")
    while True:
        try:
            item = queue_client.blpop(QUEUE, timeout=5)
        except RedisError:
            logging.exception("Redis unavailable; retrying in 5 seconds")
            time.sleep(5)
            continue
        if item is None:
            continue
        try:
            process_job(json.loads(item[1]), queue_client, storage)
        except Exception as exc:
            logging.exception("Separation failed")
            log_info(queue_client, "worker", f"Job failed: {exc}")


if __name__ == "__main__":
    main()
