"""Ciclo de reglas del servidor, sin arrancar la aplicación ni abrir ventanas."""

from __future__ import annotations

import asyncio
from threading import Event, get_ident
from unittest.mock import Mock

import pytest

from lumina.app import LuminaApp
from lumina.controllers import Services
from lumina.settings import AppSettings


async def test_rules_timer_does_not_block_event_loop_and_waits_on_shutdown(services: Services) -> None:
    application = LuminaApp(AppSettings(), services=services)
    timer = Mock()
    application._rules_timer = timer
    started, release = Event(), Event()
    loop_thread = get_ident()

    def evaluate() -> None:
        assert get_ident() != loop_thread
        started.set()
        assert release.wait(timeout=5)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(services.rules, 'evaluate', evaluate)
        cycle = asyncio.create_task(application._evaluate_rules())
        try:
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(0.01)
            assert started.is_set()
            stopping = asyncio.create_task(application._stop_rules())
            await asyncio.sleep(0)
            timer.cancel.assert_called_once()
            assert not stopping.done()
        finally:
            release.set()
            await cycle
        await stopping
        started.clear()
        await application._evaluate_rules()
        assert not started.is_set()


async def test_rules_timer_retries_after_unexpected_exception(services: Services) -> None:
    application = LuminaApp(AppSettings(), services=services)
    evaluate = Mock(side_effect=[RuntimeError('fallo inesperado'), None])
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(services.rules, 'evaluate', evaluate)
        await application._evaluate_rules()
        await application._evaluate_rules()
    assert evaluate.call_count == 2
