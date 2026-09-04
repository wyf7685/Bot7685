#!/usr/bin/env bash
set -Eeuo pipefail

readonly backup_at="${BACKUP_AT:-03:00}"
readonly full_backup_day="${BACKUP_FULL_DAY:-7}"
readonly retry_seconds="${BACKUP_RETRY_SECONDS:-60}"
readonly database_user="${PGBACKREST_PG1_USER:-postgres}"
readonly database_name="${POSTGRES_DB:-postgres}"
readonly scheduler_pid_file="/var/run/pgbackrest/scheduler.pid"

log() {
  printf '%s pgBackRest scheduler: %s\n' "$(date --iso-8601=seconds)" "$*"
}

if [[ ! "$backup_at" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
  log "BACKUP_AT must use HH:MM in 24-hour time"
  exit 1
fi

if [[ ! "$full_backup_day" =~ ^[1-7]$ ]]; then
  log "BACKUP_FULL_DAY must be between 1 and 7"
  exit 1
fi

if [[ ! "$retry_seconds" =~ ^[1-9][0-9]*$ ]]; then
  log "BACKUP_RETRY_SECONDS must be a positive integer"
  exit 1
fi

trap 'rm -f "$scheduler_pid_file"' EXIT

until pg_isready --quiet --username "$database_user" --dbname "$database_name"; do
  sleep "$retry_seconds"
done

until pgbackrest stanza-create; do
  log "stanza initialization failed; retrying in ${retry_seconds}s"
  sleep "$retry_seconds"
done

until pgbackrest check; do
  log "repository check failed; retrying in ${retry_seconds}s"
  sleep "$retry_seconds"
done

until pgbackrest --type=incr backup; do
  log "initial backup failed; retrying in ${retry_seconds}s"
  sleep "$retry_seconds"
done
log "initial backup completed"

next_backup_epoch() {
  local now today
  now="$(date +%s)"
  today="$(date -d "today $backup_at" +%s)"
  if ((today > now)); then
    printf '%s\n' "$today"
  else
    date -d "tomorrow $backup_at" +%s
  fi
}

while true; do
  now="$(date +%s)"
  next="$(next_backup_epoch)"
  sleep "$((next - now))"

  backup_type="diff"
  if [[ "$(date +%u)" == "$full_backup_day" ]]; then
    backup_type="full"
  fi

  if pgbackrest --type="$backup_type" backup; then
    log "$backup_type backup completed"
  else
    log "$backup_type backup failed; next scheduled run will retry"
  fi
done
