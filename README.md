# WeChat Auto Agent

一个本地运行的微信自动回复原型项目。

当前版本基于 `FastAPI + LangChain/LangGraph + Qwen`，通过 `wechat-cli` 读取微信新消息，再调用大模型生成回复，并尝试通过桌面微信或手机自动化发送消息。

它更适合作为一个可运行的 PoC，而不是已经打磨好的生产级方案。

## 项目定位

这个仓库当前解决的是一条最小闭环：

1. 轮询微信新消息
2. 拉取目标联系人的最近聊天上下文
3. 调用大模型生成回复
4. 通过自动化方式把消息发出去

如果你的目标是：

- 使用 DeepSeek 做更稳定的分析和回复
- 从历史聊天中学习用户本人说话风格
- 按联系人沉淀长期记忆
- 区分高风险消息并人工确认

那么这个仓库可以作为基础骨架，但还需要继续扩展。

## 当前已实现

- 自动轮询 `wechat-cli new-messages` 检测新消息
- 按联系人白名单触发自动回复
- 使用 `wechat-cli search` 拉取当天最近聊天记录作为上下文
- 通过 LangGraph ReAct Agent 调用模型和工具
- 支持桌面微信发送
- 支持手机端 Midscene + ADB 发送
- 支持动态发现本机 CLI 工具，例如 `claude`、`hermes`、`opencode`
- 提供简单的 Web 管理界面和日志查看页面

## 当前未实现

下面这些能力在仓库里还没有真正落地：

- DeepSeek 专用接入和提示词链路
- 从历史聊天中自动学习用户语气、口头禅、句式偏好
- 联系人画像和长期记忆
- 消息意图/情绪/风险等级分析中间层
- 自动回复规则引擎
- 高风险消息人工确认
- 稳定的消息去重、幂等、补偿和节流机制

## 技术架构

当前主流程如下：

```text
wechat-cli new-messages
        |
        v
   app.py 轮询后台任务
        |
        v
wechat-cli search 拉取上下文
        |
        v
  agent.py 创建的 ReAct Agent
        |
        +--> tools/wechat_read.py
        +--> tools/wechat_send.py
        +--> tools/phone_control.py
        +--> 动态 CLI 工具
        |
        v
 自动发送回复 / Web 日志输出
```

## 目录结构

```text
.
├── app.py                  # FastAPI 服务入口，含后台轮询逻辑
├── agent.py                # Qwen + LangGraph ReAct Agent
├── config.py               # .env、wechat-cli 路径、联系人配置
├── schemas.py              # 预留的数据结构定义
├── requirements.txt        # Python 依赖
├── templates/
│   └── index.html          # Web 管理界面
└── tools/
    ├── wechat_read.py      # 读取新消息、搜索聊天、搜索联系人
    ├── wechat_send.py      # LangChain 工具封装：发送桌面微信
    ├── wx_send.py          # 桌面微信 UI 自动化发送
    ├── phone_control.py    # LangChain 工具封装：手机发送
    └── midscene_send.js    # Midscene + ADB 控制手机微信
```

## 运行环境

### Python 依赖

```bash
pip install -r requirements.txt
```

### 必备外部依赖

- `wechat-cli`：用于读取微信本地数据库
- 微信桌面客户端：如果使用桌面发送模式，需要保持已登录
- Node.js：如果使用手机发送模式，需要运行 `midscene_send.js`
- ADB：如果使用手机发送模式，需要可连接安卓设备
- 一个兼容 OpenAI API 的模型服务：当前默认按 Qwen 参数名配置

## 配置说明

### 1. 环境变量

复制模板：

```bash
cp .env.example .env
```

`.env.example` 当前包含这些字段：

```env
QWEN_API_BASE=http://localhost:8000/v1
QWEN_API_KEY=your_api_key_here
QWEN_MODEL=qwen3.6-27b

MIDSCENE_MODEL_BASE_URL=http://localhost:8000/v1
MIDSCENE_MODEL_API_KEY=your_api_key_here
MIDSCENE_MODEL_NAME=qwen3.6-27b
MIDSCENE_MODEL_FAMILY=qwen3.6
MIDSCENE_MODEL_REASONING_ENABLED=false

WECHAT_CLI_PATH=
PORT=5679
SELF_NAMES=我,你的微信名,你的姓名
```

说明：

