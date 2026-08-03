# mask-audit 脱敏规则沙盒服务

数据治理人员用于维护脱敏规则、组合规则分组、演练样例文本、封存规则快照、预览脱敏效果、执行回归验证、检测规则冲突、查询审计历史以及自检链路一致性的后端沙盒服务。重点考察 Python API 设计、SQLite 建模、规则执行器、幂等脱敏处理与审计自检能力。

- 服务名称：mask-audit
- 默认端口：`18105`
- API 前缀：`/api/v1`
- SQLite 文件：项目根目录下 `mask_audit.db`（可通过 `MASK_AUDIT_DB` 环境变量自定义）
- 技术栈：Python 3.9+、FastAPI、SQLAlchemy 2.x、SQLite、Pydantic v2、pytest
- 字段命名：统一使用 `snake_case`
- 错误结构：`{"error_code":"...","message":"...","details":{...}}`
- 交互式文档：服务启动后访问 `http://localhost:18105/docs`

---

## 目录

1. [项目概览](#1-项目概览)
2. [架构图](#2-架构图)
3. [快速开始](#3-快速开始)
4. [配置说明](#4-配置说明)
5. [API 文档](#5-api-文档)
6. [替换策略说明](#6-替换策略说明)
7. [快照与回归](#7-快照与回归)
8. [幂等性保证](#8-幂等性保证)
9. [错误码表](#9-错误码表)
10. [测试说明](#10-测试说明)
11. [项目结构](#11-项目结构)

---

## 1. 项目概览

mask-audit 是一个面向数据治理场景的脱敏规则验证沙盒，核心能力包括：

- **规则管理**：创建、查询、更新、删除脱敏规则，支持精确匹配、包含匹配、正则匹配三种匹配方式。
- **规则分组**：将多条规则组合成分组，按优先级顺序级联执行。
- **样例管理**：维护待脱敏的样例文本，按类别归类。
- **演练执行**：对单条规则或整个分组执行脱敏演练，持久化输入、输出、命中次数与命中片段。
- **效果预览**：不落库的即时预览，便于在保存规则前验证效果。
- **快照封存**：分组执行时自动封存参与规则的完整配置快照。
- **回归验证**：将当前规则与历史快照对比，识别新增、删除、变更与未变更的规则；支持对样例重新执行并解释结果差异原因。
- **冲突检测**：识别分组内规则之间可能互相覆盖的问题，包括重复 exact 规则、contains 规则互相包含、相同优先级但替换策略不同。
- **审计事件**：对关键写操作与执行操作记录审计日志。

---

## 2. 架构图

```
+-----------------------------+
|        客户端 / 调用方         |
+--------------+--------------+
               |
               |  HTTP / JSON
               v
+-----------------------------+
|        FastAPI 应用层         |
|  app/main.py (入口 / 异常处理) |
+--------------+--------------+
               |
               v
+-----------------------------+
|      API 路由层 (api/v1)      |
| health rules groups samples  |
| runs preview regression      |
| snapshots conflicts          |
+--------------+--------------+
               |
               v
+-----------------------------+
|       服务层 (services)       |
| matcher  -> 匹配文本片段      |
| replacer -> 替换策略执行      |
| executor -> 单规则/分组编排   |
+--------------+--------------+
               |
               v
+-----------------------------+
|       核心层 (core)           |
| errors  统一错误与响应        |
| snapshot 快照封存与对比       |
| conflict 规则冲突检测         |
| audit   审计事件记录          |
+--------------+--------------+
               |
               v
+-----------------------------+
|     数据访问层 (repositories) |
| rule / group / sample / run  |
| snapshot / audit             |
+--------------+--------------+
               |
               v
+-----------------------------+
|  模型层 (models) | 模式层(schemas) |
|  SQLAlchemy ORM | Pydantic v2    |
+--------------+--------------+
               |
               v
+-----------------------------+
|        SQLite 数据库          |
|     (mask_audit.db)          |
+-----------------------------+
```

请求流向：客户端 → API 路由 → 服务层（匹配/替换/执行）→ 仓储层 → SQLite。核心层在执行过程中穿插完成快照封存与审计记录。

---

## 3. 快速开始

### 3.1 环境要求

- Python 3.9 及以上
- pip

### 3.2 安装依赖

```bash
cd python-mask-audit
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

依赖清单（`requirements.txt`）：

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy==2.0.35
pydantic==2.9.2
pytest==8.3.3
httpx==0.27.2
```

### 3.3 启动服务

开发模式（模块方式启动）：

```bash
python -m app.main
```

或使用 uvicorn 直接启动：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 18105
```

服务启动时会自动初始化数据库表结构（通过 SQLAlchemy `create_all`）。

启动成功后：

- 健康检查：http://localhost:18105/api/v1/health
- Swagger 文档：http://localhost:18105/docs
- ReDoc 文档：http://localhost:18105/redoc

### 3.4 初始化样例数据

服务启动后，可运行初始化脚本创建规则、分组、样例和一次演练记录，方便验证完整链路：

```bash
python -m scripts.seed_data
```

脚本会创建 4 条规则（手机号、身份证、密钥、姓名）、1 个分组、2 条样例，并执行一次分组演练自动生成快照和命中明细。若数据库中已存在规则则跳过。

### 3.5 运行测试

```bash
pytest -v
```

---

## 4. 配置说明

配置通过环境变量注入，定义在 `app/config.py`，无需额外配置文件。

| 环境变量 | 说明 | 默认值 |
| --- | --- | --- |
| `MASK_AUDIT_DB` | SQLite 数据库文件路径 | 项目根目录下 `mask_audit.db` |
| `MASK_AUDIT_HOST` | 服务监听地址 | `0.0.0.0` |
| `MASK_AUDIT_PORT` | 服务监听端口 | `18105` |

示例：

```bash
export MASK_AUDIT_DB=/data/mask_audit.db
export MASK_AUDIT_HOST=127.0.0.1
export MASK_AUDIT_PORT=18105
python -m app.main
```

---

## 5. API 文档

所有接口前缀为 `/api/v1`，请求与响应均使用 JSON，字段命名为 `snake_case`。

### 5.1 健康检查

#### GET /health

检查服务存活状态。

```bash
curl http://localhost:18105/api/v1/health
```

响应示例：

```json
{
  "status": "ok"
}
```

---

### 5.2 规则管理

#### POST /rules

创建一条脱敏规则。创建时会编译并校验正则表达式，`match_value` 不允许为空。

请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `rule_name` | string | 是 | 规则名称 |
| `field_type` | string | 否 | 字段类型，自由文本，如 `phone`、`id_card` |
| `match_type` | string | 是 | 匹配类型：`exact` / `contains` / `regex` |
| `match_value` | string | 是 | 匹配值，正则类型需为合法正则 |
| `replace_strategy` | string | 是 | 替换策略：`fixed` / `keep_edges` / `middle_mask` |
| `replace_config` | object | 否 | 替换配置，见[替换策略](#6-替换策略说明) |
| `priority` | integer | 否 | 优先级，数值越小越先执行，默认 `100` |
| `enabled` | boolean | 否 | 是否启用，默认 `true` |

```bash
curl -X POST http://localhost:18105/api/v1/rules \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "手机号脱敏",
    "field_type": "phone",
    "match_type": "regex",
    "match_value": "1[3-9]\\d{9}",
    "replace_strategy": "keep_edges",
    "replace_config": {"left": 3, "right": 4, "mask_char": "*"},
    "priority": 10,
    "enabled": true
  }'
```

#### GET /rules

查询规则列表。

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `enabled_only` | boolean | 仅返回启用的规则，默认 `false` |

```bash
curl "http://localhost:18105/api/v1/rules?enabled_only=true"
```

#### GET /rules/{rule_id}

按 ID 查询单条规则。

```bash
curl http://localhost:18105/api/v1/rules/1
```

#### PUT /rules/{rule_id}

全量更新规则。同样会校验正则合法性与 `match_value` 非空。

```bash
curl -X PUT http://localhost:18105/api/v1/rules/1 \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "手机号脱敏-更新",
    "field_type": "phone",
    "match_type": "regex",
    "match_value": "1[3-9]\\d{9}",
    "replace_strategy": "middle_mask",
    "replace_config": {"mask_char": "*"},
    "priority": 20,
    "enabled": true
  }'
```

#### DELETE /rules/{rule_id}

删除一条规则。

```bash
curl -X DELETE http://localhost:18105/api/v1/rules/1
```

#### PATCH /rules/{rule_id}/enabled

切换规则启用状态。

请求体：

```json
{ "enabled": false }
```

```bash
curl -X PATCH http://localhost:18105/api/v1/rules/1/enabled \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

#### PATCH /rules/{rule_id}/priority

调整规则优先级。

请求体：

```json
{ "priority": 5 }
```

```bash
curl -X PATCH http://localhost:18105/api/v1/rules/1/priority \
  -H "Content-Type: application/json" \
  -d '{"priority": 5}'
```

---

### 5.3 规则分组

#### POST /groups

创建分组。

请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `group_name` | string | 是 | 分组名称 |
| `description` | string | 否 | 分组描述 |

```bash
curl -X POST http://localhost:18105/api/v1/groups \
  -H "Content-Type: application/json" \
  -d '{"group_name": "客户信息脱敏组", "description": "手机号与身份证组合脱敏"}'
```

#### GET /groups

查询全部分组。

```bash
curl http://localhost:18105/api/v1/groups
```

#### GET /groups/{group_id}

查询分组详情，包含其下规则列表。

```bash
curl http://localhost:18105/api/v1/groups/1
```

#### PUT /groups/{group_id}

更新分组名称与描述。

```bash
curl -X PUT http://localhost:18105/api/v1/groups/1 \
  -H "Content-Type: application/json" \
  -d '{"group_name": "客户信息脱敏组-v2", "description": "更新描述"}'
```

#### DELETE /groups/{group_id}

删除分组（同时解除组内规则关联）。

```bash
curl -X DELETE http://localhost:18105/api/v1/groups/1
```

#### POST /groups/{group_id}/rules

向分组添加规则。

请求体：

```json
{ "group_id": 1, "rule_id": 3 }
```

> 路径中的 `group_id` 与请求体中的 `group_id` 应保持一致。

```bash
curl -X POST http://localhost:18105/api/v1/groups/1/rules \
  -H "Content-Type: application/json" \
  -d '{"group_id": 1, "rule_id": 3}'
```

#### DELETE /groups/{group_id}/rules/{rule_id}

从分组中移除一条规则。

```bash
curl -X DELETE http://localhost:18105/api/v1/groups/1/rules/3
```

#### GET /groups/{group_id}/rules

查询分组下的规则。

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `enabled_only` | boolean | 仅返回启用规则，默认 `false` |

```bash
curl "http://localhost:18105/api/v1/groups/1/rules?enabled_only=true"
```

---

### 5.4 样例文本

#### POST /samples

创建样例文本。

请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sample_name` | string | 是 | 样例名称 |
| `sample_category` | string | 否 | 样例类别 |
| `raw_text` | string | 是 | 原始文本 |
| `expected_note` | string | 否 | 预期说明 |

```bash
curl -X POST http://localhost:18105/api/v1/samples \
  -H "Content-Type: application/json" \
  -d '{
    "sample_name": "客户联系信息",
    "sample_category": "contact",
    "raw_text": "客户张三，手机号13812345678，身份证110101199001011234。",
    "expected_note": "手机号与身份证均应被脱敏"
  }'
```

#### GET /samples

查询样例列表，可按类别过滤。

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `category` | string | 按样例类别过滤 |

```bash
curl "http://localhost:18105/api/v1/samples?category=contact"
```

#### GET /samples/{sample_id}

查询单条样例。

```bash
curl http://localhost:18105/api/v1/samples/1
```

#### PUT /samples/{sample_id}

更新样例。

```bash
curl -X PUT http://localhost:18105/api/v1/samples/1 \
  -H "Content-Type: application/json" \
  -d '{
    "sample_name": "客户联系信息-更新",
    "sample_category": "contact",
    "raw_text": "客户李四，手机号13987654321。",
    "expected_note": "仅脱敏手机号"
  }'
```

#### DELETE /samples/{sample_id}

删除样例。

```bash
curl -X DELETE http://localhost:18105/api/v1/samples/1
```

---

### 5.5 演练执行

#### POST /runs/single

对单条规则执行脱敏演练，并持久化演练记录。禁用规则无法执行。

请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `rule_id` | integer | 是 | 规则 ID |
| `sample_id` | integer | 否 | 样例 ID，与 `input_text` 至少提供一个 |
| `input_text` | string | 否 | 直接输入的文本，优先级高于 `sample_id` |

```bash
curl -X POST http://localhost:18105/api/v1/runs/single \
  -H "Content-Type: application/json" \
  -d '{"rule_id": 1, "input_text": "联系电话13812345678"}'
```

#### POST /runs/group

对整个分组执行级联脱敏演练。执行前会自动封存一份参与规则的快照，并将 `snapshot_id` 记录在演练记录中。仅启用的规则参与执行。

请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sample_id` | integer | 是 | 样例 ID |
| `group_id` | integer | 是 | 分组 ID |

```bash
curl -X POST http://localhost:18105/api/v1/runs/group \
  -H "Content-Type: application/json" \
  -d '{"sample_id": 1, "group_id": 1}'
```

#### GET /runs/{run_id}

查询演练详情，包含 `hit_details` 命中片段明细。

```bash
curl http://localhost:18105/api/v1/runs/1
```

响应中 `hit_details` 结构示例：

```json
{
  "id": 1,
  "sample_id": 1,
  "rule_id": null,
  "group_id": 1,
  "input_text": "原始文本",
  "output_text": "脱敏后文本",
  "hit_count": 2,
  "snapshot_id": 1,
  "executed_at": "2026-08-03T10:00:00",
  "hit_details": [
    {
      "id": 1,
      "run_id": 1,
      "rule_id": 1,
      "matched_count": 1,
      "before_fragment": "13812345678",
      "after_fragment": "138****5678"
    }
  ]
}
```

#### GET /runs

查询演练记录列表，支持按样例、规则、分组过滤。`sample_id`、`rule_id`、`group_id` 三个过滤参数按优先级取第一个非空值。

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `sample_id` | integer | 按样例过滤 |
| `rule_id` | integer | 按规则过滤 |
| `group_id` | integer | 按分组过滤 |
| `limit` | integer | 返回条数上限，默认 `50` |

```bash
curl "http://localhost:18105/api/v1/runs?group_id=1&limit=20"
```

#### GET /runs/stats/rules

查询规则命中统计。指定 `rule_id` 时返回单条规则统计，否则返回全部规则的汇总统计。

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `rule_id` | integer | 可选，指定规则 ID |

```bash
curl "http://localhost:18105/api/v1/runs/stats/rules?rule_id=1"
```

---

### 5.6 效果预览

#### POST /preview

即时预览单条规则的脱敏效果，不产生任何持久化记录。禁用规则同样可用于预览（预览不校验启用状态）。

请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `rule_id` | integer | 是 | 规则 ID |
| `sample_id` | integer | 否 | 样例 ID，与 `input_text` 至少提供一个 |
| `input_text` | string | 否 | 直接输入的文本 |

```bash
curl -X POST http://localhost:18105/api/v1/preview \
  -H "Content-Type: application/json" \
  -d '{"rule_id": 1, "input_text": "电话13812345678"}'
```

---

### 5.7 回归验证

#### GET /regression/group/{group_id}

将指定分组的当前规则与其最近一次封存的快照进行对比。若分组无任何快照则返回校验错误。

```bash
curl http://localhost:18105/api/v1/regression/group/1
```

响应示例：

```json
{
  "snapshot_id": 1,
  "group_id": 1,
  "rules_changed": [2],
  "rules_added": [5],
  "rules_removed": [3],
  "rules_unchanged": [1, 4],
  "is_passed": false
}
```

#### GET /regression/snapshot/{snapshot_id}

以指定快照为基准，与其所属分组的当前规则进行对比。快照未关联分组时返回校验错误。

```bash
curl http://localhost:18105/api/v1/regression/snapshot/1
```

---

### 5.9 快照查询

#### GET /snapshots/{snapshot_id}

查询单个快照详情，包含其封存的所有规则条目。

```bash
curl http://localhost:18105/api/v1/snapshots/1
```

#### GET /snapshots

查询快照列表，可按分组过滤。

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `group_id` | integer | 按分组过滤 |

```bash
curl "http://localhost:18105/api/v1/snapshots?group_id=1"
```

---

## 6. 替换策略说明

所有替换策略通过 `replace_config` 字段配置。若配置项缺失，使用下表中的默认值。

### 6.1 fixed（整段固定替换）

将命中的文本整体替换为固定字符串。

配置项：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `replacement` | string | `***` | 替换文本 |

示例：

| 输入片段 | 配置 | 输出 |
| --- | --- | --- |
| `13812345678` | `{"replacement": "***"}` | `***` |
| `张三` | `{"replacement": "[REDACTED]"}` | `[REDACTED]` |

### 6.2 keep_edges（保留两端，中间掩码）

保留命中文本左侧与右侧的若干字符，将中间部分替换为掩码字符。对短文本有特殊处理，且具备幂等性。

配置项：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `left` | integer | `1` | 左侧保留字符数 |
| `right` | integer | `1` | 右侧保留字符数 |
| `mask_char` | string | `*` | 掩码字符 |

短文本处理规则：

- 文本长度为 0：原样返回。
- 文本长度 `<= left`：保留首字符，其余全部掩码。
- 文本长度 `<= left + right`：保留前 `left` 个字符，其余全部掩码。
- 否则：保留前 `left` 与后 `right` 个字符，中间全部掩码。

示例（`left=3, right=4, mask_char="*"`）：

| 输入片段 | 输出 | 说明 |
| --- | --- | --- |
| `13812345678` | `138****5678` | 保留前 3 后 4 |
| `12345` | `123**` | 长度 `<= left+right(7)` |
| `12` | `1*` | 长度 `<= left(3)` |
| `a` | `a` | 长度为 1 时保留首字符 |

### 6.3 middle_mask（首尾保留，中间掩码）

保留命中文本的首尾字符，将中间字符全部掩码。长度不超过 2 的文本不做掩码，天然具备幂等性。

配置项：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `mask_char` | string | `*` | 掩码字符 |

处理规则：

- 长度 `<= 2`：原样返回，绝不把短文本全部掩码。
- 长度 `> 2`：保留首字符与尾字符，中间替换为掩码字符，掩码长度等于中间字符数。

示例：

| 输入片段 | 输出 | 说明 |
| --- | --- | --- |
| `张三丰` | `张*丰` | 保留首尾 |
| `13812345678` | `1*********8` | 中间 9 位掩码 |
| `ab` | `ab` | 长度 2，不变 |
| `a` | `a` | 长度 1，不变 |

---

## 7. 快照与回归

### 7.1 快照（Snapshot）

快照是某一时刻分组内参与执行规则的完整配置副本，包含以下字段：

- 规则 ID、规则名称
- `enabled` 启用状态
- `priority` 优先级
- `match_type`、`match_value` 匹配配置
- `replace_strategy`、`replace_config` 替换配置

**封存时机**：每次调用 `POST /api/v1/runs/group` 执行分组演练时，系统会在执行前自动为该分组创建一份快照，标签格式为 `run_group_{sample_id}`，并将 `snapshot_id` 写入本次演练记录。

快照一旦写入即不可变，用于事后追溯“当时按什么规则执行的”。

### 7.2 回归（Regression）

回归对比将“当前规则集”与“历史快照”逐条比对，输出四类结果：

| 结果字段 | 含义 |
| --- | --- |
| `rules_changed` | 规则仍存在，但匹配方式、匹配值、替换策略、替换配置、优先级或启用状态发生变化 |
| `rules_added` | 当前分组中存在、但快照中不存在的规则（新增） |
| `rules_removed` | 快照中存在、但当前分组中已不存在的规则（删除） |
| `rules_unchanged` | 配置完全一致的规则 |
| `is_passed` | 上述三类差异均为空时为 `true`，否则为 `false` |

两种回归入口：

- `GET /regression/group/{group_id}`：自动取该分组最近一次快照作为基准。
- `GET /regression/snapshot/{snapshot_id}`：以指定快照为基准，与其所属分组的当前规则对比。

回归操作本身会写入审计事件，便于追踪谁在何时做了回归验证。

#### POST /regression/replay

对指定样例重新执行最近一次使用过的规则分组，将新结果与历史演练结果逐字比较，并复用首轮封存的规则快照分析差异来源。不只是比较最终文本，而是逐条对照快照中的规则配置。

请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `sample_id` | integer | 是 | 样例 ID |
| `group_id` | integer | 是 | 分组 ID |

```bash
curl -X POST http://localhost:18105/api/v1/regression/replay \
  -H "Content-Type: application/json" \
  -d '{"sample_id": 1, "group_id": 1}'
```

响应示例（规则替换配置发生变化导致输出不一致）：

```json
{
  "sample_id": 1,
  "group_id": 1,
  "snapshot_id": 1,
  "run_id": 1,
  "historical_output": "code *** and N**E here",
  "current_output": "code ### and N**E here",
  "is_consistent": false,
  "diff_reasons": [
    "替换配置变化（替换策略或参数变更）"
  ],
  "rules_added": [],
  "rules_removed": [],
  "rules_changed": [
    {
      "rule_id": 1,
      "rule_name": "手机号脱敏",
      "diff_fields": ["replace_config"]
    }
  ],
  "rules_unchanged": [2, 3]
}
```

`diff_reasons` 可能包含以下类型：

- 分组成员变化：新增规则 / 移除规则
- 规则配置变化（匹配方式或匹配值变更）
- 优先级变化（执行顺序改变）
- 替换配置变化（替换策略或参数变更）
- 启用状态变化（规则被启用或禁用）
- 规则存在差异但本次样例输出一致（差异未影响此样例）

---

### 5.8 规则冲突检测

#### GET /conflicts/groups/{group_id}

检测指定分组内规则之间可能存在的冲突，返回风险提示列表。冲突检测仅作为建议，**不阻止**规则保存、加入分组或执行演练。

```bash
curl http://localhost:18105/api/v1/conflicts/groups/1
```

响应示例：

```json
{
  "group_id": 1,
  "total": 3,
  "conflicts": [
    {
      "rule_ids": [1, 2],
      "conflict_type": "duplicate_exact",
      "message": "字段类型 'phone' 下存在 2 条完全相同的 exact 规则...",
      "severity": "high"
    },
    {
      "rule_ids": [3, 1],
      "conflict_type": "contains_overlap",
      "message": "字段类型 'phone' 下规则 3 ('ECR') 的匹配值被规则 1 ('SECRET') 包含...",
      "severity": "medium"
    },
    {
      "rule_ids": [1, 4],
      "conflict_type": "priority_conflict",
      "message": "规则 1 与 4 优先级相同 (priority=10)，但替换策略不同...",
      "severity": "medium"
    }
  ]
}
```

检测的三类冲突：

| conflict_type | severity | 说明 |
| --- | --- | --- |
| `duplicate_exact` | high | 同一 `field_type` 下存在完全相同的 `exact` 规则（`match_value` 一致），会导致重复脱敏 |
| `contains_overlap` | medium | 同一 `field_type` 下 `contains`/`exact` 规则的匹配值存在包含关系，先执行的规则可能覆盖后执行规则的匹配范围 |
| `priority_conflict` | medium | 优先级相同但替换策略或替换配置不同，执行顺序不确定可能导致结果不稳定 |

---

### 5.9 审计查询

从规则、样例、分组三个维度追踪演练历史。

#### GET /audit/rules/{rule_id}

规则维度：返回当前配置、历史快照中出现过的配置版本、累计命中次数、最近一次命中时间。

```bash
curl http://localhost:18105/api/v1/audit/rules/1
```

响应包含：`current_config`（完整规则对象）、`config_versions`（去重后的历史配置版本列表）、`total_hits`、`last_hit_at`。

#### GET /audit/samples/{sample_id}

样例维度：返回最近演练记录（含命中明细）、最近回归验证结果、各规则命中分布。

```bash
curl http://localhost:18105/api/v1/audit/samples/1
```

响应包含：`latest_run`、`latest_regression`、`rule_hit_distribution`（每条规则的命中次数和最近命中时间）。

#### GET /audit/groups/{group_id}

分组维度：返回当前成员、历史快照成员列表、成员变化后的执行差异摘要。

```bash
curl http://localhost:18105/api/v1/audit/groups/1
```

响应包含：`current_members`、`historical_snapshots`、`member_change_diff`（added/removed 规则及可读摘要）。

#### GET /audit/events

查询审计事件列表，支持按 `event_type`、`target_type`、`target_id` 过滤和 `limit` 分页。

```bash
curl "http://localhost:18105/api/v1/audit/events?event_type=RUN_GROUP&limit=10"
```

---

### 5.10 一致性自检

#### GET /consistency

检查脱敏审计链路是否存在断点，返回统一 JSON，按 `checks` 数组列出每项检查的名称、通过状态、问题数量和明细。

```bash
curl http://localhost:18105/api/v1/consistency
```

响应示例：

```json
{
  "all_passed": true,
  "total_issues": 0,
  "checks": [
    {"check_name": "orphan_hit_details", "passed": true, "issue_count": 0, "details": []},
    {"check_name": "group_run_missing_snapshot", "passed": true, "issue_count": 0, "details": []},
    {"check_name": "snapshot_hit_mismatch", "passed": true, "issue_count": 0, "details": []},
    {"check_name": "preview_data_leaked", "passed": true, "issue_count": 0, "details": []},
    {"check_name": "disabled_rule_in_run", "passed": true, "issue_count": 0, "details": []},
    {"check_name": "invalid_regex_residual", "passed": true, "issue_count": 0, "details": []},
    {"check_name": "regression_missing_baseline", "passed": true, "issue_count": 0, "details": []}
  ]
}
```

检查项说明：

| check_name | 检查内容 |
| --- | --- |
| `orphan_hit_details` | 孤立命中明细（hit_details 引用了不存在的 run_records） |
| `group_run_missing_snapshot` | 分组演练记录缺失快照（group_id 非空但 snapshot_id 为空） |
| `snapshot_hit_mismatch` | 快照与命中明细无法对应（规则不在快照范围内或快照中为禁用状态却命中） |
| `preview_data_leaked` | 预览数据误落库（matched_count=0 的命中明细、来源不明的演练记录） |
| `disabled_rule_in_run` | 已禁用规则在演练中产生了命中明细 |
| `invalid_regex_residual` | 数据库中残留无法编译的非法正则规则 |
| `regression_missing_baseline` | 存在演练记录的分组缺少快照，无法进行回归验证 |

---

### 5.11 快照查询

#### GET /snapshots/{snapshot_id}

查询单个快照详情，包含其封存的所有规则条目。

```bash
curl http://localhost:18105/api/v1/snapshots/1
```

#### GET /snapshots

查询快照列表，可按分组过滤。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `group_id` | integer | 按分组过滤 |

```bash
curl "http://localhost:18105/api/v1/snapshots?group_id=1"
```

---

## 8. 幂等性保证

脱敏操作可能被重复应用于已经脱敏过的文本（例如级联执行、重复演练或文本多次流经同一规则）。本服务对掩码类策略保证幂等：对同一段文本使用同一条规则重复执行，输出不会累积掩码字符。

实现要点（见 `app/services/replacer.py`）：

- **keep_edges**：在替换前检查待掩码的中间段。如果中间段已经全部由 `mask_char` 组成，则原样返回，不再重复掩码。
- **middle_mask**：在替换前检查首尾之间的内部段。如果内部段已经全部由 `mask_char` 组成，则原样返回。
- **fixed**：输出恒为配置的 `replacement`，重复执行结果一致。

示例（`middle_mask`）：

| 执行次数 | 输入 | 输出 |
| --- | --- | --- |
| 第 1 次 | `张三丰` | `张*丰` |
| 第 2 次 | `张*丰` | `张*丰`（不变） |
| 第 3 次 | `张*丰` | `张*丰`（不变） |

示例（`keep_edges`，`left=3, right=4`）：

| 执行次数 | 输入 | 输出 |
| --- | --- | --- |
| 第 1 次 | `13812345678` | `138****5678` |
| 第 2 次 | `138****5678` | `138****5678`（中间已是 `*`，不变） |

此外，`middle_mask` 与 `keep_edges` 对短文本都有保护：`middle_mask` 对长度不超过 2 的文本不做任何掩码，`keep_edges` 对短于保留长度的文本按降级规则处理，确保不会把文本全部抹除。

---

## 9. 错误码表

所有错误响应均采用统一结构：

```json
{
  "error_code": "ERROR_CODE",
  "message": "可读的错误描述",
  "details": {}
}
```

| HTTP 状态码 | error_code | 说明 |
| --- | --- | --- |
| 400 | `RULE_DISABLED` | 规则已禁用，无法参与执行 |
| 404 | `NOT_FOUND` | 请求的资源（规则/分组/样例/演练/快照等）不存在 |
| 409 | `CONFLICT` | 资源冲突，例如重复添加关联 |
| 422 | `VALIDATION_ERROR` | 业务校验失败（如 `match_value` 为空、分组无启用规则、分组无快照等） |
| 422 | `REGEX_COMPILE_ERROR` | 正则表达式编译失败 |
| 422 | `VALIDATION_ERROR`（框架层） | 请求参数 Pydantic 校验失败，`details.errors` 含字段级错误 |
| 500 | `INTERNAL_ERROR` | 服务器内部未预期错误 |

错误响应示例：

```json
{
  "error_code": "REGEX_COMPILE_ERROR",
  "message": "正则表达式编译失败",
  "details": {"reason": "missing ), unterminated subpattern"}
}
```

---

## 10. 测试说明

项目使用 `pytest` 作为测试框架，并借助 `httpx` 对 FastAPI 应用进行接口级测试。

运行全部测试：

```bash
pytest -v
```

运行指定测试文件：

```bash
pytest tests/test_rules.py -v
```

运行并打印输出：

```bash
pytest -v -s
```

测试建议覆盖的核心场景：

- 规则 CRUD 与正则合法性校验
- `fixed` / `keep_edges` / `middle_mask` 三种替换策略的正确性
- 短文本边界处理
- 幂等性：对已脱敏文本重复执行结果不变
- 分组按 `priority` 排序级联执行，禁用规则不参与
- 分组执行自动生成快照
- 回归对比能正确识别 changed / added / removed / unchanged
- 回放回归能重新执行样例并基于快照解释差异原因（规则配置、分组成员、优先级、替换配置）
- 冲突检测能识别 duplicate_exact / contains_overlap / priority_conflict 三类冲突
- 冲突检测不阻断规则保存、加入分组或演练执行
- 审计查询能从规则、样例、分组三个维度正确聚合历史数据
- 预览写入审计事件但不写入演练记录和命中明细
- 一致性自检在正常数据下全部通过
- 一致性自检能检测孤立命中明细、缺失快照、非法正则、禁用规则参与演练等异常
- 初始化脚本能创建完整的规则、分组、样例和演练记录
- 所有新增接口均保持 /api/v1 前缀
- 统一错误响应结构与错误码

---

## 11. 项目结构

```
python-mask-audit/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用入口、生命周期、异常处理
│   ├── config.py            # 环境变量配置（DB / HOST / PORT / API 前缀）
│   ├── database.py          # SQLAlchemy 引擎、会话、建表初始化
│   ├── models/              # SQLAlchemy ORM 模型
│   │   ├── rule.py          # Rule
│   │   ├── group.py         # RuleGroup / GroupMember
│   │   ├── sample.py        # SampleText
│   │   ├── run.py           # RunRecord / HitDetail
│   │   ├── snapshot.py      # RuleSnapshot / SnapshotItem
│   │   └── audit.py         # AuditEvent
│   ├── schemas/             # Pydantic v2 请求/响应模式
│   │   ├── common.py
│   │   ├── rule.py
│   │   ├── group.py
│   │   ├── sample.py
│   │   ├── run.py
│   │   ├── conflict.py
│   │   ├── audit_view.py
│   │   └── consistency.py
│   ├── repositories/        # 数据访问层
│   │   ├── rule_repo.py
│   │   ├── group_repo.py
│   │   ├── sample_repo.py
│   │   ├── run_repo.py
│   │   ├── snapshot_repo.py
│   │   └── audit_repo.py
│   ├── services/            # 核心业务逻辑
│   │   ├── matcher.py       # exact / contains / regex 匹配
│   │   ├── replacer.py      # 三种替换策略与幂等处理
│   │   ├── executor.py      # 单规则执行与分组级联编排
│   │   └── audit_query.py   # 三维度审计历史聚合
│   ├── core/                # 横切核心能力
│   │   ├── errors.py        # 统一错误定义与异常处理器
│   │   ├── snapshot.py      # 快照封存、对比与差异分类
│   │   ├── conflict.py      # 规则冲突检测
│   │   ├── consistency.py   # 链路一致性自检
│   │   └── audit.py         # 审计事件记录
│   └── api/
│       └── v1/              # API v1 路由模块
│           ├── __init__.py  # 汇总注册 api_router
│           ├── health.py
│           ├── rules.py
│           ├── groups.py
│           ├── samples.py
│           ├── runs.py
│           ├── preview.py
│           ├── regression.py
│           ├── conflicts.py
│           ├── snapshots.py
│           ├── audit.py
│           └── consistency.py
├── scripts/
│   ├── __init__.py
│   └── seed_data.py         # 初始化样例数据脚本
├── tests/                   # pytest 测试
│   ├── conftest.py
│   ├── test_replacer.py
│   ├── test_matcher.py
│   ├── test_executor.py
│   ├── test_api_rules.py
│   ├── test_api_groups.py
│   ├── test_api_samples.py
│   ├── test_api_runs.py
│   ├── test_api_preview.py
│   ├── test_api_regression.py
│   ├── test_conflict.py
│   ├── test_replay_regression.py
│   ├── test_audit_view.py
│   └── test_consistency.py
├── requirements.txt
├── mask_audit.db            # 运行后自动生成的 SQLite 文件
└── README.md
```

### 数据模型字段速查

| 模型 | 关键字段 |
| --- | --- |
| `Rule` | `id`, `rule_name`, `field_type`, `match_type`, `match_value`, `replace_strategy`, `replace_config`(JSON), `priority`, `enabled`, `created_at`, `updated_at` |
| `RuleGroup` | `id`, `group_name`, `description`, `created_at` |
| `GroupMember` | `id`, `group_id`, `rule_id`, `created_at` |
| `SampleText` | `id`, `sample_name`, `sample_category`, `raw_text`, `expected_note`, `created_at` |
| `RunRecord` | `id`, `sample_id`, `rule_id`, `group_id`, `input_text`, `output_text`, `hit_count`, `snapshot_id`, `executed_at` |
| `HitDetail` | `id`, `run_id`, `rule_id`, `matched_count`, `before_fragment`, `after_fragment` |
| `RuleSnapshot` | `id`, `group_id`, `label`, `created_at` |
| `SnapshotItem` | `id`, `snapshot_id`, `rule_id`, `rule_name`, `enabled`, `priority`, `match_type`, `match_value`, `replace_strategy`, `replace_config` |
| `AuditEvent` | `id`, `event_type`, `target_type`, `target_id`, `detail`, `created_at` |
