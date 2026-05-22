"""手机控制工具 — Midscene ADB"""
import subprocess, os
from langchain_core.tools import tool

from config import MIDSCENE_ENV, ADB_DEVICE_ID

MIDSCENE_SEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "midscene_send.js")

@tool
def send_via_phone(contact: str, message: str) -> str:
    """通过手机发送微信消息（Midscene 视觉识别控制手机）。"""
    env = {**os.environ, **MIDSCENE_ENV}
    if ADB_DEVICE_ID:
        env["ADB_DEVICE_ID"] = ADB_DEVICE_ID
    r = subprocess.run(
        ["node", MIDSCENE_SEND, contact, message],
        capture_output=True, text=True, timeout=120, env=env
    )
    return r.stdout.strip() or "发送失败"
