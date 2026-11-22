#!/usr/bin/env bash
set -euo pipefail

url=${1:?Podaj adres HTTPS publicznego repozytorium GitHub.}
repo=$(realpath "${2:-$HOME/odwolania2json.git}")
scripts=$(cd "$(dirname "$0")" && pwd)
account=$(id -un)
[[ "$account" != root && "$url" =~ ^https://github\.com/[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$ ]]
cutoff=$(git --git-dir="$repo" config --get deploy.cutoffUnix)
[[ "$cutoff" =~ ^[0-9]+$ ]] && (( $(date +%s) < cutoff )) || {
    echo 'Termin wdrożeń minął lub nie został skonfigurowany.' >&2
    exit 1
}
umask 077
units=$(mktemp -d)
trap 'rm -rf -- "$units"' EXIT
python3 - "$units" "$account" "$repo" "$cutoff" <<'PY'
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys

units = Path(sys.argv[1])
user, repo = sys.argv[2:4]
limit = datetime.fromtimestamp(int(sys.argv[4]), timezone.utc)
minute = datetime.now(timezone.utc).replace(second=0, microsecond=0)
calendar = []
while minute < limit:
    end = min(minute.replace(minute=0) + timedelta(hours=1), limit)
    last_minute = (end - timedelta(microseconds=1)).minute
    span = f"{minute.minute:02d}"
    if minute.minute < last_minute:
        span += f"..{last_minute:02d}"
    calendar.append(f"OnCalendar={minute:%Y-%m-%d %H}:{span}:00 UTC")
    minute = end

unit = "odwolania2json-sync"
repo_arg = json.dumps(repo.replace("%", "%%").replace("$", "$$"), ensure_ascii=False)
(units / (unit + ".service")).write_text(
    "[Unit]\nDescription=Synchronizacja publicznego main dla Odwolania2JSON\n"
    "After=network-online.target docker.service\n"
    f"[Service]\nType=oneshot\nUser={user}\n"
    f"ExecStart=/usr/local/libexec/odwolania2json-sync {repo_arg}\n"
    "TimeoutStartSec=infinity\n"
)
(units / (unit + ".timer")).write_text(
    "[Unit]\nDescription=Synchronizacja do terminu UZP\n[Timer]\n"
    + "\n".join(calendar) + "\nAccuracySec=1s\n[Install]\nWantedBy=timers.target\n"
)
PY
git --git-dir="$repo" config deploy.publicURL "$url"
sudo install -D -m 755 "$scripts/sync.sh" /usr/local/libexec/odwolania2json-sync
sudo install -m 644 "$units"/odwolania2json-sync.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now odwolania2json-sync.timer
sudo systemctl start --no-block odwolania2json-sync.service
