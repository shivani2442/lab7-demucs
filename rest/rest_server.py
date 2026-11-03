"""Flask API for asynchronous music separation."""
import base64
import binascii
import hashlib
import io
import json
import logging
import re

from botocore.exceptions import BotoCoreError, ClientError
from flask import Flask, jsonify, request, send_file
from redis.exceptions import RedisError
from werkzeug.exceptions import HTTPException

from common import (DEFAULT_MODEL, INPUT_BUCKET, MODELS, OUTPUT_BUCKET, QUEUE,
                    TRACKS, ensure_buckets, log_info, redis_client, storage_client)


def create_app(queue_client=None, storage=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    queue_client = queue_client if queue_client is not None else redis_client()
    storage = storage if storage is not None else storage_client()

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return jsonify(error=exc.description), exc.code

    @app.errorhandler(RedisError)
    @app.errorhandler(BotoCoreError)
    @app.errorhandler(ClientError)
    def backend_error(exc):
        app.logger.exception("Backend request failed")
        return jsonify(error="Redis or object storage is unavailable"), 503

    @app.get("/")
    def index():
        return jsonify(service="Music Separation Server")

    @app.post("/apiv1/separate")
    def separate():
        data = request.get_json()
        if not isinstance(data, dict) or not isinstance(data.get("mp3"), str):
            return jsonify(error="mp3 must contain base64 encoded audio"), 400
        model = data.get("model", DEFAULT_MODEL)
        if not isinstance(model, str) or model not in MODELS:
            return jsonify(error="model must be mdx_extra_q or htdemucs"), 400
        callback = data.get("callback")
        if callback is not None and (
                not isinstance(callback, dict)
                or not isinstance(callback.get("url"), str)
                or not callback["url"].startswith(("http://", "https://"))):
            return jsonify(error="callback must contain an HTTP(S) url and optional data"), 400
        try:
            audio = base64.b64decode(data["mp3"], validate=True)
        except (ValueError, binascii.Error):
            return jsonify(error="mp3 is not valid base64"), 400
        if not audio:
            return jsonify(error="mp3 cannot be empty"), 400
        # Include the model so different separations do not overwrite each other.
        songhash = hashlib.sha224(audio + model.encode("ascii")).hexdigest()
        ensure_buckets(storage)
        storage.put_object(Bucket=INPUT_BUCKET, Key=f"{songhash}.mp3",
                           Body=audio, ContentType="audio/mpeg")
        # Only a hash and small metadata travel through Redis, never MP3 bytes.
        job = {"hash": songhash, "model": model, "callback": callback}
        queue_client.rpush(QUEUE, json.dumps(job))
        log_info(queue_client, "rest", f"Enqueued {songhash} with {model}")
        return jsonify(hash=songhash, reason="Song enqueued for separation")

    @app.get("/apiv1/queue", strict_slashes=False)
    def queued():
        return jsonify(queue=[json.loads(job)["hash"]
                              for job in queue_client.lrange(QUEUE, 0, -1)])

    def track_key(songhash, track):
        if not re.fullmatch(r"[0-9a-f]{56}", songhash):
            return None
        if track == "base.mp3":  # The REST README spells bass as base.
            track = "bass.mp3"
        if track not in TRACKS:
            return None
        return f"{songhash}-{track}"

    @app.get("/apiv1/track/<songhash>/<track>")
    def download(songhash, track):
        key = track_key(songhash, track)
        if key is None:
            return jsonify(error="Invalid song hash or track"), 400
        try:
            result = storage.get_object(Bucket=OUTPUT_BUCKET, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"NoSuchKey", "NoSuchBucket", "404"}:
                return jsonify(error="Track not found; separation may still be running"), 404
            raise
        body = result["Body"]
        try:
            audio = body.read()
        finally:
            body.close()
        return send_file(io.BytesIO(audio), mimetype="audio/mpeg",
                         as_attachment=True, download_name=key)

    @app.route("/apiv1/remove/<songhash>/<track>", methods=["GET", "DELETE"])
    def remove(songhash, track):
        key = track_key(songhash, track)
        if key is None:
            return jsonify(error="Invalid song hash or track"), 400
        storage.delete_object(Bucket=OUTPUT_BUCKET, Key=key)
        log_info(queue_client, "rest", f"Removed {key}")
        return jsonify(hash=songhash, track=track, reason="Track removed")

    return app


logging.basicConfig(level=logging.INFO)
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
