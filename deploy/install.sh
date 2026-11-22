#!/usr/bin/env bash
# Odwolania2JSON deployment hook installer
set -euo pipefail

solution=$(realpath "${1:-/opt/solution}")
repo=$(realpath -m "${2:-$HOME/odwolania2json.git}")
scripts=$(cd "$(dirname "$0")" && pwd)
cutoff=$(date -u -d "${3:-2026-11-22T10:00:00Z}" +%s)
for directory in "$solution/input" "$solution/output"; do
    [[ -d "$directory" ]] || { echo "Brakuje katalogu $directory" >&2; exit 1; }
done

umask 077
if [[ ! -e "$repo" ]]; then
    git init --quiet --bare --initial-branch=main "$repo"
fi
[[ "$(git --git-dir="$repo" rev-parse --is-bare-repository)" == true ]]
exec 9>"$repo/deploy.lock"
flock 9
for hook in pre-receive update; do
    destination="$repo/hooks/$hook"
    if [[ -e "$destination" ]] && ! grep -Fxq '# Odwolania2JSON deployment hook' "$destination"; then
        echo "Istnieje niezależny hook $destination" >&2
        exit 1
    fi
done
git --git-dir="$repo" config deploy.solutionRoot "$solution"
git --git-dir="$repo" config deploy.cutoffUnix "$cutoff"
git --git-dir="$repo" config receive.denyDeletes true
git --git-dir="$repo" config receive.denyNonFastForwards true
for hook in pre-receive update; do
    install -m 700 "$scripts/$hook" "$repo/hooks/$hook.new"
    mv -T "$repo/hooks/$hook.new" "$repo/hooks/$hook"
done
echo "Repozytorium wdrożeniowe jest gotowe: $repo"
