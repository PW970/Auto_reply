"""桌面微信发送入口 — 按平台分发到对应实现

用法: python wx_send.py "联系人" "消息内容"

- Windows: 走 wx_send_win.py (uiautomation)
- macOS:   走 wx_send_mac.py (AppleScript + System Events)
- 其它:    报错退出
"""
import sys


def main() -> int:
    if len(sys.argv) < 3:
        print('用法: python wx_send.py "联系人" "消息内容"')
        return 1
    contact, message = sys.argv[1], sys.argv[2]

    if sys.platform == "win32":
        from wx_send_win import send_wechat_msg
        ok = send_wechat_msg(contact, message)
    elif sys.platform == "darwin":
        from wx_send_mac import send_wechat_msg_mac
        ok = send_wechat_msg_mac(contact, message)
    else:
        print(f"ERROR: 当前平台 {sys.platform} 暂不支持桌面发送,请改用 send_method=phone")
        return 2

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
