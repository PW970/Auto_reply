# WeChat Auto Agent

一个本地运行的微信自动回复项目,目标是做成**个性化微信分身**:基于 DeepSeek 理解对方的消息,再用学习了你说话风格的模型生成回复,自动发回微信。

> ⚠️ 当前仓库处于早期阶段,核心闭环已经跑通,但"风格学习"和"风险拦截"等关键能力还在路线图上,详见下文。

## 设计目标

不是"调用大模型生成通用回复"的助手,而是希望最终具备这些能力:

1. **会读消息** — 自动读取微信好友新消息
2. **先理解再答** — 用 DeepSeek 分析意图、情绪、风险等级
3. **像你本人说话** — 不是 AI 腔,而是你的语气、措辞、句长、口头禅
4. **越用越像** — 从历史聊天和你的修改行为中持续学习
5. **可控自动化** — 不是无脑全自动,高风险消息可拦截/转人工

## 当前实现

主流程:

```text
wechat-cli new-messages (1s 轮询)
        │
        ▼
   命中白名单联系人?
        │ 是
        ▼
wechat-cli search 拉当天上下文
        │
        ▼
┌──────────────────────────────┐
│ DeepSeek 预分析 (analyzer.py) │
│  → intent / emotion / risk   │
│    summary / reply_hint      │
└──────────────────────────────┘
        │
        ▼
┌──────────────────────────────┐
│ Qwen ReAct Agent (agent.py)  │
│  输入 = 上下文 + 分析简报    │
│  输出 = 调用 send_xxx 工具   │
└──────────────────────────────┘
        │
        ▼
   桌面微信(Win) / 手机(ADB)
```

### 已实现

- [x] `wechat-cli new-messages` 轮询新消息
- [x] 联系人白名单触发
- [x] `wechat-cli search` 拉取当天上下文
- [x] **DeepSeek 预分析层**:每条消息先做 intent / emotion / risk / summary / reply_hint 五项分析,结果注入 Qwen prompt
- [x] DeepSeek 失败/未配置时优雅降级,主流程不中断
- [x] Qwen LangGraph ReAct Agent 调用工具发回复
- [x] **Windows** 桌面微信发送(uiautomation)
- [x] **macOS** 桌面微信发送(AppleScript + System Events,需授权辅助功能)
- [x] 手机端 ADB + Midscene 发送
- [x] 动态发现本机 CLI 工具(claude / hermes / opencode 等)作为额外 Agent 工具
- [x] 简单 Web 管理界面(状态/白名单/发送方式/日志/测试对话)

### 还没实现(路线图)

- [ ] **风险分级实际拦截** — 当前 risk=high 只是日志打出,还没接审批流
- [ ] **草稿模式 + 人工确认 UI**
- [ ] **历史聊天导入与本地存储**(暂缓)
- [ ] **风格学习** — 目前只有静态 `personality` 字符串
- [ ] **per-contact 风格画像** — 跟老板/哥们/家人不同语气
- [ ] **手机端 DEVICE_ID 配置化**(目前硬编码)
- [ ] **回复修改 feedback 回流** — 用户改写草稿的差异作为后续学习样本
- [ ] **消息去重幂等**
- [ ] DeepSeek 同时承担"生成"职责(目前仅分析,生成仍走 Qwen)

## 目录结构

```text
.
├── app.py                  # FastAPI 服务 + 后台轮询
├── agent.py                # Qwen LangGraph ReAct Agent
├── analyzer.py             # DeepSeek 预分析层 ★
├── config.py               # .env 加载、wechat-cli 路径、配置
├── schemas.py              # 数据结构(预留)
├── requirements.txt
├── templates/index.html    # Web 管理界面
└── tools/
    ├── wechat_read.py      # search / new-messages / contacts
    ├── wechat_send.py      # 桌面微信 send tool
    ├── wx_send.py          # uiautomation 实现(Windows)
    ├── phone_control.py    # 手机 send tool
    └── midscene_send.js    # Midscene + ADB 控制手机微信
```

## 运行环境

### 1. Python 依赖

```bash
pip install -r requirements.txt
```

> 注意:`requirements.txt` 当前未列全。运行时还需要:
> - `langgraph`(agent.py 用)
> - `uiautomation`(仅 Windows 桌面发送时需要)
> - DeepSeek 不需要额外 SDK,直接用 httpx 调

### 2. 必备外部依赖

| 依赖 | 用途 | 是否可选 |
|---|---|---|
| `wechat-cli` | 读取微信本地数据 | 必需 |
| 微信桌面客户端(已登录) | 桌面发送 | 桌面模式必需 |
| Node.js + ADB + 安卓设备 | 手机发送 | 手机模式必需 |
| DeepSeek API key | 消息预分析 | 推荐(否则降级) |
| Qwen 兼容端点 | 主 Agent | 必需 |

## 配置

### 环境变量

