<h1 align="center">微信自动回复</h1>

<p align="center">
  <b>从你的改写中学习如何像你本人说话的微信自动回复分身</b><br/>
  <sub>DeepSeek 分析意图与风险 · 结构化风格画像 · 高风险消息一键审批 · Win/Mac/手机三端可发</sub>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-blue"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-green"></a>
  <a href="https://github.com/PW970/Auto_reply/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/PW970/Auto_reply?style=social"></a>
</p>

<p align="center">
  <i>📹 演示动图待录制 — <code>docs/demo.gif</code></i>
</p>

---

## 这个项目和别的"AI 微信回复"不一样在哪

大多数微信自动回复项目都是 *"接个 LLM 把回复套个壳发出去"*。这个项目不是。

- **先理解再答** — 每条新消息先经过 DeepSeek 提取意图、情绪、**风险等级**,再决定怎么回
- **不只是 prompt 套人设** — 结构化风格画像(语气/句长/标点/emoji/口头禅/禁用词),**支持按联系人覆写**,跟老板和哥们语气自动切换
- **越用越像你** — 你在 Web UI 上每改一次草稿,系统就把"AI 草稿 vs 你的版本"存下来,下次同联系人来消息直接当 few-shot 用
- **高风险不乱发** — DeepSeek 标 `risk=high` 的消息(涉及金钱/约定/敏感话题)自动转草稿队列,人工审批后才发
- **三端通吃** — Windows uiautomation / macOS AppleScript / 安卓 ADB+Midscene,同一个 Agent 接口

## 5 分钟跑起来

