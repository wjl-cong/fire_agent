"""
一键导入所有数据 — 按顺序执行：
1. 行政区边界 (region_boundaries)
2. 历史火点 (historical_fire_points)
3. 预测火险 (predicted_fire_risks)

用法:
  python scripts/run_all_imports.py
  python scripts/run_all_imports.py --fire-path <path> --border-path <path> --daily-path <path> --monthly-path <path>
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_db import init_database


def ensure_tables():
    """确保 PostGIS + 表已创建"""
    print("=" * 60)
    print("[1/4] 初始化数据库（PostGIS + 表结构）...")
    init_database()
    print()


def import_borders(border_path: str):
    """导入行政区边界"""
    print("=" * 60)
    print("[2/4] 导入行政区边界...")
    from scripts.import_region_boundaries import import_region_boundaries
    import_region_boundaries(border_path)
    print()


def import_fire_points(fire_path: str):
    """导入历史火点"""
    print("=" * 60)
    print("[3/4] 导入历史火点...")
    from scripts.import_fire_points import import_fire_points
    import_fire_points(fire_path)
    print()


def import_predict_risks(daily_path: str, monthly_path: str):
    """导入预测火险"""
    print("=" * 60)
    print("[4/4] 导入预测火险...")
    from scripts.import_predict_risks import main as import_predict
    # 直接调用内部函数
    from scripts.import_predict_risks import import_daily, import_monthly
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        daily_count = import_daily(daily_path, db)
        print(f"[INFO] 逐日数据: {daily_count} 条")
        monthly_count = import_monthly(monthly_path, db)
        print(f"[INFO] 逐月数据: {monthly_count} 条")
        print(f"[SUCCESS] 预测数据共 {daily_count + monthly_count} 条")
    except Exception as e:
        db.rollback()
        print(f"[ERROR] 预测数据导入失败: {e}")
        raise
    finally:
        db.close()
    print()


def resolve_path(relative: str) -> str:
    """从项目根目录解析路径"""
    return os.path.join(os.path.dirname(__file__), "..", "..", relative)


def main():
    start = time.time()

    # 解析自定义路径
    args = sys.argv[1:]
    paths = {
        "--fire-path": None,
        "--border-path": None,
        "--daily-path": None,
        "--monthly-path": None,
    }
    i = 0
    while i < len(args):
        if args[i] in paths and i + 1 < len(args):
            paths[args[i]] = args[i + 1]
            i += 2
        else:
            i += 1

    # 默认路径
    fire_path = paths["--fire-path"] or resolve_path(
        "fire_agent_front/src/assets/Yunnan_fire.json"
    )
    border_path = paths["--border-path"] or resolve_path(
        "fire_agent_front/src/assets/Yunnan_border.json"
    )
    daily_path = paths["--daily-path"] or resolve_path(
        "fire_agent_front/src/assets/predict_2025_2026_daily.json"
    )
    monthly_path = paths["--monthly-path"] or resolve_path(
        "fire_agent_front/src/assets/predict_2025_2026_month.json"
    )

    # 检查文件存在
    for name, p in [("历史火点", fire_path), ("行政区边界", border_path),
                     ("逐日预测", daily_path), ("逐月预测", monthly_path)]:
        if not os.path.exists(p):
            print(f"[ERROR] {name} 文件不存在: {p}")
            return

    try:
        ensure_tables()
        import_borders(border_path)
        import_fire_points(fire_path)
        import_predict_risks(daily_path, monthly_path)
    except Exception as e:
        print(f"\n[FAILED] 导入过程出错: {e}")
        sys.exit(1)

    elapsed = time.time() - start
    print("=" * 60)
    print(f"[DONE] 全部数据导入完成，耗时 {elapsed:.1f} 秒")


if __name__ == "__main__":
    main()