```bash
cp .env.example .env
```

`.env.example` 主要字段:

```env
# Qwen — 主 Agent(回复生成)
QWEN_API_BASE=http://localhost:8000/v1
QWEN_API_KEY=your_api_key_here
QWEN_MODEL=qwen3.6-27b

# DeepSeek — 消息预分析层
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_ENABLED=true

# Midscene — 手机端视觉模型
MIDSCENE_MODEL_BASE_URL=http://localhost:8000/v1
MIDSCENE_MODEL_API_KEY=your_api_key_here
MIDSCENE_MODEL_NAME=qwen3.6-27b
MIDSCENE_MODEL_FAMILY=qwen3.6
MIDSCENE_MODEL_REASONING_ENABLED=false

WECHAT_CLI_PATH=        # 留空则自动检测
PORT=5679
SELF_NAMES=我,你的微信名,你的姓名
```

DeepSeek 没填 key 时 `DEEPSEEK_ENABLED` 自动降为 false,系统用 fallback 简报继续运行。

### 联系人配置

启动后会读取/写入项目根目录的 `wechat_agent.json`:

```json
{
  "enabled_contacts": ["联系人A", "联系人B"],
  "send_method": "desktop",
  "personality": "直爽、干脆,像哥们聊天",
  "available_cli_tools": {
    "claude": "claude"
  }
}
```

| 字段 | 含义 |
|---|---|
| `enabled_contacts` | 触发自动回复的联系人白名单 |
| `send_method` | `desktop` 或 `phone` |
| `personality` | 当前仅是静态字符串,会注入 prompt |
| `available_cli_tools` | 可选,注册额外 CLI 工具(只有命令在 PATH 中才会真正注册) |

## 启动

```bash
python app.py
```

打开 `http://localhost:5679`。

Web UI 当前能力:

- 启停后台轮询
- 编辑白名单联系人
- 切换发送方式
- 查看最近 50 行日志
- 测试对话(直接调 Agent,不发微信)

启动后日志中会看到 DeepSeek 分析结果:

```
[DeepSeek] 张三 → intent=咨询 emotion=中性 risk=low | 问周末有没有空
```

## 工作原理

### 消息流(`app.py:poll_loop`)

1. 每秒调一次 `wechat-cli new-messages`
2. 过滤命中 `enabled_contacts` 的消息
3. 跳过 `SELF_NAMES` 中自己发的消息
4. 调 `wechat-cli search` 拉当天最近 15 条上下文
5. **调 `analyzer.analyze_message()` 走 DeepSeek 拿结构化分析**
6. 把上下文 + 分析简报 + personality 拼成 prompt
7. 调 Qwen Agent → Agent 决定是否调用 `send_wechat_message` / `send_via_phone`
8. 工具完成 UI 自动化操作

### DeepSeek 简报结构

```python
{
  "intent": "闲聊|咨询|请求|约定|工作安排|情感倾诉|敏感话题|其他",
  "emotion": "中性|开心|不满|焦虑|急切|难过",
  "risk": "low|medium|high",
  "summary": "一句话概括对方说了什么",
  "reply_hint": "给生成层的核心要点提示"
}
```

`risk` 字段是为后续 Rule Engine 准备的入口,目前只在日志打印,**还没真的拦截 high**。

## 已知限制

- **风险分级未真正拦截** — high 风险消息也会自动发,Rule Engine 还没做
- **风格学习未实现** — 只有静态 personality,不会从历史聊天学
- **macOS 桌面发送需要辅助功能授权** — 首次运行会被系统拦,需在 系统设置 → 隐私与安全性 → 辅助功能 中加入运行 Python 的终端
- **手机端 DEVICE_ID 硬编码** — 见 `tools/midscene_send.js:13`
- **`requirements.txt` 缺关键依赖** — `langgraph`、`uiautomation` 未列出
- **无消息去重** — 依赖 `wechat-cli new-messages` 自身的增量语义
- **`/api/chat` 无鉴权** — 默认监听 `0.0.0.0:5679`,生产场景应改为 `127.0.0.1` + token

## 适合的使用方式

**①作为本地消息读取工具:** 只用 `tools/wechat_read.py` 对应的命令,把微信聊天作为本地 AI 的输入源,不跑整个服务。

```bash
wechat-cli search "" --chat "联系人" --start-time "2026-05-01" --limit 30
wechat-cli new-messages
wechat-cli contacts --query "姓名"
```

**②作为自动回复 PoC:** 在白名单联系人 + 低风险场景下做端到端验证。不建议直接对全部联系人启用全自动。

**③作为后续重构的底座:** 沿着上面"还没实现"清单继续扩展。

## 免责声明

本项目依赖本地微信数据读取和自动化发送能力,请自行确认账号风险、稳定性和合规性。**强烈建议**先在白名单联系人 + 低风险场景下验证,再考虑扩大启用范围。
