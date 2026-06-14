# 催孩子写作业

本地单机 Web MVP。家长可以添加孩子并绑定 QQ 号，创建作业并设置提醒时间。到点后，系统默认生成模拟 QQ 提醒日志；配置本地 OneBot v11 网关后，也可以发送真实 QQ 私聊消息。

## 功能

- 添加孩子：姓名、QQ 号。
- 创建作业：孩子、标题、说明、提醒时间。
- 自动提醒：后台每 30 秒扫描到点作业。
- QQ 发送：默认模拟发送并记录日志；配置本地 OneBot v11 网关后可发送真实 QQ 私聊消息。
- 管理页面：查看孩子、作业状态和提醒日志。

## 暂不支持

- 真实 QQ 登录或内置 QQ 协议实现。
- 家长账号、登录鉴权、多用户隔离。
- 公网部署、多设备同步。
- 重复提醒、完成确认、催促升级。
- 跨时区处理；MVP 使用本机本地时间设置提醒。

## 安装

```bash
uv sync
```

## 运行测试

```bash
uv run pytest
```

## 启动应用

```bash
uv run uvicorn app.main:app --reload
```

## 真实 QQ 发送

默认使用模拟发送，不会访问 QQ：

```bash
uv run uvicorn app.main:app --reload
```

要发送真实 QQ 私聊消息，先启动一个兼容 OneBot v11 HTTP API 的本地 QQ 网关，例如 NapCat 或 Lagrange。然后设置：

```bash
QQ_SENDER=onebot \
ONEBOT_BASE_URL=http://127.0.0.1:3000 \
uv run uvicorn app.main:app --reload
```

如果网关配置了 access token：

```bash
QQ_SENDER=onebot \
ONEBOT_BASE_URL=http://127.0.0.1:3000 \
ONEBOT_ACCESS_TOKEN=your-token \
uv run uvicorn app.main:app --reload
```

发送失败会写入提醒日志，作业保持待提醒状态，下一轮扫描会继续重试。

打开：

```text
http://127.0.0.1:8000
```

## 数据位置

默认 SQLite 数据库：

```text
data/assignment_reminder.sqlite3
```

`data/` 是本地运行数据目录，已加入 `.gitignore`。

## 验收流程

1. 打开本地管理页面。
2. 添加一个孩子和 QQ 号。
3. 创建一条一两分钟后提醒的作业。
4. 等待后台扫描。
5. 确认作业状态变为“已提醒”。
6. 默认配置下，确认提醒日志出现模拟 QQ 消息。
# assignment-reminder-codebuddy
