# python-mask-audit

脱敏规则审计沙盒，帮助数据治理人员在接触真实业务数据前，用样例文本验证脱敏规则是否**稳定、可重复、可追踪**，并能回放每次演练所使用的规则快照。

纯后端 HTTP API 服务，基于 Python + Flask + SQLite，监听 **18105** 端口。

## 快速开始

```bash
pip install flask pytest      # 仅依赖 flask，pytest 用于测试
python3 run.py                # 启动服务，监听 0.0.0.0:18105
python3 scripts/seed.py       # 可选：初始化样例规则/分组/样例并完成一次演练
python3 -m pytest tests/      # 运行测试（38 个用例）
```

SQLite 数据文件默认位于项目根目录的 `mask_audit.db`，首次启动自动建表；`create_app(db_path)` 可指定其他路径（测试使用临时文件）。`scripts/seed.py` 可重复执行，同名规则/分组会复用，输出本次演练的输入/输出与 hit_count。

## 目录结构

```
app/
  __init__.py       # create_app 工厂
  database.py       # SQLite 连接与建表（rules/rule_groups/group_members/samples/
                    # drill_runs/hit_details/rule_snapshots/audit_events）
  errors.py         # ApiError 与统一错误响应
  strategies.py     # 替换策略：fixed / keep_edges / middle_mask（幂等）
  conflicts.py      # 规则冲突检测（duplicate_exact / contains_overlap / 同优先级不同替换）
  audit_queries.py  # 审计查询：规则/样例/分组三维度聚合
  executor.py       # 规则校验、匹配（exact/contains/regex）、按优先级执行
  snapshot.py       # 规则快照构建、快照/当前规则 diff 与差异归因
  repositories.py   # 仓储层：全部 SQL 访问
  routes.py         # 路由层：/api/v1 全部接口
  selfcheck.py      # 一致性自检：7 项链路完整性检查
run.py              # 服务入口（18105）
scripts/seed.py     # 初始化样例数据（规则/分组/样例/一次演练）
tests/test_api.py   # 端到端 API 测试
```

## 数据库 Schema（SQLite，8 张表）

| 表 | 关键字段 |
| --- | --- |
| rules | id、rule_name(唯一)、field_type、match_type(exact/contains/regex)、match_value、replace_strategy(fixed/keep_edges/middle_mask)、replace_config(JSON)、priority、enabled、created_at、updated_at |
| rule_groups | id、group_name(唯一)、description、created_at |
| group_members | id、group_id、rule_id、created_at，(group_id, rule_id) 唯一 |
| samples | id、sample_name、sample_category、raw_text、expected_note、created_at |
| drill_runs | id、sample_id、rule_id、group_id、input_text、output_text、hit_count、executed_at |
| hit_details | id、run_id、rule_id、matched_count、before_fragment、after_fragment |
| rule_snapshots | id、run_id、rule_id、rule_name、enabled、priority、match_type、match_value、replace_strategy、replace_config |
| audit_events | id、event_type、entity_type、entity_id、detail(JSON)、created_at |

## 接口一览（统一前缀 /api/v1，字段 snake_case）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /health | 健康检查 |
| POST | /rules | 创建规则（regex 入库前编译校验，match_value 非空） |
| GET | /rules 、 /rules/{id} | 规则列表 / 详情 |
| PATCH | /rules/{id}/status | 启停规则 `{enabled: bool}` |
| PATCH | /rules/{id}/priority | 调整优先级 `{priority: int}` |
| POST | /groups | 创建分组 `{group_name, description}` |
| GET | /groups 、 /groups/{id}/rules | 分组列表 / 分组成员 |
| POST | /groups/{id}/rules | 分组添加规则 `{rule_id}` |
| DELETE | /groups/{id}/rules/{rule_id} | 分组移除规则 |
| GET | /groups/{id}/conflicts | 规则冲突检测（只提示风险，不阻断任何操作） |
| POST | /samples | 创建样例 `{sample_name, sample_category, raw_text, expected_note}` |
| GET | /samples | 样例列表 |
| POST | /rules/{id}/execute | 单条规则演练（禁用规则拒绝执行），写入演练记录+命中明细+快照 |
| POST | /groups/{id}/execute | 分组演练（仅启用规则参与），输入支持 `sample_id` 或 `input_text` |
| GET | /runs/{id} | 演练明细（含 hit_details） |
| GET | /runs/{id}/snapshot | 演练的规则快照 |
| GET | /rules/{id}/stats | 规则命中统计（run_count / total_hits） |
| POST | /preview | 脱敏预览，只返回结果与命中明细，**不写入演练记录** |
| POST | /regression | 回归验证：基于最近一次演练快照对比当前规则变化并重跑；只传 `sample_id` 时自动定位该样例最近使用的分组 |
| GET | /audits | 审计事件列表 |
| GET | /audit/rules/{id} | 审计查询·规则维度：当前配置、历史快照配置版本、累计命中、最近命中时间 |
| GET | /audit/samples/{id} | 审计查询·样例维度：最近演练、最近回归验证结果、各规则命中分布 |
| GET | /audit/groups/{id} | 审计查询·分组维度：当前成员、历史快照成员、成员变化后的执行差异摘要 |
| GET | /selfcheck | 一致性自检：7 项链路完整性检查，只读不修改数据 |

