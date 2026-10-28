"""``easel up``：gateway + Web 一条命令的启动顺序与收尾语义。

用假实现替换 cmd_gateway / cmd_web / _gateway_healthy，只验证编排逻辑：
先 gateway 后 web、复用已在跑的 gateway、只停本次自己起的那个。
"""

from __future__ import annotations

import types

import pytest

from easel import cli


def _args(**overrides):
    base = {"port": 8188, "no_gateway": False, "keep_gateway": False}
    base.update(overrides)
    return types.SimpleNamespace(**base)


def _stub(monkeypatch, *, healthy=False, start_rc=0, stop_rc=0):
    """装一套假实现，返回 (calls, state)；start 成功后把 healthy 置 True。"""
    calls = {"gateway": [], "web": []}
    state = {"healthy": healthy}

    def fake_gateway(args):
        calls["gateway"].append(args.action)
        if args.action == "start":
            if start_rc == 0:
                state["healthy"] = True
            return start_rc
        return stop_rc

    def fake_web(args):
        calls["web"].append(args.port)
        return 0

    monkeypatch.setattr(cli, "cmd_gateway", fake_gateway)
    monkeypatch.setattr(cli, "cmd_web", fake_web)
    monkeypatch.setattr(cli, "_gateway_needed", lambda: True)
    monkeypatch.setattr(cli, "_gateway_healthy", lambda *a, **k: state["healthy"])
    return calls, state


def test_up_starts_gateway_then_web_and_stops_it(monkeypatch):
    calls, _ = _stub(monkeypatch, healthy=False)
    assert cli.cmd_up(_args()) == 0
    assert calls["gateway"] == ["start", "stop"]
    assert calls["web"] == [8188]


def test_up_reuses_running_gateway_and_leaves_it_alone(monkeypatch):
    """gateway 已在跑时：不 start、也不 stop —— 那不是我们起的，不该动它。"""
    calls, _ = _stub(monkeypatch, healthy=True)
    assert cli.cmd_up(_args()) == 0
    assert calls["gateway"] == []
    assert calls["web"] == [8188]


def test_up_no_gateway_flag_skips_gateway_entirely(monkeypatch):
    calls, _ = _stub(monkeypatch, healthy=False)
    assert cli.cmd_up(_args(no_gateway=True)) == 0
    assert calls["gateway"] == []
    assert calls["web"] == [8188]


def test_up_keep_gateway_does_not_stop_it(monkeypatch):
    calls, _ = _stub(monkeypatch, healthy=False)
    assert cli.cmd_up(_args(keep_gateway=True)) == 0
    assert calls["gateway"] == ["start"]
    assert calls["web"] == [8188]


def test_up_still_starts_web_when_gateway_start_fails(monkeypatch):
    """gateway 起不来不该挡住 Web：登录/发布走的是 Web 后端，不是网关。"""
    calls, _ = _stub(monkeypatch, healthy=False, start_rc=1)
    assert cli.cmd_up(_args()) == 0
    assert calls["gateway"] == ["start"]       # 没有 stop：本来就没起来
    assert calls["web"] == [8188]


def test_up_skips_gateway_when_engine_does_not_need_it(monkeypatch):
    calls, _ = _stub(monkeypatch, healthy=False)
    monkeypatch.setattr(cli, "_gateway_needed", lambda: False)
    assert cli.cmd_up(_args()) == 0
    assert calls["gateway"] == []
    assert calls["web"] == [8188]


def test_up_treats_interrupt_as_clean_exit(monkeypatch):
    calls, _ = _stub(monkeypatch, healthy=True)

    def interrupted(args):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "cmd_web", interrupted)
    assert cli.cmd_up(_args()) == 0


# ---- 端口默认值 ------------------------------------------------------------


def test_default_port_uses_env(monkeypatch):
    monkeypatch.setenv("EASEL_PORT", "8188")
    assert cli._default_port() == 8188


@pytest.mark.parametrize("raw", ["", "banana", "0", "70000", "-1"])
def test_default_port_falls_back_to_7860(monkeypatch, raw):
    monkeypatch.setenv("EASEL_PORT", raw)
    assert cli._default_port() == 7860
