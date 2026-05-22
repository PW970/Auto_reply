"""macOS 桌面微信发送 — AppleScript + System Events + 剪贴板"""
import subprocess
import sys
import time

WECHAT_BUNDLE = "com.tencent.xinWeChat"


def _osascript(script: str) -> tuple[int, str, str]:
    p = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=15,
    )
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def _set_clipboard(text: str) -> None:
    p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    p.communicate(text.encode("utf-8"))


def _activate_wechat() -> bool:
    rc, _, err = _osascript(f'tell application id "{WECHAT_BUNDLE}" to activate')
    if rc != 0:
        print(f"ERROR: 无法激活微信: {err}")
        return False
    return True


def _keystroke(script_body: str) -> bool:
    """运行一段 System Events 的脚本片段。失败时打印 a11y 授权提示"""
    rc, _, err = _osascript(
        f'tell application "System Events" to tell process "WeChat"\n{script_body}\nend tell'
    )
    if rc != 0:
        if "1002" in err or "not allowed" in err.lower() or "assistive" in err.lower():
            print(
                "ERROR: 缺少辅助功能权限。请到 系统设置 → 隐私与安全性 → 辅助功能,"
                "把运行此脚本的终端/Python 加入并勾选。"
            )
        else:
            print(f"ERROR: keystroke 失败: {err}")
        return False
    return True


def send_wechat_msg_mac(contact: str, message: str) -> bool:
    print(f"[mac] 启动微信发送 → {contact}")

    if not _activate_wechat():
        return False
    print("[1] 微信已激活")
    time.sleep(0.6)

    # 打开搜索 (Cmd+F)
    print("[2] Cmd+F 搜索联系人")
    if not _keystroke('keystroke "f" using command down'):
        return False
    time.sleep(0.4)

    # 清空 + 粘贴联系人
    _set_clipboard(contact)
    time.sleep(0.15)
    if not _keystroke('keystroke "a" using command down'):
        return False
    time.sleep(0.15)
    if not _keystroke('keystroke "v" using command down'):
        return False
    time.sleep(0.8)

    # 回车进入会话
    if not _keystroke('key code 36'):  # Return
        return False
    time.sleep(1.0)
    print("[3] 已进入会话")

    # 粘贴消息内容
    print(f"[4] 粘贴消息: {message[:40]}{'...' if len(message) > 40 else ''}")
    _set_clipboard(message)
    time.sleep(0.15)
    if not _keystroke('keystroke "v" using command down'):
        return False
    time.sleep(0.3)

    # 发送 (Return)
    if not _keystroke('key code 36'):
        return False
    time.sleep(0.4)
    print("[5] 已发送")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('用法: python wx_send_mac.py "联系人" "消息内容"')
        sys.exit(1)
    ok = send_wechat_msg_mac(sys.argv[1], sys.argv[2])
    sys.exit(0 if ok else 1)
