#!/usr/bin/env bash
set -euo pipefail

repo=$1
cutoff=$(git --git-dir="$repo" config --get deploy.cutoffUnix)
[[ "$cutoff" =~ ^[0-9]+$ ]]
(( $(date +%s) < cutoff )) || exit 0
url=$(git --git-dir="$repo" config --get deploy.publicURL)
[[ "$url" =~ ^https://github\.com/[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$ ]]

umask 077
exec 8>"$repo/sync.lock"
flock -n 8 || exit 0
mirror="$repo/public-mirror.git"
if [[ ! -d "$mirror" ]]; then
    git init --bare --quiet --initial-branch=main "$mirror"
fi
export GIT_TERMINAL_PROMPT=0 GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
git --git-dir="$mirror" -c credential.helper= -c core.askpass=/bin/false fetch --quiet \
    --no-tags "$url" refs/heads/main:refs/heads/main
new=$(git --git-dir="$mirror" rev-parse refs/heads/main)
deployed=$(git --git-dir="$repo" rev-parse --verify refs/heads/main 2>/dev/null || true)
if [[ "$new" != "$deployed" ]]; then
    git --git-dir="$mirror" push "$repo" refs/heads/main:refs/heads/main
fi
