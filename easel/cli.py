"""Easel CLI — 社媒内容工作流整合层。

用法：
    easel chat                              # 新会话（选画像后进入）
    easel doctor                            # 检查环境
    easel up                                # 一次启动 gateway + Web 工作台
    easel web                               # 只启动 Web 工作台
    easel gateway {start|stop|status}       # 管理 gateway
    easel ping                              # 连通性测试
    easel skill <name> -i "..." -p <画像>   # 运行 SKILL
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

from easel.commands.doctor import cmd_doctor
from easel.commands.gateway import cmd_gateway
from easel.commands.ping import cmd_ping
from easel.commands.skill import cmd_skill
from easel.openclaw_cmd import openclaw_base_cmd
from easel.persona import list_personas as _list_personas
from easel.persona import persona_prefix
from easel.persona import chat_turn_message
from easel.persona import load_profile_text
from easel.direct_api import (DirectAPIError, SYSTEM_PROMPT, history_path,
                              read_settings, stream_chat)
from easel.timeouts import TIMEOUT_CHAT
from easel import harnesses
from easel.harnesses.base import HarnessError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = PROJECT_ROOT / "profiles"
PROFILE = "easel"


def _proxy_env() -> dict[str, str]:
    """返回带外网代理的环境变量（保护内网直连）。"""
    env = os.environ.copy()
    env.setdefault("EASEL_ROOT", str(PROJECT_ROOT))
    env.setdefault("http_proxy", os.environ.get("EASEL_PROXY", ""))
    env.setdefault("https_proxy", os.environ.get("EASEL_PROXY", ""))
    env.setdefault("no_proxy", "localhost,127.0.0.1,*.xiaohongshu.com,*.devops.xiaohongshu.com,10.*")
    return env

CYAN = "\033[0;36m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
RED = "\033[0;31m"
DIM = "\033[0;90m"
NC = "\033[0m"


def _build_chat_cmd(session_key: str, message_prefix: str = "") -> list[str]:
    """组装 `easel chat` 的 openclaw tui 命令行。

    必须用 openclaw_base_cmd() 解析启动方式，不能写死字面量 "openclaw"：Windows 上
    PATH 里的 openclaw 是 .cmd shim，CreateProcess 跑不了（见 easel/openclaw_cmd.py）。
    必须用 tui 子命令——`chat`/`terminal` 是 tui 的别名，会强制本地模式
    （openclaw dist/tui-cli-*.js: invokedSubcommand === "chat" → isLocal = true），
    而 --local 要求独占 state 目录，与 Easel 自启的 gateway 冲突，只会打印
    "A Gateway is running for this state directory" 后退出。
    """
    cmd = openclaw_base_cmd() + [
        "--profile", PROFILE,
        "tui",
        "--session", session_key,
        # chat 里可能直接发起制作层/跨层编排，给足制作层预算，避免长任务被 turn 超时掐断（O2）。
        # 超时统一走 easel/timeouts.py（三入口单一真相源），毫秒 = TIMEOUT_CHAT * 1000。
        "--timeout-ms", str(TIMEOUT_CHAT * 1000),
    ]
    # 画像作为初始消息内联注入（无全局 USER.md，避免并发竞态；与 web/skill 同源）。
    # 说明：注入随 session 历史留存，超长会话被压缩后可能丢画像——换取「每个请求自包含」，
    # 与 docs/prompt-stack.md 声明的架构一致。
    if message_prefix:
        cmd += ["--message", message_prefix]
    return cmd


def cmd_chat(_args) -> int:
    """启动 Easel 交互对话（每次新会话）。"""

    print()
    print(f"  {CYAN}Easel{NC} — 社媒内容工作流")
    print()

    # ---- 选择画像 ----
    personas = _list_personas()
    selected_persona = None

    if personas:
        print("  选择用户画像：")
        for i, name in enumerate(personas, 1):
            identity = PROFILES_DIR / name / "identity.md"
            desc = ""
            if identity.is_file():
                for line in identity.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("<!--"):
                        desc = f"  — {line[:50]}"
                        break
            print(f"    {i}) {name}{desc}")
        print(f"    0) 不使用画像（通用模式）")
        print()

        try:
            choice = input("  请选择 [0]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if choice and choice != "0":
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(personas):
                    selected_persona = personas[idx]
            except ValueError:
                if choice in personas:
                    selected_persona = choice

    # ---- 每次新会话 ----
    if selected_persona:
        print(f"\n  {GREEN}✓{NC} 画像: {selected_persona}")
    else:
        print(f"\n  {YELLOW}→{NC} 通用模式")

    session_key = f"easel-{time.strftime('%m%d-%H%M%S')}"

    settings = read_settings()
    runtime = harnesses.settings(PROJECT_ROOT / "outputs", settings)["runtime"]
    if runtime not in ("api", "openclaw"):
        print(f"  Agent 底座：{runtime}（/exit 退出）")
        native_id = ""

        def remember(value):
            nonlocal native_id
            native_id = value

        while True:
            try:
                message = input("你：").strip()
                if message in ("/exit", "/quit"):
                    return 0
                if message:
                    # timeout 与同命令的 openclaw TUI / web 路径对齐（TIMEOUT_CHAT=7200）：
                    # chat 可能中途触发制作层任务，console_turn 默认 1800s 会把它掐断。
                    _, native_id = asyncio.run(harnesses.console_turn(
                        chat_turn_message(message, selected_persona), PROJECT_ROOT,
                        {**settings, **_proxy_env()}, native_id, on_bind=remember,
                        timeout=TIMEOUT_CHAT))
                    print()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            except (HarnessError, asyncio.TimeoutError) as error:
                print(f"\nAgent 执行失败：{error or '请求超时'}")
    if runtime == "api":
        print("  API 直连模式（文字问答；/exit 退出）\n")
        system = SYSTEM_PROMPT
        if selected_persona:
            system += "\n\n当前画像：\n" + load_profile_text(selected_persona)
        async def reply(message):
            async for kind, text in stream_chat(
                    read_settings(), message, system=system,
                    history_file=history_path(PROJECT_ROOT / "outputs" / "_sessions", session_key),
                    timeout=TIMEOUT_CHAT):
                if kind == "token":
                    print(text, end="", flush=True)
        while True:
            try:
                message = input("你：").strip()
                if message in ("/exit", "/quit"):
                    return 0
                if message:
                    asyncio.run(asyncio.wait_for(reply(message), TIMEOUT_CHAT))
                    print()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            except (DirectAPIError, asyncio.TimeoutError) as error:
                print(f"\n❌ {error or 'API 请求超时'}")

    print(f"  {DIM}会话: {session_key}{NC}")
    print(f"  {DIM}切换历史会话: 对话中输入 /session{NC}")
    print(f"  {CYAN}Ctrl+C{NC} 退出")
    print()

    prefix = persona_prefix(selected_persona)
    try:
        # openclaw_base_cmd() 在 openclaw 全装不上时抛 FileNotFoundError；
        # subprocess.run 在可执行文件缺失时同样抛 FileNotFoundError。两者都提示安装。
        cmd = _build_chat_cmd(session_key, prefix)
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=_proxy_env())
    except FileNotFoundError:
        print(f"{RED}未找到 openclaw{NC} — 请先安装：npm i -g openclaw，"
              f"或运行 `python -m easel doctor` 检查环境。", file=sys.stderr)
        return 1

    return result.returncode


def _default_port() -> int:
    """Web 端口默认值：``EASEL_PORT``（.env 或环境变量）> 7860。

    允许把端口钉在 .env 里，这样 ``easel up`` / ``easel web`` 不必每次带 ``--port``。
    WSL 上尤其需要：Windows 保留的 7409-7979 区间会让 ``localhost:7860`` 无法从
    Windows 侧转发（wslrelay 绑不上宿主回环端口，且静默失败），只能换一个端口。
    """
    try:
        # read_settings 已经合并 os.environ（环境变量优先），这里不必再查一遍。
        raw = str(read_settings(PROJECT_ROOT / ".env").get("EASEL_PORT", "") or "").strip()
    except Exception:  # noqa: BLE001  .env 读不了不该阻塞启动，退回默认端口
        raw = ""
    if raw.isdigit() and 0 < int(raw) <= 65_535:
        return int(raw)
    return 7860


def _gateway_healthy(timeout: float = 1.5) -> bool:
    """回环探针：gateway ``/healthz`` 是否 200。

    与 doctor / ping 同一条 doctrine：探针绝不能继承 ``http_proxy``，否则设置过代理的
    环境里，活着的回环网关会被判成离线。
    """
    import urllib.error
    import urllib.request

    from easel.gateway_endpoint import healthz_url

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(healthz_url(), timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _gateway_needed() -> bool:
    """当前执行引擎是否需要 OpenClaw gateway（api / Codex / OpenCode 模式不需要）。"""
    try:
        runtime = harnesses.settings(PROJECT_ROOT / "outputs", read_settings())["runtime"]
    except Exception:  # noqa: BLE001  判定失败按「需要」处理：多起一次 gateway 无害
        return True
    return runtime == "openclaw"


def cmd_up(args) -> int:
    """一次性启动 OpenClaw gateway + Web 工作台，Ctrl+C 一起收摊。

    为什么要有这个命令：``easel web`` 只起 FastAPI，gateway 是另一条长驻进程
    （``web/app.py`` 只探测它，探不到就退回每轮冷启动的 CLI 传输）。少打一条命令
    不是重点，重点是**顺序和收尾**：先 gateway 后 web、退出时只停本次自己起的
    gateway（复用已在跑的那个时不动它），否则很容易留下一个没人管的孤儿进程。
    """
    from easel.gateway_endpoint import describe

    def say(message: str, *, err: bool = False) -> None:
        # 启动期提示必须 flush。stdout 被重定向（日志、CI、`> file`）时 Python 是块缓冲，
        # 不 flush 的话用户在 gateway 起来之前只会看到一片空屏。
        print(message, file=sys.stderr if err else sys.stdout, flush=True)

    started_gateway = False
    if getattr(args, "no_gateway", False):
        say(f"  {DIM}--no-gateway：只启动 Web，不动 gateway{NC}")
    elif not _gateway_needed():
        say(f"  {DIM}当前执行引擎不需要 OpenClaw gateway，直接启动 Web{NC}")
    elif _gateway_healthy():
        say(f"  {GREEN}gateway 已在运行{NC} {DIM}{describe()}{NC}")
    else:
        say(f"  {CYAN}启动 gateway…{NC}")
        started_gateway = cmd_gateway(argparse.Namespace(action="start")) == 0
        # gateway.sh 用 setsid 起进程后立刻返回，健康与否要自己等：40 × 0.25s ≈ 10s。
        # start 本身就失败时不必等：进程根本没起来，等满 10s 只会拖慢报错。
        if started_gateway:
            for _ in range(40):
                if _gateway_healthy(0.5):
                    break
                time.sleep(0.25)
        if _gateway_healthy():
            say(f"  {GREEN}gateway 就绪{NC} {DIM}{describe()}{NC}")
        else:
            started_gateway = False
            say(f"  {YELLOW}gateway 没起来，Web 仍会启动{NC}"
                f"（聊天会退回每轮冷启动的 CLI 传输）\n"
                f"  {DIM}排查：bash scripts/gateway.sh status"
                f"（日志 /tmp/easel-gateway.log）{NC}", err=True)

    port = getattr(args, "port", 7860)
    say(f"  Web 工作台：{CYAN}http://127.0.0.1:{port}{NC} {DIM}Ctrl+C 退出{NC}")
    try:
        return cmd_web(args)
    except KeyboardInterrupt:
        # 子进程已经收到同一个 SIGINT 并退出，这里只负责把退出码收敛成 0。
        return 0
    finally:
        if started_gateway and not getattr(args, "keep_gateway", False):
            say(f"\n  {DIM}停止本次启动的 gateway…{NC}")
            cmd_gateway(argparse.Namespace(action="stop"))


def cmd_web(args) -> int:
    """启动 Web 工作台（FastAPI + React），默认 http://localhost:7860。"""
    from easel.runtime_env import web_environment

    port = getattr(args, "port", 7860)
    env = web_environment(_proxy_env())
    env["EASEL_PORT"] = str(port)
    script = PROJECT_ROOT / "web" / "app.py"
    if not script.is_file():
        print(f"{RED}未找到 web/app.py{NC} — 安装可能不完整，请重跑 `bash setup.sh`。",
              file=sys.stderr)
        return 1
    # 透传子进程返回码：端口占用/依赖缺失导致 app.py 立刻退出时，调用方
    # （自启/CI/脚本）能据此判断启动是否成功，而非恒拿到 0。
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="easel",
        description="Easel — 社媒内容工作流整合层 CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # chat
    p_chat = sub.add_parser("chat", help="交互对话（新会话）")
    p_chat.set_defaults(func=cmd_chat)

    # doctor
    p_doctor = sub.add_parser("doctor", help="检查环境")
    p_doctor.set_defaults(func=cmd_doctor)

    # gateway
    p_gw = sub.add_parser("gateway", help="管理 OpenClaw gateway")
    p_gw.add_argument("action", choices=["start", "stop", "restart", "status", "logs"],
                       default="status", nargs="?")
    p_gw.set_defaults(func=cmd_gateway)

    # ping
    p_ping = sub.add_parser("ping", help="连通性测试")
    p_ping.set_defaults(func=cmd_ping)

    # skill
    p_skill = sub.add_parser("skill", help="运行 SKILL（自动路由）")
    p_skill.add_argument("name", help="SKILL 名称")
    p_skill.add_argument("--input", "-i", required=True, help="输入内容")
    p_skill.add_argument("--profile", "-p", default=None, help="用户画像名称")
    p_skill.set_defaults(func=cmd_skill)

    # web
    # 端口默认值只算一次：它要读 .env，而 --help 的文案里得写出「实际生效的那个值」，
    # 否则 .env 里设了 EASEL_PORT=8188、帮助里还印 7860，用户会以为设置没生效。
    default_port = _default_port()
    p_web = sub.add_parser("web", help="启动 Web UI")
    p_web.add_argument("--port", type=int, default=default_port,
                       help=f"端口（默认 {default_port}；可用 EASEL_PORT 覆盖）")
    p_web.set_defaults(func=cmd_web)

    # up：gateway + web 一条命令
    p_up = sub.add_parser("up", help="一次性启动 gateway 和 Web 工作台")
    p_up.add_argument("--port", type=int, default=default_port,
                      help=f"Web 端口（默认 {default_port}；可用 EASEL_PORT 覆盖）")
    p_up.add_argument("--no-gateway", action="store_true",
                      help="只启动 Web，不碰 gateway")
    p_up.add_argument("--keep-gateway", action="store_true",
                      help="Ctrl+C 退出时保留本次启动的 gateway")
    p_up.set_defaults(func=cmd_up)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except HarnessError as error:
        print(f"Agent 设置错误：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
