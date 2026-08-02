# python-mask-audit

脱敏规则审计沙盒服务，帮助数据治理人员在接触真实业务数据前，使用样本文本验证脱敏规则的**稳定性、可重复性、可追踪性**，并能够回放每次演练所使用的规则配置（快照）。

- 纯后端 Python HTTP API（Flask）
- SQLite 持久化：规则、分组、样例、演练记录、命中明细、规则快照、审计事件
- 统一前缀 `/api/v1`，字段统一为 `snake_case`
- 统一错误响应：`{"error_code":"...","message":"...","details":{...}}`
- 默认监听 `0.0.0.0:18105`

---

## 目录结构

```
python-mask-audit/
├── app/
│   ├── __init__.py            # 包入口，导出 create_app
│   ├── main.py                # 应用工厂、启动入口
│   ├── config.py              # 配置
│   ├── database.py            # SQLite 连接、建表 SQL
│   ├── errors.py              # 统一异常与错误处理
│   ├── validators.py          # 字段/枚举/regex 校验
│   ├── strategies.py          # 三种替换策略实现
│   ├── rule_executor.py       # 规则匹配/替换/幂等执行器
│   ├── conflict_detector.py   # 规则冲突检测
│   ├── consistency.py         # 链路一致性自检
│   ├── services.py            # 业务服务层（演练、快照、回归、统计、冲突、自检）
│   ├── repositories/          # 仓储层（规则/分组/样例/演练/快照/审计）
│   └── routers/               # HTTP 路由（Blueprint 分模块）
├── scripts/
│   └── seed_data.py           # 初始化样例数据脚本
├── tests/                     # pytest 测试
├── requirements.txt
├── run.py                     # 启动脚本
└── README.md
```

---

## 快速开始

```bash
# 安装依赖
pip3 install -r requirements.txt

# 启动服务（默认 0.0.0.0:18105）
python3 run.py

# 健康检查
curl http://127.0.0.1:18105/api/v1/health
```

环境变量：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `MASK_AUDIT_HOST` | `0.0.0.0` | 监听地址 |
| `MASK_AUDIT_PORT` | `18105` | 监听端口 |
| `MASK_AUDIT_DB` | `./mask_audit.db` | SQLite 数据库路径 |
| `MASK_AUDIT_DEBUG` | `0` | 是否开启 Flask debug |

---

## 数据模型

### 规则 rules
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `rule_name` | str | 规则名称 |
| `field_type` | str | 字段类型（phone/email/id_card 等自定义） |
| `match_type` | enum | `exact` / `contains` / `regex` |
| `match_value` | str | 匹配值，**regex 入库前会被编译校验，不能为空** |
| `replace_strategy` | enum | `fixed` / `keep_edges` / `middle_mask` |
| `replace_config` | object | 替换参数（见下） |
| `priority` | int | 数值越小越先执行 |
| `enabled` | bool | 是否启用，**禁用规则不能参与分组演练，也不能加入分组** |
| `created_at` / `updated_at` | datetime | 时间戳 |

`replace_config`：

- `fixed`：`{"replacement": "[REDACTED]"}`
- `keep_edges`：`{"left": 3, "right": 2, "mask_char": "*"}`
- `middle_mask`：`{"mask_char": "*"}`（长度 ≤ 2 时保持原文，不会把全部字符替换掉）

### 分组 groups / group_members
- `group_name`、`description`、`created_at`
- 通过 `group_members` 关联规则与分组，`(group_id, rule_id)` 唯一。

### 样例 samples
- `sample_name`、`sample_category`、`raw_text`、`expected_note`、`created_at`。

### 演练记录 runs
- `sample_id`、`rule_id`、`group_id`、`input_text`、`output_text`、`hit_count`、`executed_at`。

### 命中明细 hit_details
- `run_id`、`rule_id`、`matched_count`、`before_fragment`、`after_fragment`。

### 规则快照 rule_snapshots
每次演练时封存参与执行的规则副本：`rule_id`、`rule_name`、`enabled`、`priority`、`match_type`、`match_value`、`replace_strategy`、`replace_config`。

### 审计事件 audit_events
- `event_type`、`entity_type`、`entity_id`、`detail`、`created_at`。

---

## 幂等性保证

规则执行器对每个匹配片段都**基于原始匹配片段**计算替换结果，并从后向前应用到文本上。对已脱敏文本重复执行同一规则：

- 原匹配模式（如手机号正则 `1[3-9]\d{9}`）在已脱敏字符串上不再命中；
- `replace_config` 只影响原始命中片段，不会让已有的 `*` 继续增加。

因此同一文本重复执行同一规则，输出稳定且可重复。

---

## API 列表

所有接口前缀 `/api/v1`。

### 健康检查
- `GET /health`

### 规则
- `GET /rules?enabled=true|false` 列出规则
- `POST /rules` 创建规则
- `GET /rules/<id>` 查看规则
- `PUT /rules/<id>` 更新规则
- `POST /rules/<id>/enable` 启用
- `POST /rules/<id>/disable` 禁用
- `POST /rules/<id>/priority` 调整优先级，body `{"priority": 10}`
- `DELETE /rules/<id>` 删除规则

### 分组
- `GET /groups`
- `POST /groups`，body `{"group_name":"pii","description":"..."}`
- `GET /groups/<id>`（含规则列表）
- `POST /groups/<id>/rules`，body `{"rule_id": 1}`
- `DELETE /groups/<id>/rules/<rule_id>`
- `GET /groups/<id>/rules`
- `GET /groups/<id>/conflicts` 冲突检测（见下）
- `DELETE /groups/<id>`

