"""初始化样例数据：创建规则、分组、样例并执行一次演练，用于验证完整链路。

用法：
    python3 scripts/seed.py [db_path]     # 默认 mask_audit.db

重复执行安全：已存在的规则/分组会复用，不会报错退出。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

RULES = [
    {
        "rule_name": "手机号脱敏", "field_type": "phone", "match_type": "regex",
        "match_value": r"1\d{10}", "replace_strategy": "keep_edges",
        "replace_config": {"left": 3, "right": 4, "mask_char": "*"}, "priority": 10,
    },
    {
        "rule_name": "身份证脱敏", "field_type": "id_card", "match_type": "regex",
        "match_value": r"\d{17}[\dXx]", "replace_strategy": "keep_edges",
        "replace_config": {"left": 4, "right": 4, "mask_char": "*"}, "priority": 20,
    },
    {
        "rule_name": "姓名脱敏", "field_type": "name", "match_type": "exact",
        "match_value": "张三", "replace_strategy": "middle_mask",
        "replace_config": {"mask_char": "*"}, "priority": 5,
    },
]

GROUP = {"group_name": "身份信息默认组", "description": "seed 脚本创建的演示分组"}

SAMPLE = {
    "sample_name": "客服工单样例", "sample_category": "客服",
    "raw_text": "客户张三，手机13812345678，证件110101199001011234，请回电。",
    "expected_note": "姓名、手机号、身份证号均应脱敏",
}


def _post(client, path, payload):
    resp = client.post(path, json=payload)
    return resp.status_code, resp.get_json()


def _find_by_name(client, path, key, name):
    items = client.get(path).get_json()
    items = items.get("rules") or items.get("groups") or []
    for item in items:
        if item[key] == name:
            return item
    return None


def seed(db_path: str = "mask_audit.db") -> dict:
    app = create_app(db_path)
    client = app.test_client()

    # 1. 规则（重复执行时复用同名规则）
    rule_ids = []
    for rule in RULES:
        status, body = _post(client, "/api/v1/rules", rule)
        if status == 409:
            body = _find_by_name(client, "/api/v1/rules", "rule_name", rule["rule_name"])
        assert body and body.get("id"), f"创建规则失败: {body}"
        rule_ids.append(body["id"])

    # 2. 分组与成员
    status, group = _post(client, "/api/v1/groups", GROUP)
    if status == 409:
        group = _find_by_name(client, "/api/v1/groups", "group_name", GROUP["group_name"])
    assert group and group.get("id"), f"创建分组失败: {group}"
    for rule_id in rule_ids:
        _post(client, f"/api/v1/groups/{group['id']}/rules", {"rule_id": rule_id})

    # 3. 样例
    _, sample = _post(client, "/api/v1/samples", SAMPLE)
    assert sample and sample.get("id"), f"创建样例失败: {sample}"

    # 4. 一次分组演练
    status, run = _post(client, f"/api/v1/groups/{group['id']}/execute",
                        {"sample_id": sample["id"]})
    assert status == 200, f"演练失败: {run}"

    return {
        "db_path": db_path,
        "rule_ids": rule_ids,
        "group_id": group["id"],
        "sample_id": sample["id"],
        "run_id": run["run_id"],
        "hit_count": run["hit_count"],
        "input_text": run["input_text"],
        "output_text": run["output_text"],
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "mask_audit.db"
    print(json.dumps(seed(path), ensure_ascii=False, indent=2))
