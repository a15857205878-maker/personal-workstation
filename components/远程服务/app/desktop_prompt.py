"""Native desktop confirmation prompt for opening a Codex conversation.

The caller owns the 15 second deadline.  This module only presents the prompt
and returns a small status code:

0  user explicitly confirmed before the deadline
2  continue in background (button, window close, or Escape)
3  deadline expired
1  unexpected error
"""

from __future__ import annotations

import json
import math
import sys
import time

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover - Tk may be missing on headless builds
    tk = None
    ttk = None


FONT_FAMILY = "Microsoft YaHei UI"


def _enable_dpi_awareness() -> None:
    """Let Windows scale the Tk window with the system DPI setting.

    This is best effort.  A process that already has a different awareness
    context simply keeps it; the dialog still works.
    """

    if sys.platform != "win32":
        return
    try:
        import ctypes
    except Exception:
        return
    try:
        result = ctypes.windll.shcore.SetProcessDpiAwareness(1)
        if result != 0:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def ask_open(title: str, expires_at: float) -> int:
    """Show a modal prompt and return 0, 1, 2, or 3.

    ``expires_at`` is an absolute ``time.time()`` deadline.  A confirmation is
    accepted only when the button is pressed while ``time.time()`` is still
    before that deadline.
    """

    try:
        deadline = float(expires_at)
        if not math.isfinite(deadline):
            return 1
    except (TypeError, ValueError):
        return 1

    if time.time() >= deadline:
        return 3
    if tk is None or ttk is None:
        return 1

    _enable_dpi_awareness()

    win = None
    state = {"done": False, "code": 1, "timer": None}

    def cancel_timer():
        timer = state["timer"]
        state["timer"] = None
        if timer is not None and win is not None:
            try:
                win.after_cancel(timer)
            except Exception:
                pass

    try:
        parent = getattr(tk, "_default_root", None)
        owns_root = parent is None
        win = tk.Tk() if owns_root else tk.Toplevel(parent)
        win.withdraw()
        if not owns_root:
            try:
                win.transient(parent)
            except Exception:
                pass
        win.title("打开会话确认")
        win.resizable(False, False)
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass
        try:
            win.configure(background="#f4f6f2")
        except Exception:
            pass

        try:
            scale = max(0.85, min(2.2, win.winfo_fpixels("1i") / 96.0))
        except Exception:
            scale = 1.0
        pad = max(10, int(16 * scale))
        wrap = max(320, int(430 * scale))

        title_text = " ".join(str(title if title is not None else "会话").split()) or "会话"
        if len(title_text) > 180:
            title_text = title_text[:180] + "…"

        outer = ttk.Frame(win, padding=(pad, pad, pad, pad))
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text=title_text,
            font=(FONT_FAMILY, 12, "bold"),
            wraplength=wrap,
            justify="left",
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text=(
                "远程任务会优先在后台继续。\n"
                "若现在打开同一会话，手机上的后续指令可能需要等待占用释放。\n"
                "取消或超时只是不再打开，不会关闭已打开的 Codex 会话。"
            ),
            font=(FONT_FAMILY, 10),
            wraplength=wrap,
            justify="left",
        ).pack(anchor="w", pady=(pad // 2, pad // 2))

        countdown = tk.StringVar(master=win, value="")
        remaining = deadline - time.time()
        countdown.set(
            "剩余 %d 秒；到期将默认继续后台。" % int(math.ceil(max(0.0, remaining)))
        )
        ttk.Label(
            outer,
            textvariable=countdown,
            font=(FONT_FAMILY, 9),
            foreground="#5f6f63",
        ).pack(anchor="w", pady=(0, pad // 2))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(pad // 2, 0))

        def finish(code: int) -> None:
            if state["done"]:
                return
            state["done"] = True
            state["code"] = int(code)
            cancel_timer()
            try:
                win.grab_release()
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass

        def on_confirm() -> None:
            if time.time() >= deadline:
                finish(3)
            else:
                finish(0)

        def tick() -> None:
            state["timer"] = None
            if state["done"]:
                return
            left = deadline - time.time()
            if left <= 0:
                finish(3)
                return
            countdown.set(
                "剩余 %d 秒；到期将默认继续后台。" % int(math.ceil(left))
            )
            try:
                state["timer"] = win.after(200, tick)
            except Exception:
                pass

        background = ttk.Button(actions, text="继续后台", command=lambda: finish(2))
        confirm = ttk.Button(actions, text="确认打开", command=on_confirm)
        background.pack(side="left")
        confirm.pack(side="right")

        win.protocol("WM_DELETE_WINDOW", lambda: finish(2))
        win.bind("<Escape>", lambda event: finish(2))
        # Enter must never act as an implicit confirmation.
        win.bind("<Return>", lambda event: "break")
        win.bind("<KP_Enter>", lambda event: "break")
        for button in (background, confirm):
            button.bind("<Return>", lambda event: "break")
            button.bind("<KP_Enter>", lambda event: "break")

        win.update_idletasks()
        width = max(int(470 * scale), win.winfo_reqwidth())
        height = win.winfo_reqheight()
        x = max(0, (win.winfo_screenwidth() - width) // 2)
        y = max(0, (win.winfo_screenheight() - height) // 3)
        win.geometry("%dx%d+%d+%d" % (width, height, x, y))

        win.deiconify()
        win.lift()
        win.update()
        if not state["done"]:
            try:
                win.focus_force()
            except Exception:
                pass
            background.focus_set()
            try:
                win.grab_set()
            except Exception:
                pass
            state["timer"] = win.after(200, tick)
            try:
                win.wait_window(win)
            except Exception:
                pass
        return int(state["code"])
    except Exception:
        cancel_timer()
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
        return int(state["code"]) if state["done"] else 1


def _main() -> int:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        title = payload.get("title", "会话")
        expires_at = payload["expires_at"]
    except Exception:
        return 1
    return ask_open(title, expires_at)


if __name__ == "__main__":
    sys.exit(_main())
