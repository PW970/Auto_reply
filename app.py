"""FastAPI 主服务 — Web UI + Agent API 一体化"""
import asyncio, json, logging, os
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from config import load_contact_config as load_config, save_contact_config as save_config, LOG_PATH, WECHAT_CLI, PORT, SELF_NAMES, DEEPSEEK_ENABLED
from agent import create_agent
from analyzer import analyze_message, format_brief
import drafts
from tools.wechat_send import send_wechat_message
from tools.phone_control import send_via_phone

HIGH_RISK_NEEDS_APPROVAL = True  # risk=high 走草稿审批,low/medium 自动发

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

agent_executor = None
polling_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent_executor, polling_task
    agent_executor = create_agent()
    polling_task = asyncio.create_task(poll_loop())
    add_log("[DAEMON] 自启动")
    yield
    if polling_task and not polling_task.done():
        polling_task.cancel()

app = FastAPI(lifespan=lifespan)

# ── 日志 ──

def add_log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ── Web UI ──

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    cfg = load_config()
    logs = []
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            logs = f.readlines()[-50:]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "contacts": ", ".join(cfg.get("enabled_contacts", [])),
        "send_method": cfg.get("send_method", "desktop"),
        "running": polling_task is not None and not polling_task.done(),
        "logs": "".join(logs[-50:]),
    })

# ── API ──

@app.post("/api/daemon/toggle")
async def toggle_daemon():
    global polling_task
    if polling_task and not polling_task.done():
        polling_task.cancel()
        add_log("[DAEMON] 已停止")
        return {"status": "stopped"}
    polling_task = asyncio.create_task(poll_loop())
    add_log("[DAEMON] 已启动")
    return {"status": "started"}

@app.post("/api/contacts")
async def update_contacts(request: Request):
    data = await request.json()
    cfg = load_config()
    cfg["enabled_contacts"] = [c.strip() for c in data.get("contacts", "").split(",") if c.strip()]
    save_config(cfg)
    add_log(f"[CONFIG] 联系人更新: {cfg['enabled_contacts']}")
    return {"msg": "已保存"}

@app.post("/api/send-method")
async def update_method(request: Request):
    data = await request.json()
    cfg = load_config()
    cfg["send_method"] = data.get("method", "desktop")
    save_config(cfg)
    add_log(f"[CONFIG] 发送方式: {cfg['send_method']}")
    return {"msg": "已保存"}

@app.post("/api/chat")
async def chat(request: Request):
    data = await request.json()
    msg = data.get("message", "")
    add_log(f"[CHAT] 用户: {msg[:50]}")
    result = await agent_executor.ainvoke({"messages": [("human", msg)]})
    messages = result.get("messages", [])
    reply = messages[-1].content if messages else ""
    add_log(f"[CHAT] 回复: {reply[:100]}")
    return {"reply": reply}

@app.get("/api/logs")
async def get_logs():
    logs = []
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            logs = f.readlines()[-50:]
    return {"logs": "".join(logs)}

@app.get("/api/status")
async def get_status():
    cfg = load_config()
    import shutil
    cli_available = {}
    for name, cmd in cfg.get("available_cli_tools", {}).items():
        cli_available[name] = shutil.which(cmd.split()[0]) is not None
    return {
        "running": polling_task is not None and not polling_task.done(),
        "contacts": cfg.get("enabled_contacts", []),
        "send_method": cfg.get("send_method", "desktop"),
        "cli_tools": cli_available,
        "deepseek_enabled": DEEPSEEK_ENABLED,
        "drafts": drafts.stats(),
    }


# ── 草稿审批 API ──

@app.get("/api/drafts")
async def get_drafts():
    return {"drafts": drafts.list_pending()}


@app.post("/api/drafts/{draft_id}/approve")
async def approve_draft(draft_id: int, request: Request):
    body = await request.json() if await request.body() else {}
    d = drafts.get_draft(draft_id)
    if not d or d["status"] != "pending":
        return {"ok": False, "error": "草稿不存在或已处理"}

    final = (body.get("reply") or d["draft_reply"]).strip()
    if not final:
        return {"ok": False, "error": "回复内容为空"}

    cfg = load_config()
    method = cfg.get("send_method", "desktop")
    add_log(f"[审批] 通过草稿 #{draft_id} → {d['chat']} ({method})")

    drafts.decide(draft_id, "approved", final_reply=final)

    try:
        if method == "phone":
            send_result = send_via_phone.invoke({"contact": d["chat"], "message": final})
        else:
            send_result = send_wechat_message.invoke({"contact": d["chat"], "message": final})
        drafts.decide(draft_id, "sent", final_reply=final)
        add_log(f"[审批]   已发送: {str(send_result)[:80]}")
        return {"ok": True, "sent": str(send_result)}
    except Exception as e:
        add_log(f"[审批]   发送失败: {e}")
        return {"ok": False, "error": f"发送失败: {e}"}


@app.post("/api/drafts/{draft_id}/reject")
async def reject_draft(draft_id: int):
    if drafts.decide(draft_id, "rejected"):
        add_log(f"[审批] 拒绝草稿 #{draft_id}")
        return {"ok": True}
    return {"ok": False, "error": "草稿不存在或已处理"}

# ── 后台轮询 ──

