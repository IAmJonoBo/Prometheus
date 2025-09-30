#!/usr/bin/env bash
# Offline-friendly docker login helper for CI environments
# Usage: docker-login.sh <registry> <username> <password>
#
# This script provides a fallback for air-gapped GHES environments where
# docker/login-action@v3 may not be available. It uses native docker login
# with stdin password passing to avoid exposing credentials in process lists.

set -euo pipefail

REGISTRY="${1:-}"
USERNAME="${2:-}"
PASSWORD="${3:-}"

if [[ -z "${REGISTRY}" || -z "${USERNAME}" || -z "${PASSWORD}" ]]; then
    echo "Usage: $0 <registry> <username> <password>" >&2
    echo "  registry: e.g., ghcr.io or containers.example.com" >&2
    echo "  username: e.g., \${{ github.actor }}" >&2
    echo "  password: e.g., \${{ secrets.GITHUB_TOKEN }}" >&2
    exit 1
fi

echo "Logging in to ${REGISTRY} as ${USERNAME}..."

# Pass password via stdin to avoid shell history/process exposure
if echo "${PASSWORD}" | docker login "${REGISTRY}" --username "${USERNAME}" --password-stdin; then
    echo "Successfully logged in to ${REGISTRY}"
else
    echo "::error::Failed to log in to ${REGISTRY}. Check credentials and registry endpoint." >&2
    exit 1
fi
