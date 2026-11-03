#!/bin/sh
# Infrastructure only; run API and worker locally using the forwarded ports.
set -eu
cd "$(dirname "$0")"
kubectl apply -f redis/redis-deployment.yaml -f redis/redis-service.yaml -f rustfs/rustfs.yaml
kubectl rollout status deployment/redis --timeout=180s
kubectl rollout status deployment/rustfs --timeout=180s
kubectl port-forward service/redis 6379:6379 &
redis_pid=$!
trap 'kill "$redis_pid"' EXIT INT TERM
kubectl port-forward service/rustfs 9000:9000 9001:9001