错误响应统一为：

```json
{"error_code": "VALIDATION_ERROR", "message": "match_value 不能为空", "details": {}}
```

## 关键设计

- **匹配方式**：`exact`（区分大小写子串）、`contains`（不区分大小写子串）、`regex`（创建时 `re.compile` 校验，非法正则拒绝入库）。
- **替换策略**：
  - `fixed`：整体替换为 `replace_config.replacement`；
  - `keep_edges`：保留左右 `left`/`right` 个字符，中间用 `mask_char` 打码；文本长度不足时兜底保留首字符；
  - `middle_mask`：保留首尾字符中间打码，可用 `mask_count` 指定打码个数；长度 ≤1 的文本不做替换，保证短文本不会被全部替换掉。
- **幂等验证**：片段已是替换结果或中间部分已全为掩码字符时原样返回，同一文本重复执行同一规则不会持续增加星号；`test_execute_is_idempotent` 验证二次执行 hit_count 为 0 且输出不变。
- **执行顺序**：分组演练按 `priority` 降序、规则 ID 升序执行，结果可重复；禁用规则不参与分组演练。
- **规则快照**：每次演练把参与规则的 ID、名称、启用状态、优先级、匹配方式、替换策略、替换配置封存到 `rule_snapshots`，可通过 `/runs/{id}/snapshot` 回放。
- **冲突检测**：`GET /groups/{id}/conflicts` 输出 `{rule_ids, conflict_type, message, severity}`，覆盖三类场景——同一 field_type 下完全相同的 exact 规则（high）、contains 规则匹配值互相包含（medium）、优先级相同但替换策略或替换配置不同（low）。仅提示风险，不阻止保存规则、加入分组或执行演练。
- **回归验证**：`/regression` 复用最近一次演练封存的规则快照，与当前分组成员逐字段 diff（modified/added/deleted），并用快照时的输入文本按当前启用规则重跑，比较输出与命中数。结果不一致时 `diff_sources` 逐项说明差异来源：`member_change`（分组成员变化）、`priority_change`（优先级变化）、`replace_config_change`（替换配置变化）、`rule_config_change`（匹配方式/匹配值/替换策略/启用状态等规则配置变化），绝不仅比较最终文本。
- **审计事件**：创建规则、启停、调优先级、分组成员变更、创建样例、演练、预览、回归验证、冲突检测均写入 `audit_events`；预览只写审计事件，仍不写演练记录和命中明细。
- **审计查询**（[audit_queries.py](app/audit_queries.py)）：纯聚合查询不修改数据。
  - 规则维度：当前配置 + `config_versions`（历史快照中出现的全部配置版本及首见/最近 run、出现次数）+ 累计命中 + 最近命中时间；
  - 样例维度：最近 10 次演练（倒序）+ 最近一次回归验证结果（passed/output_changed/change_count）+ 各规则命中分布；
  - 分组维度：当前成员 + 历史快照成员（含出现次数）+ `member_change_summary`（最近两次演练的成员增删、命中数与输出差异；输入不一致时 output_changed 置空，避免错误归因）。
- **一致性自检**：`GET /selfcheck` 返回 `{passed, check_count, failed_count, checks[]}`，每项检查含 `check_name / passed / issue_count / details`（明细最多 20 条）。覆盖 7 项：`orphan_hit_details`（孤立命中明细）、`group_run_missing_snapshot`（缺失快照的分组演练）、`snapshot_hit_mismatch`（快照与命中明细无法对应）、`preview_residue_in_runs`（预览数据误落库）、`disabled_rule_participation`（快照中禁用的规则却产生命中）、`invalid_regex_residue`（绕过校验的非法正则残留）、`regression_missing_baseline`（回归验证缺少历史基准）。自检只读，每次调用写一条 `selfcheck` 审计事件。

## 示例

```bash
curl -X POST http://127.0.0.1:18105/api/v1/rules -H 'Content-Type: application/json' -d '{
  "rule_name": "手机号", "field_type": "phone", "match_type": "regex",
  "match_value": "1\\d{10}", "replace_strategy": "keep_edges",
  "replace_config": {"left": 3, "right": 4}, "priority": 10
}'

curl -X POST http://127.0.0.1:18105/api/v1/groups/1/execute \
  -H 'Content-Type: application/json' \
  -d '{"input_text": "客户手机13812345678请回电"}'
# => {"output_text": "客户手机138****5678请回电", "hit_count": 1, "run_id": 1, ...}

curl -X POST http://127.0.0.1:18105/api/v1/regression \
  -H 'Content-Type: application/json' -d '{"group_id": 1}'
# => {"passed": true, "rule_changes": [], "output_changed": false, ...}
```
