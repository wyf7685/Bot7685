#!/usr/bin/env bash
set -Eeuo pipefail

postgres_pid=""
scheduler_pid=""

stop_processes() {
  if [[ -n "$postgres_pid" ]]; then
    kill -INT "$postgres_pid" 2>/dev/null || true
  fi
  if [[ -n "$scheduler_pid" ]]; then
    kill -TERM "$scheduler_pid" 2>/dev/null || true
  fi
}

trap stop_processes INT TERM

case "${1:-}" in
  postgres|-*)
    install -d -m 0750 -o postgres -g postgres \
      /var/log/pgbackrest \
      /var/run/pgbackrest
    rm -f /var/run/pgbackrest/scheduler.pid

    /usr/local/bin/docker-entrypoint.sh "$@" &
    postgres_pid=$!

    gosu postgres /usr/local/bin/pgbackrest-scheduler &
    scheduler_pid=$!
    printf '%s\n' "$scheduler_pid" >/var/run/pgbackrest/scheduler.pid

    set +e
    wait -n "$postgres_pid" "$scheduler_pid"
    status=$?
    set -e

    stop_processes
    wait "$postgres_pid" 2>/dev/null || true
    wait "$scheduler_pid" 2>/dev/null || true
    exit "$status"
    ;;
  pgbackrest)
    exec gosu postgres "$@"
    ;;
  *)
    exec /usr/local/bin/docker-entrypoint.sh "$@"
    ;;
esac
