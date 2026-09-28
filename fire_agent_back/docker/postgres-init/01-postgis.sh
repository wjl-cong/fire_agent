#!/bin/bash
# PostGIS 扩展初始化（postgres 官方镜像首次启动时由 docker-entrypoint-initdb.d 自动执行）
set -e
psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE EXTENSION IF NOT EXISTS postgis;"
echo "[init] PostGIS extension ready in $POSTGRES_DB"
