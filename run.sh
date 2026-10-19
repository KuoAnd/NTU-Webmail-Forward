#!/usr/bin/env bash
# Install / remove / show the cron job that runs ntu2gmail.py.
#   ./run.sh            install (or update) the cron job
#   ./run.sh remove     remove the cron job
#   ./run.sh status     show the current cron job
# Note: crontab is per machine; run this on the workstation that should do the job.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INTERVAL="${INTERVAL:-10}"   # minutes
TAG="# ntu2gmail"
JOB="*/$INTERVAL * * * * /usr/bin/python3 $DIR/ntu2gmail.py >> $DIR/ntu2gmail.log 2>&1 $TAG"

current() { crontab -l 2>/dev/null | grep -vF "$TAG" || true; }

case "${1:-install}" in
    install)
        [ -f "$DIR/config.ini" ] || { echo "missing $DIR/config.ini" >&2; exit 1; }
        { current; echo "$JOB"; } | crontab -
        echo "installed on $(hostname): $JOB"
        ;;
    remove)
        current | crontab -
        echo "removed from $(hostname)"
        ;;
    status)
        crontab -l 2>/dev/null | grep -F "$TAG" || echo "not installed on $(hostname)"
        ;;
    *)
        echo "usage: $0 [install|remove|status]" >&2
        exit 1
        ;;
esac
