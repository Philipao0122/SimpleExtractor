#!/bin/sh
set -e

PRIMARY_HOST=${PRIMARY_HOST:-db_primary}
REPLICATION_USER=${REPLICATION_USER:-replicator}
REPLICATION_PASSWORD=${REPLICATION_PASSWORD:-replicator_password}

# Ensure the data directory is owned by postgres user
chown -R postgres:postgres "$PGDATA"

# Initialize standby data directory if empty
if [ -z "$(ls -A "$PGDATA" 2>/dev/null)" ]; then
  echo "Cloning primary ($PRIMARY_HOST) for standby..."
  export PGPASSWORD="$REPLICATION_PASSWORD"
  
  # Execute pg_basebackup as postgres user
  su-exec postgres pg_basebackup -R -D "$PGDATA" -Fp -Xs -P -v -h "$PRIMARY_HOST" -U "$REPLICATION_USER"
  
  # Append configuration as postgres user
  su-exec postgres sh -c "echo 'hot_standby = on' >> \"$PGDATA/postgresql.auto.conf\""
  
  echo "Standby clone completed."
fi

# Execute postgres as postgres user
exec su-exec postgres postgres
