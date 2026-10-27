"""管理命令行：python manage.py <initdb|seed|reset|restock|serve|check|inject>"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time


def main() -> int:
    ap = argparse.ArgumentParser(description="海上风电场运维智能体管理工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("initdb", help="创建数据库与表结构")
    sp = sub.add_parser("seed", help="写入初始化数据(幂等)")
    sp.add_argument("--minutes", type=int, default=180, help="实时库回填分钟数")
    sub.add_parser("reset", help="[危险] 清空本项目数据库并重建")
    sub.add_parser("restock", help="演示复位: 恢复备件库存、停止故障注入、取消未结工单和告警（保留知识与审计）")
    sv = sub.add_parser("serve", help="启动 Web 服务")
    sv.add_argument("--host", default="0.0.0.0")
    sv.add_argument("--port", type=int, default=8000)
    sub.add_parser("check", help="检查数据库与 DeepSeek 连通性")
    ij = sub.add_parser("inject", help="注入故障场景用于演示: inject WT-023 gearbox_cooler_clog [ramp分钟]")
    ij.add_argument("asset")
    ij.add_argument("scenario")
    ij.add_argument("ramp", nargs="?", type=float, default=15.0)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    from windom import db
    if args.cmd == "initdb":
        db.init_db()
        print("数据库已就绪:", db.health())
    elif args.cmd == "seed":
        db.init_db()
        from windom import seed
        t = time.time()
        print(json.dumps(seed.seed_all(backfill_minutes=args.minutes), ensure_ascii=False, default=str))
        print(f"完成，用时 {time.time() - t:.1f}s")
    elif args.cmd == "reset":
        db.ensure_database()
        db.reset_schema()
        print("已重置")
    elif args.cmd == "restock":
        from windom import ontology as ont
        db.x("UPDATE sim_faults SET active=FALSE")
        a = db.x("UPDATE alarms SET status='closed', closed_at=now() WHERE status IN ('open','acknowledged')")
        w = db.x("UPDATE work_orders SET status='cancelled' WHERE source<>'history' AND status IN ('draft','pending_approval','approved','dispatched','in_progress')")
        db.x("UPDATE trip_plans SET status='cancelled' WHERE status IN ('suggested','confirmed')")
        for fid, code in [(r["id"], r["code"]) for r in db.q("SELECT id, code FROM wind_farms")]:
            big = code == "EH-01"
            for c, _n, _ct, st, _l, _d in ont.SPARE_PARTS:
                db.x("UPDATE spare_parts SET stock=%s, reserved=0 WHERE farm_id=%s AND code=%s", (st if big else max(0, st // 2), fid, c))
        # 清理测试遗留文档，并确保种子规程的“当前有效版本”是设计文档版本
        from windom import seed_docs
        db.x("DELETE FROM documents WHERE doc_no LIKE %s", ("ZZ-%",))
        for dno, (_t, _ty, ver, _m, _s) in seed_docs.DOCS.items():
            db.x("UPDATE documents SET status='deprecated' WHERE doc_no=%s AND version<>%s", (dno, ver))
            db.x("UPDATE documents SET status='active' WHERE doc_no=%s AND version=%s", (dno, ver))
        print(f"已复位：关闭告警 {a} 条，取消工单 {w} 张，备件库存恢复初始值")
    elif args.cmd == "check":
        from windom import llm
        print("PostgreSQL:", db.health())
        if llm.available():
            print("DeepSeek:", llm.chat([{"role": "user", "content": "回复ok"}], max_tokens=8))
        else:
            print("DeepSeek: 未配置 DEEPSEEK_API_KEY")
    elif args.cmd == "inject":
        from windom.services import faults
        print(faults.inject(args.asset, args.scenario, args.ramp))
    elif args.cmd == "serve":
        import uvicorn
        uvicorn.run("windom.api.app:app", host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
