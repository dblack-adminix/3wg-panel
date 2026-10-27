#!/usr/bin/env bash
set -euo pipefail

for stage in \
  'Preparing source' \
  'Provisioning protocol containers' \
  'Detecting protocol settings' \
  'Applying backend API patches' \
  'Building React frontend' \
  'Building Docker image' \
  'Installing update runner' \
  'Recreating container' \
  'Health check' \
  'Configuring Caddy reverse proxy'
do
  printf '%s\n' "$stage"
done

printf '3WG Core installed.\n'
