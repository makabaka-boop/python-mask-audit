"""初始化样例数据脚本。

创建规则、分组、样例文本，并执行一次分组演练，方便验证完整链路。

用法:
    python -m scripts.seed_data
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db
from app.repositories.rule_repo import RuleRepository
from app.repositories.group_repo import GroupRepository
from app.repositories.sample_repo import SampleRepository
from app.repositories.run_repo import RunRepository
from app.core.snapshot import SnapshotService
from app.services.executor import RuleExecutor


def seed():
    init_db()
    db = SessionLocal()
    try:
        existing = RuleRepository.list_all(db)
        if existing:
            print("数据库中已存在规则，跳过初始化。如需重新初始化请先删除 mask_audit.db。")
            return

        print("=== 创建规则 ===")

        phone_rule = RuleRepository.create(
            db,
            rule_name="手机号脱敏",
            field_type="phone",
            match_type="regex",
            match_value=r"1[3-9]\d{9}",
            replace_strategy="keep_edges",
            replace_config={"left": 3, "right": 4, "mask_char": "*"},
            priority=10,
            enabled=True,
        )
        print(f"  规则 {phone_rule.id}: {phone_rule.rule_name}")

        id_rule = RuleRepository.create(
            db,
            rule_name="身份证脱敏",
            field_type="id_card",
            match_type="regex",
            match_value=r"\d{17}[\dXx]",
            replace_strategy="keep_edges",
            replace_config={"left": 4, "right": 4, "mask_char": "*"},
            priority=20,
            enabled=True,
        )
        print(f"  规则 {id_rule.id}: {id_rule.rule_name}")

        secret_rule = RuleRepository.create(
            db,
            rule_name="密钥固定替换",
            field_type="secret",
            match_type="contains",
            match_value="SECRET",
            replace_strategy="fixed",
            replace_config={"replacement": "[REDACTED]"},
            priority=30,
            enabled=True,
        )
        print(f"  规则 {secret_rule.id}: {secret_rule.rule_name}")

        name_rule = RuleRepository.create(
            db,
            rule_name="姓名中间掩码",
            field_type="name",
            match_type="exact",
            match_value="张三",
            replace_strategy="middle_mask",
            replace_config={"mask_char": "*"},
            priority=5,
            enabled=True,
        )
        print(f"  规则 {name_rule.id}: {name_rule.rule_name}")

        print()
        print("=== 创建分组 ===")

        group = GroupRepository.create(
            db,
            group_name="客户信息脱敏组",
            description="手机号、身份证、姓名、密钥组合脱敏",
        )
        for rule in [phone_rule, id_rule, secret_rule, name_rule]:
            GroupRepository.add_rule(db, group.id, rule.id)
        print(f"  分组 {group.id}: {group.group_name} (包含 4 条规则)")

        print()
        print("=== 创建样例 ===")

        sample1 = SampleRepository.create(
            db,
            sample_name="客户联系信息",
            sample_category="contact",
            raw_text=(
                "客户张三，手机号13812345678，身份证110101199001011234，"
                "密钥SECRET-ABC-123。"
            ),
            expected_note="手机号保留前3后4，身份证保留前4后4，密钥替换为[REDACTED]，姓名保留首尾",
        )
        print(f"  样例 {sample1.id}: {sample1.sample_name}")

        sample2 = SampleRepository.create(
            db,
            sample_name="多手机号文本",
            sample_category="contact",
            raw_text="联系电话：13812345678 / 15987654321，紧急联系人李四。",
            expected_note="两个手机号均应脱敏",
        )
        print(f"  样例 {sample2.id}: {sample2.sample_name}")

        print()
        print("=== 执行分组演练 ===")

        rules = GroupRepository.get_rules(db, group.id, enabled_only=True)
        rule_dicts = [r.to_dict() for r in rules]
        snapshot = SnapshotService.create_snapshot(
            db, group_id=group.id, rules=rule_dicts, label="seed_initial"
        )

        result = RuleExecutor.execute_group(sample1.raw_text, rule_dicts)
        run = RunRepository.create(
            db,
            sample_id=sample1.id,
            rule_id=None,
            group_id=group.id,
            input_text=sample1.raw_text,
            output_text=result["output_text"],
            hit_count=result["hit_count"],
            snapshot_id=snapshot.id,
        )
        for hd in result["hit_details"]:
            RunRepository.add_hit_detail(
                db, run_id=run.id, rule_id=hd["rule_id"],
                matched_count=hd["matched_count"],
                before_fragment=hd["before_fragment"],
                after_fragment=hd["after_fragment"],
            )
        print(f"  演练 {run.id}: 命中 {run.hit_count} 次")
        print(f"  输入: {run.input_text}")
        print(f"  输出: {run.output_text}")
        print(f"  快照: {snapshot.id}")

        print()
        print("=== 初始化完成 ===")
        print(f"  规则数: 4")
        print(f"  分组数: 1")
        print(f"  样例数: 2")
        print(f"  演练记录: {run.id}")
        print()
        print("访问 http://localhost:18105/api/v1/health 检查服务状态")
        print("访问 http://localhost:18105/docs 查看 Swagger 文档")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
