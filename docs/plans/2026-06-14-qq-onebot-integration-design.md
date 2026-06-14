# QQ OneBot Integration Design

日期：2026-06-14

## 背景

当前项目已经跑通本地 Web MVP：家长添加孩子和 QQ 号，创建作业，后台扫描到期作业，并写入模拟 QQ 提醒日志。下一步要把模拟发送替换为真实 QQ 发消息能力，但仍保持项目本身轻量、单机、本地运行。

本设计选择本地 QQ 机器人网关方案。项目不直接处理 QQ 登录、协议连接或风控细节，而是调用兼容 OneBot v11 的本机 HTTP 网关。推荐本地实现可以是 NapCat 或 Lagrange；本项目只依赖 OneBot HTTP API。

## 目标

1. 到期作业可以通过 OneBot HTTP 网关发送 QQ 私聊消息。
2. 未配置真实网关时，系统继续支持模拟发送，方便开发和测试。
3. 发送成功或失败都写入提醒日志，便于家长排查。
4. 发送失败时作业保持 `pending`，下一轮扫描继续重试。
5. QQ 网关实现可替换，不把代码绑定到 NapCat 的专有能力。

## 非目标

- 不在本项目内实现 QQ 登录、扫码登录或协议连接。
- 不支持 QQ 群消息、多人批量消息或富媒体消息。
- 不做复杂重试策略、退避、重试次数上限或告警。
- 不做公网部署、多用户隔离或鉴权。
- 不新增主动测试发送按钮，避免误发消息。

## 方案选择

### 方案 A：OneBot HTTP 适配器（采用）

新增一个 OneBot HTTP sender。后台提醒流程调用：

```text
POST {ONEBOT_BASE_URL}/send_private_msg
```

请求体：

```json
{
  "user_id": 123456,
  "message": "作业提醒内容",
  "auto_escape": true
}
```

OneBot v11 的 `send_private_msg` 使用 `user_id` 表示对方 QQ 号，`message` 表示消息内容，成功响应包含 `message_id`。如果配置了 access token，请求头带：

```text
Authorization: Bearer <token>
```

优点是项目只依赖稳定的 OneBot 语义，NapCat、Lagrange 等实现可以替换。缺点是用户需要另外启动 QQ 网关。

### 方案 B：仅抽象 Sender，暂不接真实网关

先把模拟发送拆成插件式接口，后续再加 OneBot。这个方案风险最低，但不能满足“下一步真实发 QQ”的目标。

### 方案 C：直接绑定 NapCat

围绕 NapCat 做具体配置和状态检查。这个方案落地最具体，但会让项目更难替换其他 OneBot 实现。

最终采用方案 A，同时保留 sender 抽象，避免后续替换网关时改动提醒业务逻辑。

## 架构

新增 `app/qq_sender.py`，提供三个核心概念：

- `SendMessageRequest`：目标 QQ、消息正文、作业上下文。
- `SendMessageResult`：provider、success、provider_message_id、error_message。
- `BaseSender`：统一发送接口。

实现两个 sender：

- `SimulatedSender`：开发和测试默认使用，不访问外部服务。
- `OneBotHttpSender`：调用本机 OneBot HTTP API。

`process_due_reminders()` 不再直接把“写成功日志”等同于“发送成功”，而是先构造消息，再调用 sender，然后根据结果写日志和更新作业状态。

## 配置

使用环境变量配置，避免引入额外配置文件：

```text
QQ_SENDER=simulated | onebot
ONEBOT_BASE_URL=http://127.0.0.1:3000
ONEBOT_ACCESS_TOKEN=
ONEBOT_TIMEOUT_SECONDS=5
```

默认值：

- `QQ_SENDER=simulated`
- `ONEBOT_TIMEOUT_SECONDS=5`

当 `QQ_SENDER=onebot` 时，`ONEBOT_BASE_URL` 必填。启动时不主动连接网关，避免网关未启动时阻止本地管理页面打开。

## 数据模型

扩展 `reminder_logs`：

- `provider TEXT NOT NULL DEFAULT 'simulated'`
- `provider_message_id TEXT`

现有字段继续保留：

- `target_qq`
- `message`
- `scheduled_at`
- `sent_at`
- `status`
- `error_message`

SQLite 初始化需要兼容旧数据库：如果字段不存在，则通过轻量迁移添加字段。

## 提醒处理流程

后台扫描流程：

1. 查询 `status = 'pending'` 且 `remind_at <= now` 的作业。
2. 生成提醒消息。
3. 调用当前 sender。
4. 如果发送成功：
   - 在事务中将作业状态更新为 `reminded`，条件仍带 `status = 'pending'`。
   - 写入 `reminder_logs.status = 'success'`。
   - 记录 `provider` 和 `provider_message_id`。
5. 如果发送失败：
   - 写入 `reminder_logs.status = 'failed'`。
   - 记录 `provider` 和 `error_message`。
   - 作业保持 `pending`，下次扫描继续重试。

如果作业在发送期间被取消，最终更新 `status = 'reminded'` 会因为条件不匹配失败；这种情况下不写成功日志。

## 错误处理

OneBot sender 把这些情况视为发送失败：

- 网关连接失败。
- 请求超时。
- HTTP 状态码不是 2xx。
- JSON 解析失败。
- 响应中的 `status` 不是 `ok`。
- 响应缺少可识别的成功结果。

失败日志只记录简短错误，不记录 access token。后台扫描处理单条作业失败时继续处理后续作业。

## API 和界面

第一阶段不新增写接口。现有 `GET /api/reminder-logs` 增加返回字段：

- `provider`
- `provider_message_id`

管理页面的提醒日志增加两列或紧凑展示：

- 发送方式：`simulated` / `onebot`
- 外部消息 ID：成功时显示

可选新增只读接口：

```text
GET /api/qq-sender/status
```

返回当前 sender 类型和配置完整性，但不发送测试消息。

## 测试策略

后端测试：

- 默认配置使用 `SimulatedSender`，现有提醒测试继续通过。
- OneBot sender 对 `/send_private_msg` 发送正确 JSON。
- 配置 token 时发送 `Authorization: Bearer ...`。
- OneBot 成功响应会写 `success` 日志，并保存 `provider_message_id`。
- 连接失败、超时、非 2xx 或失败响应会写 `failed` 日志，作业保持 `pending`。
- 失败作业下一轮扫描会继续尝试。

手动验收：

1. 启动本地 OneBot 网关并登录 QQ。
2. 设置 `QQ_SENDER=onebot` 和 `ONEBOT_BASE_URL`。
3. 启动本项目。
4. 添加孩子并填写 QQ 号。
5. 创建一分钟后的作业提醒。
6. 到点后确认目标 QQ 收到消息。
7. 确认管理页面日志显示 `onebot` 和外部消息 ID。

## 后续扩展

- 支持 QQ 群消息：给孩子配置发送目标类型和群号。
- 支持重试上限：连续失败多次后标记为需要人工处理。
- 支持发送前健康检查：展示网关是否在线、机器人 QQ 号。
- 支持消息模板：允许家长自定义提醒话术。