- `QWEN_*`：主 Agent 使用的大模型配置
- `MIDSCENE_*`：手机发送模式使用的模型配置
- `WECHAT_CLI_PATH`：可选，手动指定 `wechat-cli` 路径
- `SELF_NAMES`：用于识别“哪些消息是你自己发出的”

### 2. 联系人与发送方式配置

项目运行后会读取 `wechat_agent.json`。

示例：

```json
{
  "enabled_contacts": ["联系人A", "联系人B"],
  "send_method": "desktop",
  "personality": "直爽、干脆，像哥们聊天",
  "available_cli_tools": {
    "claude": "claude"
  }
}
```

字段说明：

- `enabled_contacts`：允许自动回复的联系人名单
- `send_method`：发送方式，当前值会写入提示词
- `personality`：静态人格描述，当前版本不会自动学习
- `available_cli_tools`：可选，注册额外 CLI 模型工具

## 启动方式

```bash
python app.py
```

启动后访问：

- `http://localhost:5679`

Web 页面目前支持：

- 查看服务运行状态
- 修改联系人白名单
- 修改发送方式
- 查看最近日志
- 测试对话接口

## 核心文件说明

### `app.py`

负责：

- 启动 FastAPI
- 创建 Agent
- 启动后台轮询任务
- 调用 `wechat-cli` 检测新消息
- 拼接上下文后调用 Agent
- 输出日志和 Web API

### `agent.py`

负责：

- 创建 `ChatOpenAI` 模型实例
- 注册微信读取和发送工具
- 动态发现本地 CLI 工具
- 构造 ReAct Agent 的 system prompt

### `tools/wechat_read.py`

封装了三个核心读取能力：

- `search_messages(chat_name, start_date, limit)`
- `get_new_messages()`
- `list_contacts(query)`

这部分也可以单独抽出来，作为本地消息读取工具使用。

## 已知限制

在实际使用前，建议先了解这些限制：

- 当前默认模型是 Qwen，不是 DeepSeek
- “学习用户语气”尚未实现，只有静态 `personality` 文本
- 上下文只取当天最近消息，无法覆盖长期历史
- 多个联系人的消息可能被拼到同一个 prompt 中处理
- 发送方式虽然有 `desktop` 和 `phone` 配置，但当前提示词仍偏向固定调用桌面发送工具
- 桌面发送依赖 UI 自动化，稳定性受微信窗口结构影响较大
- 手机发送依赖 ADB、Midscene 和设备环境，脚本中存在环境相关硬编码
- 错误处理、去重、风控、节流能力都比较基础

## 适合的使用方式

更推荐把这个项目当成下面两种用途之一：

### 1. 自动回复原型

适合验证：

- 本地微信消息读取是否可行
- 大模型自动回复链路是否能跑通
- UI 自动化发送是否满足你的设备环境

### 2. 后续重构底座

适合继续往下扩展：

- 替换为 DeepSeek
- 新增历史聊天导入
- 新增风格学习和长期记忆
- 新增人工确认和风险规则
- 从“全自动回复”改成“半自动助手优先”

## 后续改造建议

如果要对齐“像用户本人说话的微信自动回复助手”这个目标，建议新增这些模块：

- `History Importer`：历史聊天导入和清洗
- `Style Learner`：提取用户说话风格
- `Message Analyzer`：意图、情绪、风险分析
- `Memory Retriever`：长期记忆和相似历史检索
- `Style Rewriter`：把回复改写成更像用户本人
- `Rule Engine`：决定自动发、建议发还是禁止发
- `Approval Center`：高风险消息人工确认
- `Feedback Logger`：记录用户修改，持续优化回复风格

## 作为本地消息读取工具使用

如果你不想跑整个 Web 服务，也可以只使用 `tools/wechat_read.py` 对应的底层命令：

```bash
# 查询联系人聊天记录
wechat-cli search "" --chat "联系人" --start-time "2026-05-01" --limit 30

# 查询新消息
wechat-cli new-messages

# 搜索联系人
wechat-cli contacts --query "姓名"
```

这种模式适合：

- 把微信聊天记录交给本地 AI 做分析
- 从聊天记录中提取需求、问题、截图信息
- 作为其他 Agent/工具的消息输入源

## 免责声明

本项目依赖本地微信数据读取和自动化发送能力，请你自行确认使用场景、账号风险、稳定性和合规性。

如果用于真实自动回复，请优先从半自动、白名单联系人、低风险场景开始，不建议直接对全部联系人启用全自动回复。