### 样例
- `GET /samples?category=...`
- `POST /samples`
- `GET /samples/<id>`
- `DELETE /samples/<id>`

### 演练
- `POST /runs/single`，body `{"rule_id":1,"text":"...","sample_id":1}`
- `POST /runs/group`，body `{"group_id":1,"text":"...","sample_id":1}`
- `GET /runs?sample_id=&rule_id=&group_id=&limit=50`
- `GET /runs/<id>` 查看演练明细（含命中明细）
- `GET /runs/<id>/snapshot` 查看当次规则快照

### 预览（不写演练记录）
- `POST /preview/rule/<id>`，body `{"text":"..."}`
- `POST /preview/group/<id>`，body `{"text":"..."}`

### 回归验证
- `GET /regression?run_id=<id>` 对比指定演练快照
- `GET /regression?sample_id=<id>` 对比该样例最近一次演练
- `GET /regression?group_id=<id>` 对比该分组最近一次演练

返回内容（关键字段）：

- `consistent`：基于**首轮规则快照**重放后的输出与当前分组成员重放输出是否一致；
- `baseline_output` / `current_output`：两侧重放结果（而不是只比较最终文本，而是实际执行两组规则）；
- `change_categories`：将差异归因为四类：
  - `rule_config_changed`：匹配方式或匹配值变化；
  - `priority_changed`：优先级变化；
  - `replace_config_changed`：替换策略或替换配置变化；
  - `membership_changed`：分组成员新增/移除（或规则被禁用）。
- `member_changes`：成员增删明细；
- `snapshot_diff`：每条规则的字段级差异说明。

### 冲突检测
- `GET /groups/<id>/conflicts?include_disabled=0|1`

对分组内规则进行静态冲突分析，**只返回风险提示，不会阻止规则保存、加入分组或演练执行**。每条冲突结构：

```json
{
  "rule_ids": [1, 2],
  "conflict_type": "duplicate_exact",
  "message": "...",
  "severity": "high"
}
```

检测的三类冲突（同一 `field_type` 下）：

| conflict_type | 含义 | severity |
| --- | --- | --- |
| `duplicate_exact` | 存在完全相同的 exact 规则（match_value 相同） | high |
| `contains_overlap` | contains 规则之间存在包含关系（外层会覆盖内层命中） | medium |
| `same_priority_diff` | 优先级相同但替换策略或替换配置不同，执行顺序不稳定 | medium |

### 统计
- `GET /stats/hits` 每条规则累计命中次数与演练次数。

### 审计查询（按规则 / 样例 / 分组三个维度）
- `GET /audit/events?limit=100` 全局事件流
- `GET /audit/rules/<id>` 规则维度：
  - `current_config` 当前规则配置
  - `config_versions` 历史快照中出现过的配置版本
  - `total_hit_count` / `run_count` / `last_hit_at` 累计命中与最近命中时间
  - `recent_events` 该规则相关事件
- `GET /audit/samples/<id>` 样例维度：
  - `latest_run` / `latest_hit_details` 最近演练
  - `latest_regression` 最近一次回归验证结果
  - `rule_hit_distribution` 各规则命中分布
- `GET /audit/groups/<id>` 分组维度：
  - `current_members` 当前成员
  - `snapshot_members` 历次演练封存的快照成员
  - `latest_run` / `latest_hit_details` 最近演练
  - `member_change_summary` 成员增删变更摘要

> 预览接口 `POST /preview/...` 会写入 `preview_executed` 审计事件，但**不会**写入 `runs` / `hit_details` / `rule_snapshots`。回归验证接口会写入 `regression_executed` 事件。规则启停、优先级调整、分组成员变更均会写审计。

### 一致性自检
- `GET /consistency/checks`

检查脱敏审计链路是否存在断点，返回统一 JSON：

```json
{
  "status": "ok",
  "all_passed": true,
  "total_issue_count": 0,
  "checks": [
    {"name": "orphan_hit_details", "passed": true, "issue_count": 0, "details": []}
  ]
}
```

检查项：

| name | 含义 |
| --- | --- |
| `orphan_hit_details` | 命中明细引用了不存在的演练 |
| `group_run_without_snapshot` | 分组演练缺失规则快照 |
| `snapshot_hit_mismatch` | 同一次演练中命中明细的 rule_id 无法对应到快照 |
| `preview_persisted` | 预览数据被错误写入 runs 表 |
| `disabled_rule_in_run` | 禁用规则参与了演练（快照 enabled=false） |
| `invalid_regex_residue` | 规则表中残留无法编译的正则 |
| `regression_no_baseline` | 存在样例或分组但从未演练过，无法回归 |

### 初始化样例数据
```bash
python3 scripts/seed_data.py
```
脚本会创建 3 条规则（手机号、邮箱、身份证）、一个分组 `seed_pii`、一条样例，并执行一次分组演练，便于一键验证完整链路。脚本执行后可调用 `/consistency/checks` 确认无断点。

---

## 错误响应

```json
{
  "error_code": "validation_error",
  "message": "match_value 不能为空",
  "details": { "field": "match_value" }
}
```

常见 `error_code`：`validation_error`、`regex_invalid`、`not_found`、`conflict`、`rule_disabled`、`method_not_allowed`、`internal_error`。

---

## 测试

```bash
python3 -m pytest tests/ -v
```

测试覆盖：三种替换策略、匹配模式、优先级顺序、禁用规则跳过、幂等性、规则/分组/演练/快照/回归/统计/审计/冲突检测/一致性自检的完整 HTTP 流程、初始化数据脚本以及统一错误格式；所有业务接口均使用 `/api/v1` 前缀。
