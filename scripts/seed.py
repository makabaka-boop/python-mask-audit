"""初始化样例数据脚本。

通过 HTTP API 创建规则、分组、样例，并执行一次分组演练记录，方便验证
完整的脱敏审计链路。默认连接本机 18105 端口。

用法::

    python3 scripts/seed.py                 # 连接 http://127.0.0.1:18105
    python3 scripts/seed.py http://host:port
"""

import json
import sys
import urllib.error
import urllib.request


def _request(base, method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        base + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def seed(base):
    """创建规则/分组/样例并执行一次分组演练，返回创建结果摘要。"""
    prefix = base + "/api/v1"

    # 1) 创建两条规则：手机号 keep_edges + 关键字 fixed。
    _, phone = _request(
        prefix,
        "POST",
        "/rules",
        {
            "rule_name": "手机号脱敏",
            "field_type": "phone",
            "match_type": "regex",
            "match_value": r"\d{11}",
            "replace_strategy": "keep_edges",
            "replace_config": {"left": 3, "right": 4, "mask_char": "*"},
            "priority": 10,
        },
    )
    _, keyword = _request(
        prefix,
        "POST",
        "/rules",
        {
            "rule_name": "密级关键字脱敏",
            "field_type": "text",
            "match_type": "contains",
            "match_value": "机密",
            "replace_strategy": "fixed",
            "replace_config": {"value": "[已脱敏]"},
            "priority": 20,
        },
    )

    # 2) 创建分组并加入两条规则。
    _, group = _request(prefix, "POST", "/groups", {"group_name": "默认脱敏组", "description": "初始化样例分组"})
    _request(prefix, "POST", f"/groups/{group['id']}/members", {"rule_id": phone["id"]})
    _request(prefix, "POST", f"/groups/{group['id']}/members", {"rule_id": keyword["id"]})

    # 3) 创建样例。
    _, sample = _request(
        prefix,
        "POST",
        "/samples",
        {
            "sample_name": "客服记录样例",
            "sample_category": "contact",
            "raw_text": "客户手机号 13800001111，本次沟通涉及机密项目。",
            "expected_note": "手机号与密级关键字需脱敏",
        },
    )

    # 4) 执行一次分组演练，形成完整审计链路（演练记录 + 命中明细 + 快照）。
    _, run = _request(
        prefix, "POST", "/runs/group", {"group_id": group["id"], "sample_id": sample["id"]}
    )

    return {
        "rules": [phone["id"], keyword["id"]],
        "group_id": group["id"],
        "sample_id": sample["id"],
        "run_id": run["id"],
        "run_output": run["output_text"],
        "hit_count": run["hit_count"],
    }


def main():
    base = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:18105"
    result = seed(base)
    print("初始化样例数据完成：")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
