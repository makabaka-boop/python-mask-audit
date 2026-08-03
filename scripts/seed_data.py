"""初始化样例数据脚本。

创建若干规则、一个分组、样例文本，并执行一次分组演练，
用于验证完整链路（规则 -> 分组 -> 样例 -> 演练 -> 快照 -> 审计）。

使用：
    python3 scripts/seed_data.py
可选环境变量：
    MASK_AUDIT_DB   SQLite 数据库路径（默认 mask_audit.db）
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Config  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services import MaskService  # noqa: E402


SEED_RULES = [
    {
        "rule_name": "phone_cn",
        "field_type": "phone",
        "match_type": "regex",
        "match_value": r"1[3-9]\d{9}",
        "replace_strategy": "keep_edges",
        "replace_config": {"left": 3, "right": 2, "mask_char": "*"},
        "priority": 10,
        "enabled": True,
    },
    {
        "rule_name": "email",
        "field_type": "email",
        "match_type": "regex",
        "match_value": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        "replace_strategy": "middle_mask",
        "replace_config": {"mask_char": "*"},
        "priority": 20,
        "enabled": True,
    },
    {
        "rule_name": "id_card",
        "field_type": "id_card",
        "match_type": "regex",
        "match_value": r"\d{17}[\dXx]",
        "replace_strategy": "keep_edges",
        "replace_config": {"left": 4, "right": 4, "mask_char": "*"},
        "priority": 30,
        "enabled": True,
    },
]


SEED_SAMPLES = [
    {
        "sample_name": "contact_info",
        "sample_category": "pii",
        "raw_text": (
            "联系人张三，手机 13812345678，邮箱 zhangsan@example.com，"
            "身份证 110101199003078888。备用手机 13900001111。"
        ),
        "expected_note": "手机号/邮箱/身份证均应被脱敏",
    },
]


def seed() -> dict:
    os.environ.setdefault("MASK_AUDIT_DB", Config.DATABASE_PATH)
    app = create_app()
    with app.app_context():
        svc = MaskService()

        rule_ids = []
        for rule_data in SEED_RULES:
            rule = svc.rules.create(rule_data)
            rule_ids.append(rule["id"])
            print(f"[seed] created rule #{rule['id']} {rule['rule_name']}")

        group = svc.groups.create("seed_pii", "种子数据：个人敏感信息分组")
        for rid in rule_ids:
            svc.groups.add_rule(group["id"], rid)
        print(f"[seed] created group #{group['id']} with {len(rule_ids)} rules")

        sample_ids = []
        for sample_data in SEED_SAMPLES:
            sample = svc.samples.create(**sample_data)
            sample_ids.append(sample["id"])
            print(f"[seed] created sample #{sample['id']} {sample['sample_name']}")

        run = svc.execute_group(
            group_id=group["id"], sample_id=sample_ids[0], persist=True
        )
        print(
            f"[seed] executed run #{run['run']['id']}, "
            f"hit_count={run['run']['hit_count']}"
        )
        print(f"[seed] output: {run['run']['output_text']}")

        return {
            "rule_ids": rule_ids,
            "group_id": group["id"],
            "sample_ids": sample_ids,
            "run_id": run["run"]["id"],
            "output_text": run["run"]["output_text"],
        }


if __name__ == "__main__":
    result = seed()
    print("\n[seed] done.")
    print(result)
