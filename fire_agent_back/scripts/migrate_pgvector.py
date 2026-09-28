"""
pgvector 迁移脚本（可选，P1 #9 预留）

运行时检测 pgvector 扩展可用性：
- 不可用（如本机 PG 14 未安装 vector 扩展）→ 打印说明后正常退出（exit 0），不做任何变更；
- 可用 → CREATE EXTENSION + 为 kb_chunks 增加 embedding_vec vector(1024) 列 +
  JSON embedding 回填 + HNSW 余弦索引（m=16, ef_construction=64）。

使用（后端目录下）：
    python scripts/migrate_pgvector.py

说明：当前检索链路不依赖 pgvector（JSON embedding + 内存余弦），
本脚本仅作为后续向量检索升级的预备迁移，可重复执行（幂等）。
"""
import sys
from pathlib import Path

# 保证可从后端根目录/任意目录运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg  # noqa: E402  psycopg3（langgraph-checkpoint-postgres 已引入）

from app.core.config import settings  # noqa: E402

EMBEDDING_DIM = 1024  # 与 text-embedding-v3 维度一致


def main() -> int:
    dsn = settings.DATABASE_URL
    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                # 1) 运行时检测 pgvector 可用性
                cur.execute("SELECT name FROM pg_available_extensions WHERE name = 'vector'")
                row = cur.fetchone()
                if not row:
                    print("[pgvector] 当前 PostgreSQL 未安装 vector 扩展（pg_available_extensions 中不可见）。")
                    print("[pgvector] 跳过迁移，检索链路继续使用 JSON embedding + 内存余弦，不影响使用。")
                    print("[pgvector] 如需启用：安装 pgvector 扩展后重新运行本脚本。")
                    return 0

                # 2) 启用扩展 + 加列（幂等）
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(
                    f"ALTER TABLE kb_chunks ADD COLUMN IF NOT EXISTS embedding_vec vector({EMBEDDING_DIM})"
                )

                # 3) 回填：JSON embedding → vector 列
                cur.execute(
                    "SELECT id, embedding FROM kb_chunks "
                    "WHERE embedding IS NOT NULL AND embedding_vec IS NULL"
                )
                rows = cur.fetchall()
                import json
                for chunk_id, raw in rows:
                    try:
                        vec = json.loads(raw) if isinstance(raw, str) else raw
                        cur.execute(
                            "UPDATE kb_chunks SET embedding_vec = %s::vector WHERE id = %s",
                            (json.dumps(vec), chunk_id),
                        )
                    except (ValueError, TypeError):
                        continue
                print(f"[pgvector] 回填完成：{len(rows)} 行")

                # 4) HNSW 余弦索引
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_kb_chunks_embedding_hnsw "
                    "ON kb_chunks USING hnsw (embedding_vec vector_cosine_ops) "
                    "WITH (m = 16, ef_construction = 64)"
                )
            conn.commit()
        print("[pgvector] 迁移成功：embedding_vec 列 + HNSW 余弦索引已就绪。")
        return 0
    except psycopg.OperationalError as e:
        print(f"[pgvector] 数据库连接失败：{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