async def _fetch_new_messages():
    import subprocess
    r = await asyncio.get_event_loop().run_in_executor(
        None, lambda: subprocess.run(
            [WECHAT_CLI, "new-messages"], capture_output=True, text=True, timeout=30)
    )
    try:
        raw = r.stdout.strip()
        return json.loads(raw[raw.index("{"):]) if "{" in raw else {}
    except (json.JSONDecodeError, ValueError):
        return None


async def _fetch_context(chat: str, today_str: str, fallback: str) -> str:
    import subprocess
    r2 = await asyncio.get_event_loop().run_in_executor(
        None, lambda c=chat: subprocess.run(
            [WECHAT_CLI, "search", "", "--chat", c, "--start-time", today_str, "--limit", "15"],
            capture_output=True, text=True, timeout=30)
    )
    try:
        raw2 = r2.stdout.strip()
        ctx = json.loads(raw2[raw2.index("{"):])
        return "\n".join(ctx.get("results", [])[-10:])
    except Exception:
        return fallback


async def process_one_message(msg: dict, cfg: dict, tag: str = "轮询"):
    """处理一条新消息:分析 → 按 risk 分流 → 自动发送 / 落库审批"""
    chat = msg.get("chat", "")
    sender = msg.get("sender", "")
    content = msg.get("last_message", "")
    add_log(f"[{tag}]   [{chat}] {sender}: {content[:60]}")
    if sender in SELF_NAMES:
        add_log(f"[{tag}]   {chat} 自己发的,跳过")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    context = await _fetch_context(chat, today_str, f"[{chat}] {sender}: {content}")
    analysis = await analyze_message(chat, sender, content, context=context)
    risk = analysis.get("risk", "medium")
    add_log(f"[{tag}]   [DeepSeek] {chat} risk={risk} {analysis.get('summary','')}")

    needs_approval = HIGH_RISK_NEEDS_APPROVAL and risk == "high"

    if needs_approval:
        # 高风险:让 Agent 只生成回复文本,不调发送工具
        prompt = (
            f"以下是 [{chat}] 的聊天记录:\n{context}\n\n"
            f"{format_brief(analysis)}\n\n"
            f"⚠️ 这是高风险消息,**不要调用任何发送工具**。\n"
            f"请直接输出你建议的回复内容(纯文本,不要解释,不要加引号,不要 tool call)。\n"
            f"个性: {cfg.get('personality','')}"
        )
    else:
        prompt = (
            f"有新消息来自 [{chat}],以下是聊天记录:\n{context}\n\n"
            f"{format_brief(analysis)}\n\n"
            f"请基于以上预分析和聊天记录,调用 send_wechat_message(contact=\"{chat}\", message=...) 回复。"
            f"个性: {cfg.get('personality','')}"
        )

    result = await agent_executor.ainvoke({"messages": [("human", prompt)]})
    out_msgs = result.get("messages", [])
    reply_text = out_msgs[-1].content if out_msgs else ""

    if needs_approval:
        draft_id = drafts.create_draft(
            chat=chat, sender=sender, original_msg=content,
            context=context, analysis_json=json.dumps(analysis, ensure_ascii=False),
            draft_reply=reply_text, risk=risk,
        )
        add_log(f"[{tag}]   ⚠️ 高风险消息已落草稿 #{draft_id},等待 Web UI 审批")
    else:
        add_log(f"[{tag}]   [回复] {chat} agent 输出: {reply_text[:200]}")


async def poll_loop():
    # 启动检测
    add_log(f"[启动] 检查新消息...")
    cfg = load_config()
    contacts = cfg.get("enabled_contacts", [])
    data = await _fetch_new_messages() or {}
    relevant = [m for m in data.get("messages", []) if m.get("chat") in contacts]
    if not relevant:
        add_log(f"[启动] 没有未处理的新消息")
    else:
        add_log(f"[启动] 发现 {len(relevant)} 条新消息")
        for msg in relevant:
            try:
                await process_one_message(msg, cfg, tag="启动")
            except Exception as e:
                add_log(f"[启动]   处理失败: {e}")
    add_log("[启动] 启动检测完成,进入实时监听")

    while True:
        try:
            cfg = load_config()
            contacts = cfg.get("enabled_contacts", [])
            if not contacts:
                await asyncio.sleep(1); continue

            data = await _fetch_new_messages()
            if data is None:
                await asyncio.sleep(1); continue

            new_msgs = data.get("messages", [])

            poll_loop._count = getattr(poll_loop, "_count", 0) + 1
            if poll_loop._count % 30 == 0:
                add_log(f"[监听] 最后检测: {datetime.now().strftime('%H:%M:%S')},新消息数: {len(new_msgs)}")

            if new_msgs:
                relevant = [m for m in new_msgs if m.get("chat") in contacts]
                add_log(f"[轮询] new-messages 返回 {len(new_msgs)} 条,匹配联系人 {len(relevant)} 条")
                for m in new_msgs:
                    add_log(f"[轮询]   原始: [{m.get('chat','')}] {m.get('last_message','')[:50]}")
                for msg in relevant:
                    try:
                        await process_one_message(msg, cfg, tag="轮询")
                    except Exception as e:
                        add_log(f"[轮询]   处理失败: {e}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            add_log(f"[ERROR] {e}")
        await asyncio.sleep(1)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
