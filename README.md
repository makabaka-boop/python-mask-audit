# python-mask-audit

脱敏规则审计沙盒服务 —— 纯后端，使用 Python 标准库实现的 HTTP API。

数据治理团队可在接触真实业务数据前，先用样例文本验证脱敏规则是否
**稳定、可重复、可追踪**，并能回放每次演练所使用的规则配置。

- 监听端口：**18105**
- 存储：**SQLite**（单文件，零外部依赖）
- API 前缀：所有路径以 `/api/v1` 开头
- 字段命名：统一 `snake_case`
- 错误响应固定为：

  ```json
  {"error_code": "...", "message": "...", "details": {}}
  ```

## 运行

```bash
python3 run.py
# 或
python3 -m app
```

启动后访问健康检查：

```bash
curl http://127.0.0.1:18105/api/v1/health
```

数据库文件默认位于项目根目录 `mask_audit.db`，可用环境变量 `MASK_AUDIT_DB` 覆盖
（测试即通过该变量指向临时库）。

## 初始化样例数据

服务启动后，可运行脚本一键创建规则、分组、样例并执行一次分组演练，
形成完整的审计链路（演练记录 + 命中明细 + 规则快照），方便验证：

```bash
python3 scripts/seed.py                  # 默认连接 http://127.0.0.1:18105
python3 scripts/seed.py http://host:port # 指定目标
```

随后调用 `GET /api/v1/selfcheck` 应返回 `passed: true`。

## 运行测试

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

覆盖替换策略幂等性、短文本保护、匹配方式校验、regex 编译校验、
禁用规则不参与分组演练、预览不落库、规则冲突检测（三类）、冲突不阻断执行、
回归一致/不一致及快照差异说明、规则/样例/分组三维度审计聚合、
一致性自检（通过/异常）、初始化数据可用、所有接口保持 `/api/v1` 前缀等关键行为，共 60 个用例。

## 目录结构

代码按职责拆分清楚：