> 前置:已安装 [wechat-cli](https://github.com/dxz1/wechat-cli)、Python 3.10+,以及一个 [DeepSeek API key](https://platform.deepseek.com/)。

```bash
git clone https://github.com/PW970/Auto_reply.git
cd Auto_reply
pip install -r requirements.txt
cp .env.example .env             # 然后填 DEEPSEEK_API_KEY 和 QWEN_API_*
python app.py                    # 打开 http://localhost:5679
```

在 Web UI 上加几个**测试联系人**到白名单,跟自己另一个微信号互发消息试一下。

## 它能做什么

```text
微信新消息
    │
    ▼
┌─ DeepSeek 预分析 ─────────────────┐
│ intent  / emotion / risk          │
│ summary / reply_hint              │
└───────────────────────────────────┘
    │
    ├─ risk = low/medium ─→ 直接生成 + 发送
    │
    └─ risk = high ────────→ 落草稿,Web UI 审批
                                │
                            通过/改写/拒绝
                                │
                            改写差异 → 下次 few-shot
```

| 模块 | 文件 | 做什么 |
|---|---|---|
| 入口 | `app.py` | FastAPI + 1s 轮询 + 风险路由 |
| 预分析 | `analyzer.py` | DeepSeek → 结构化简报 |
| Agent | `agent.py` | LangGraph ReAct,调发送工具 |
| 风格 | `style.py` | 三层合并 + few-shot 注入 |
| 草稿 | `drafts.py` | 高风险队列 + feedback 库 |
| 桌面发送 | `tools/wx_send_{win,mac}.py` | uiautomation / AppleScript |
| 手机发送 | `tools/midscene_send.js` | ADB + Midscene 视觉控制 |

## 配置说明

### `.env` — 模型和外部依赖

```env
# DeepSeek — 消息预分析(没填则系统降级,主流程不中断)
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat

# Qwen / OpenAI 兼容 — 主 Agent(回复生成)
QWEN_API_BASE=http://localhost:8000/v1
QWEN_API_KEY=
QWEN_MODEL=qwen3.6-27b

# 可选
ADB_DEVICE_ID=                   # 多设备时指定;单设备自动选
WECHAT_CLI_PATH=                 # 留空自动检测
PORT=5679
SELF_NAMES=我,你的昵称           # 用于跳过自己发的消息
```

> 主 Agent 走 **OpenAI 兼容协议**,所以可以替换为本地 vLLM、Ollama、SiliconFlow、OpenRouter 等任意兼容服务。

### `wechat_agent.json` — 白名单与风格画像

```json
{
  "enabled_contacts": ["张三", "老板"],
  "send_method": "desktop",

  "style_profile": {
    "tone": "直爽、干脆,像哥们聊天",
    "sentence_length": "short",
    "punctuation": "casual",
    "emoji": "rarely",
    "catchphrases": ["行", "妥了", "整"],
    "avoid": ["亲", "宝子", "您"],
    "examples": ["行,我看下", "明天上午整一下,问题不大"]
  },

  "contact_styles": {
    "老板": {
      "tone": "正式、稳重",
      "punctuation": "standard",
      "emoji": "never",
      "catchphrases": ["收到", "好的"]
    }
  }
}
```

完整字段:

| 字段 | 取值 |
|---|---|
| `tone` | 自由文本,整体语气 |
| `sentence_length` | `short` / `medium` / `long` / `mixed` |
| `punctuation` | `casual` / `standard` / `strict` |
| `emoji` | `never` / `rarely` / `often` |
| `catchphrases` | 字符串数组,你的口头禅 |
| `avoid` | 字符串数组,禁用词(比如 AI 腔的"宝子""亲") |
| `examples` | 字符串数组,2-5 条最有代表性的真实回复 |

`contact_styles[X]` 中没填的字段会自动从 `style_profile` 兜底,只覆写需要差异化的部分。

老的 `personality: "..."` 字符串仍兼容,会作为 `tone` 使用。

### 自学习(feedback 回流)

每次你在 Web UI **修改一条草稿后发出**,系统就把 `(对方原话, AI 草稿, 你的版本)` 存到 `drafts.db`。下次同联系人来消息,Agent prompt 里会自动注入最近 3 条改写样本作 few-shot — 你改一次,下次就开始往那个语气靠。

```bash
curl 'http://localhost:5679/api/feedback?contact=老板'
curl 'http://localhost:5679/api/style?contact=老板'    # 查看合并后画像
```

## 已实现 / 路线图

✅ DeepSeek 预分析(意图/情绪/风险)· 风险分级审批 · 结构化风格画像 + per-contact 覆写 · feedback 自学习 · Win/Mac/手机三端发送 · Web 管理 UI

⏳ 历史聊天导入(暂缓) · 离线风格统计(从 feedback 自动建议口头禅) · 消息去重幂等 · DeepSeek 同时承担生成职责

## 安全与合规

⚠️ **请认真读这一段。** 本项目依赖微信本地数据读取和 UI 自动化发送,有以下风险:

- **账号风险** — 微信对自动化操作的检测策略不公开,理论上存在限制风险
- **隐私边界** — 项目运行时会把白名单联系人的近期聊天上下文发给 DeepSeek/Qwen 模型服务
- **本地端口暴露** — `app.py` 默认监听 `0.0.0.0:5679` 且 `/api/chat` 无鉴权,**生产环境务必改为 `127.0.0.1` 或加 token**
- **macOS 需要辅助功能授权** — 首次运行系统会拦截,需在 系统设置 → 隐私与安全性 → 辅助功能 加入运行 Python 的终端

**强烈建议**:先用一两个测试联系人 + 低风险场景验证,再考虑扩大启用范围。本项目按 MIT 协议提供,作者不对账号封停或隐私泄露承担责任。

## 贡献与讨论

- 发现 Bug 或想要新功能 → [Issues](https://github.com/PW970/Auto_reply/issues)
- 提 PR 前最好先开 Issue 讨论方案,避免做完发现路线不一致

如果这个项目对你有帮助,欢迎点 ⭐ — 这对维护者继续投入有非常大的激励作用。

## License

[MIT](LICENSE)