| 文件 | 职责 |
| --- | --- |
| [config.py](file:///Users/zhangxinyu/sunxidan/9999-gsb/0731-new/python-mask-audit/app/config.py) | 端口、DB 路径、枚举等常量 |
| [db.py](file:///Users/zhangxinyu/sunxidan/9999-gsb/0731-new/python-mask-audit/app/db.py) | SQLite 连接与建表（8 张表） |
| [errors.py](file:///Users/zhangxinyu/sunxidan/9999-gsb/0731-new/python-mask-audit/app/errors.py) | 统一错误类型与错误响应结构 |
| [strategies.py](file:///Users/zhangxinyu/sunxidan/9999-gsb/0731-new/python-mask-audit/app/strategies.py) | 三种替换策略（含幂等与短文本保护） |
| [executor.py](file:///Users/zhangxinyu/sunxidan/9999-gsb/0731-new/python-mask-audit/app/executor.py) | 规则执行器（三种匹配方式） |
| [snapshot.py](file:///Users/zhangxinyu/sunxidan/9999-gsb/0731-new/python-mask-audit/app/snapshot.py) | 规则快照封存 |
| [repositories.py](file:///Users/zhangxinyu/sunxidan/9999-gsb/0731-new/python-mask-audit/app/repositories.py) | 仓储层，SQL 与业务校验集中于此 |
| [audit_queries.py](file:///Users/zhangxinyu/sunxidan/9999-gsb/0731-new/python-mask-audit/app/audit_queries.py) | 规则/样例/分组三维度审计聚合 |
| [selfcheck.py](file:///Users/zhangxinyu/sunxidan/9999-gsb/0731-new/python-mask-audit/app/selfcheck.py) | 交付前一致性自检（7 项检查） |
| [routes.py](file:///Users/zhangxinyu/sunxidan/9999-gsb/0731-new/python-mask-audit/app/routes.py) | 路由表与请求处理（演练/预览/回归逻辑） |
| [server.py](file:///Users/zhangxinyu/sunxidan/9999-gsb/0731-new/python-mask-audit/app/server.py) | HTTP 服务器与 JSON 编解码 |
| [scripts/seed.py](file:///Users/zhangxinyu/sunxidan/9999-gsb/0731-new/python-mask-audit/scripts/seed.py) | 初始化样例数据脚本 |
| [tests/](file:///Users/zhangxinyu/sunxidan/9999-gsb/0731-new/python-mask-audit/tests) | 单元测试 + 集成测试 |

## 数据模型（SQLite）

| 表 | 关键字段 |
| --- | --- |
| `rules` | rule_name, field_type, match_type, match_value, replace_strategy, replace_config, priority, enabled, created_at, updated_at |
| `groups` | group_name, description, created_at |
| `group_members` | group_id, rule_id, added_at |
| `samples` | sample_name, sample_category, raw_text, expected_note, created_at |
| `runs` | sample_id, rule_id, group_id, input_text, output_text, hit_count, executed_at |
| `hit_details` | run_id, rule_id, matched_count, before_fragment, after_fragment |
| `rule_snapshots` | run_id, rule_id, rule_name, enabled, priority, match_type, replace_strategy, replace_config |
| `audit_events` | event_type, entity_type, entity_id, detail, created_at |

## 规则约束

- **匹配方式** `match_type` 仅允许：`exact`、`contains`、`regex`
- **替换策略** `replace_strategy` 仅允许：`fixed`、`keep_edges`、`middle_mask`
- `regex` **入库前必须编译校验**，编译失败返回 `validation_error`
- `match_value` **不能为空**
- **禁用规则不参与分组演练**（也不允许单条执行）
- `keep_edges` 的 `replace_config` 支持 `left`、`right`、`mask_char`
- `middle_mask` 遇到短文本时**不会把全部字符都替换掉**（至少保留一个字符）
- **脱敏执行幂等**：同一文本重复执行同一规则不会持续增加掩码字符

### replace_config 示例

```jsonc
// fixed：整体替换为固定文本
{"value": "[PHONE]"}

// keep_edges：保留左右边缘，中间用 mask_char 填充
{"left": 3, "right": 4, "mask_char": "*"}

// middle_mask：遮蔽中间，保留首尾
{"keep_left": 1, "keep_right": 1, "mask_char": "*"}
```

## 接口一览（均以 `/api/v1` 开头）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| POST | `/rules` | 创建规则 |
| GET | `/rules` | 规则列表 |
| GET | `/rules/{id}` | 规则详情 |
| POST | `/rules/{id}/enable` | 启用规则 |
| POST | `/rules/{id}/disable` | 停用规则 |
| POST | `/rules/{id}/priority` | 调整优先级 |
| GET | `/rules/{id}/stats` | 统计规则命中次数 |
| POST | `/groups` | 创建分组 |
| GET | `/groups` | 分组列表 |
| GET | `/groups/{id}/members` | 分组成员 |
| POST | `/groups/{id}/members` | 分组添加规则 |
| DELETE | `/groups/{id}/members/{rule_id}` | 分组移除规则 |
| GET | `/groups/{id}/conflicts` | 规则冲突检测（只提示风险，不阻断） |
| POST | `/samples` | 创建样例 |
| GET | `/samples` | 样例列表 |
| GET | `/samples/{id}` | 样例详情 |
| POST | `/runs/rule` | 执行单条规则（写入演练记录） |
| POST | `/runs/group` | 按分组执行演练（写入演练记录） |
| GET | `/runs` | 演练记录列表 |
| GET | `/runs/{id}` | 演练明细 + 规则快照 |
| GET | `/runs/{id}/snapshots` | 规则快照 |
| POST | `/preview` | 脱敏预览（只返回结果与命中明细，**不落库**） |
| POST | `/regression` | 回归验证（基于样例最近一次演练快照比较当前规则变化） |
| GET | `/audit/events` | 审计事件列表 |
| GET | `/audit/rules/{id}` | 规则维度审计（当前配置/历史版本/累计命中/最近命中时间） |
| GET | `/audit/samples/{id}` | 样例维度审计（最近演练/最近回归/命中分布） |
| GET | `/audit/groups/{id}` | 分组维度审计（当前成员/历史成员/成员变化执行差异） |
| GET | `/selfcheck` | 一致性自检（交付前检查审计链路断点） |

### 执行 / 预览 / 回归 请求体

```jsonc
// 单条执行
POST /api/v1/runs/rule
{"rule_id": 1, "input_text": "call 13800001111"}   // 或 {"rule_id":1,"sample_id":2}

// 分组执行（仅启用规则参与，按 priority 升序应用）
POST /api/v1/runs/group
{"group_id": 1, "sample_id": 2}                     // 或 input_text

// 预览：不写入演练记录
POST /api/v1/preview
{"rule_id": 1, "input_text": "..."}                 // 或 group_id

// 回归验证：重放样例最近一次使用过的分组，复用首轮快照比较差异
POST /api/v1/regression
{"sample_id": 2}
```

回归验证会定位样例**最近一次基于分组的演练记录**，重新用当前分组的启用
规则执行，并**复用首轮定义的规则快照**（不只比较最终文本）进行归因。
返回字段包括基线输出/命中数、当前输出/命中数、`output_consistent`（两段
最终文本是否一致）、`consistent`（结果与配置是否完全一致）以及
`differences` —— 逐条列出差异及其来源类型：

| difference_type | 含义 |
| --- | --- |
| `member_change` | 分组成员较首轮发生增删 |
| `priority_change` | 规则优先级较首轮变化 |
| `replace_config_change` | 替换策略或替换配置较首轮变化 |
| `rule_config_change` | 规则核心配置（enabled / match_type）较首轮变化 |

即使两段最终文本相同，只要快照字段（如优先级）发生变化，`consistent`
仍为 `false` 并给出差异说明。

### 规则冲突检测

`GET /api/v1/groups/{id}/conflicts` 在执行前识别分组内规则可能互相覆盖的
问题，返回 `items` 列表，每项包含 `rule_ids`、`conflict_type`、`message`、
`severity`。至少检测三类：

| conflict_type | 含义 | severity |
| --- | --- | --- |
| `duplicate_exact` | 同一 `field_type` 下完全相同的 exact 规则 | high |
| `contains_overlap` | contains 规则的匹配值互相包含 | medium |
| `same_priority_different_replace` | 优先级相同但替换策略或配置不同 | medium |

冲突检测**只返回风险提示**，不阻止保存规则、加入分组或执行演练。

### 审计查询（规则 / 样例 / 分组三维度）

演练、预览、回归验证、规则启停、优先级调整、分组成员变更都会写入审计事件
（`GET /api/v1/audit/events`）；其中**预览只写审计事件，不写入演练记录与命中
明细**。在此基础上提供三个维度的历史聚合视图：

- `GET /api/v1/audit/rules/{id}` — 规则维度：`current_config`、`history_versions`
  （历史快照中出现过的去重配置版本）、`total_matched`、`hit_records`、`last_hit_at`。
- `GET /api/v1/audit/samples/{id}` — 样例维度：`latest_run`、`latest_regression`
  （最近一次回归验证结果）、`rule_hit_distribution`（各规则命中分布）。
- `GET /api/v1/audit/groups/{id}` — 分组维度：`current_members`、`history_members`
  （历史快照成员）、`member_change_summary`（相对历史成员的增减，以及相邻两次演练
  之间成员变化后的执行差异摘要 `run_transitions`）。

读侧聚合集中在 [audit_queries.py](file:///Users/zhangxinyu/sunxidan/9999-gsb/0731-new/python-mask-audit/app/audit_queries.py)，其依赖的 SQL 仍收敛在 `repositories.py`。

### 一致性自检

`GET /api/v1/selfcheck` 供交付前确认脱敏审计链路没有断点，返回统一 JSON：
顶层 `passed`（整体是否通过）、`total_problems`，以及 `checks` 数组，逐项列出
检查名称、`passed`、`problem_count` 与 `problems` 明细。检查项：

| check | 检查内容 |
| --- | --- |
| `orphan_hit_details` | 孤立命中明细（run_id 找不到演练记录） |
| `group_run_missing_snapshot` | 有命中的分组演练却缺失规则快照 |
| `hit_detail_snapshot_mismatch` | 命中明细的规则与该演练快照无法对应 |
| `preview_leaked_into_runs` | 预览数据误落库（rule_id 与 group_id 均空的演练） |
| `disabled_rule_in_run` | 禁用规则参与了分组演练（快照 enabled=0） |
| `invalid_regex_rules` | 非法正则残留（regex 规则无法编译） |
| `regression_missing_baseline` | 回归验证缺少历史基准（baseline_run_id 不存在） |

检查逻辑在 [selfcheck.py](file:///Users/zhangxinyu/sunxidan/9999-gsb/0731-new/python-mask-audit/app/selfcheck.py)。
