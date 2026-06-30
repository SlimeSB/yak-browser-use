"""REST + WebSocket routes for the Yak Browser-Use API."""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from yak_browser_use.api.errors import APIError, ServerError
from yak_browser_use.api.state import engine_state
from yak_browser_use.utils.logging import get_logger
from yak_browser_use.utils._path import project_root

logger = get_logger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────


def _extract_pipeline_name(pipeline_text: str) -> str:
    """Extract pipeline name from pipeline.yaml."""
    import yaml
    try:
        data = yaml.safe_load(pipeline_text)
        if isinstance(data, dict) and "name" in data:
            return str(data["name"]).strip().strip('"').strip("'")
    except Exception:  # expected: invalid yaml
        pass
    return "unnamed"


# ── Router registration ────────────────────────────────────────────


def register_all_routes(app: FastAPI) -> None:
    """Register all REST and WebSocket routes on *app*."""

    # =================================================================
    # PROVIDER CONFIG
    # =================================================================

    @app.get("/api/provider-config")
    async def api_get_provider_config() -> JSONResponse:
        """Get the current LLM provider configuration."""
        from yak_browser_use.utils.browser import _get_config_path
        p = _get_config_path()
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return JSONResponse({"ok": True, "config": data})
            except Exception:
                logger.debug("Failed to parse provider config JSON", exc_info=True)
        return JSONResponse({"ok": True, "config": {}})

    @app.post("/api/provider-config")
    async def api_set_provider_config(request: dict) -> JSONResponse:
        """Save LLM provider configuration."""
        from yak_browser_use.utils.browser import _get_config_path
        p = _get_config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
        return JSONResponse({"ok": True})

    @app.post("/api/provider-test")
    async def api_test_provider(request: dict) -> JSONResponse:
        """Test an LLM provider config by making a simple call."""
        try:
            from yak_browser_use.llm.client import LLMClient
            from yak_browser_use.llm.messages import UserMessage

            model = request.get("model", "gpt-4o")
            api_key = request.get("api_key", "")
            api_base = request.get("api_base", "")

            kwargs: dict = {"model": model}
            if api_key:
                kwargs["api_key"] = api_key
            if api_base:
                kwargs["base_url"] = api_base

            llm = LLMClient(**kwargs)
            await llm.ainvoke([UserMessage(content="Say hello in one word.")])
            return JSONResponse({"ok": True})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)})

    @app.get("/api/provider-presets")
    async def api_get_provider_presets() -> JSONResponse:
        """Fetch LLM provider presets from models.dev API."""
        import aiohttp

        PRESET_IDS = {"opencode-go", "deepseek"}
        CACHE_SECONDS = 300
        _cache = getattr(api_get_provider_presets, "_cache", None)
        _ts = getattr(api_get_provider_presets, "_ts", 0)
        now = time.time()
        if _cache and (now - _ts) < CACHE_SECONDS:
            return JSONResponse({"ok": True, "presets": _cache})

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://models.dev/api.json", timeout=15) as resp:
                    raw = await resp.json()
        except Exception as e:
            logger.warning("Failed to fetch models.dev/api.json: %s", e)
            return JSONResponse({"ok": False, "error": str(e)})

        presets = []
        for pid in PRESET_IDS:
            entry = raw.get(pid)
            if not entry:
                continue
            models = []
            for mid, m in entry.get("models", {}).items():
                models.append({
                    "id": mid,
                    "name": m.get("name", mid),
                    "context": (m.get("limit") or {}).get("context"),
                })
            models.sort(key=lambda x: x["name"])
            presets.append({
                "id": pid,
                "name": entry.get("name", pid),
                "api_base": entry.get("api"),
                "env": entry.get("env", []),
                "models": models,
            })

        api_get_provider_presets._cache = presets
        api_get_provider_presets._ts = now
        return JSONResponse({"ok": True, "presets": presets})

    # =================================================================
    # RUN
    # =================================================================

    @app.post("/api/run")
    async def api_run(request: dict) -> JSONResponse:
        """Execute a pipeline.yaml pipeline (runs as an async background task).

        Request body: ``{"pipeline": "...", "params": {...}}``

        Returns immediately with a ``run_id``.  Poll ``GET /api/status``
        or subscribe to ``/ws/events`` for completion.
        """
        pipeline_text = request.get("pipeline", "")
        params = request.get("params", {}) or {}
        logger.debug("POST /api/run: pipeline=%s... params=%s", pipeline_text[:80], params)

        if not engine_state.chrome_connected:
            raise APIError("Chrome is not connected — connect first via POST /api/chrome/connect")

        try:
            pipeline_name = _extract_pipeline_name(pipeline_text)
            wm = _get_workspace_manager(pipeline_name)
            wm.ensure_workspace()
            ts = int(time.time())
            snapshot_path = wm.versions_dir / f"snapshot_{ts}.pipeline.yaml"
            snapshot_path.write_text(pipeline_text, encoding="utf-8")

            from yak_browser_use.compiler.parser import inject_params_to_pipeline
            pipeline_text = inject_params_to_pipeline(pipeline_text, params)

            parsed, steps = _prepare_steps(pipeline_text, snapshot_path)

            if params:
                for step in steps:
                    if step.get("is_goal"):
                        desc = step.get("goal_description", "") or step.get("description", "")
                        extras = " | ".join(f"{k}={v}" for k, v in params.items())
                        step["goal_description"] = f"{desc} (params: {extras})"

            from yak_browser_use.engine._lifecycle.guardian import (
                create_guardian_from_frontmatter,
                inject_guardian_config_to_steps,
            )
            inject_guardian_config_to_steps(steps, parsed.frontmatter)
            guardian = create_guardian_from_frontmatter(parsed.frontmatter)

            from yak_browser_use.cdp.helpers import CDPHelpers
            browser = CDPHelpers(engine_state.bridge)

            try:
                from yak_browser_use.engine.runner_preset import run_pipeline
            except ImportError:
                raise ServerError(
                    "engine.runner_preset is not yet available — pipeline execution cannot start."
                )

            ctx = await run_pipeline(
                pipeline_name=parsed.name,
                steps=steps,
                cdp_helpers=browser,
                pipeline_path=snapshot_path,
                frontmatter=parsed.frontmatter,
                guardian=guardian,
            )

            status = "completed" if not ctx.errors else "failed"
            first_error = ctx.errors[0].get("message", str(ctx.errors[0])) if ctx.errors else None
            return JSONResponse({
                "run_id": ctx.run_id,
                "pipeline": ctx.pipeline_name,
                "status": status,
                "step_count": len(steps),
                "errors": ctx.errors,
                "error": first_error,
            })
        except APIError:
            raise
        except Exception as exc:
            logger.exception("POST /api/run failed")
            raise ServerError(str(exc))

    # =================================================================
    # STATUS
    # =================================================================

    @app.get("/api/status")
    async def api_status(pipeline: str = Query(None)) -> JSONResponse:
        """Query pipeline run status.

        Without ``?pipeline=`` returns the global engine state.
        With a pipeline name, returns the latest run metadata.
        """
        logger.debug("GET /api/status pipeline=%s", pipeline)

        if not pipeline:
            rp = engine_state.running_pipeline
            return JSONResponse({
                "current_state": engine_state.current_state,
                "chrome_connected": engine_state.chrome_connected,
                "active_pipeline": {
                    "run_id": rp.run_id,
                    "pipeline_name": rp.pipeline_name,
                } if rp else None,
            })

        try:
            wm = _get_workspace_manager(pipeline)
            runs = wm.list_runs()
            if not runs:
                return JSONResponse({"status": "idle", "pipeline": pipeline})

            latest = runs[0]
            return JSONResponse({
                "run_id": latest.get("run_id"),
                "pipeline": latest.get("pipeline"),
                "current_step": latest.get("current_step"),
                "status": latest.get("status"),
                "version": latest.get("version"),
                "created_at": latest.get("created_at"),
                "completed_at": latest.get("completed_at"),
            })
        except Exception as exc:
            logger.exception("GET /api/status failed")
            raise ServerError(str(exc))

    # =================================================================
    # CHROME
    # =================================================================

    async def _inject_initial_highlights() -> None:
        """Inject highlights on the current page after connect/restart."""
        from yak_browser_use.cdp.helpers import CDPHelpers

        if engine_state.bridge is None:
            return
        try:
            helpers = CDPHelpers(engine_state.bridge)
            await helpers.add_dom_highlights()
        except Exception:
            logger.debug("initial highlight injection after connect failed", exc_info=True)

    @app.post("/api/chrome/connect")
    async def api_chrome_connect(request: dict) -> JSONResponse:
        """Connect to Chrome via CDP WebSocket.

        Request body: ``{"mode": "user"|"isolated", "profile_name": "...", "ws_url": "..."}``
        """
        mode = request.get("mode", "user")
        profile_name = request.get("profile_name")
        ws_url = request.get("ws_url")
        highlight_mode = request.get("highlight_mode", "a11y")
        pipeline_name = request.get("pipeline_name")
        logger.info("Chrome connect requested: mode=%s profile=%s highlight=%s", mode, profile_name or "none", highlight_mode)

        if engine_state.running_pipeline is not None:
            raise APIError("A pipeline is currently running — cannot connect Chrome", status_code=409)

        try:
            if mode == "isolated" and profile_name:
                from yak_browser_use.cdp.launcher import launch_isolated_chrome
                ws_url = await launch_isolated_chrome(profile_name=profile_name)
            elif ws_url:
                pass
            else:
                from yak_browser_use.cdp.discover import discover_ws_url
                ws_url = await discover_ws_url(profile_name=profile_name)

            if pipeline_name is None:
                service = await _get_service()
                pipeline_name = service.sessions.active_pipeline

            actual_ws = await engine_state.connect_chrome(ws_url, pipeline_name=pipeline_name)

            # 监控 ybu 自己启动的浏览器进程（isolated mode），Edge 关窗口后进程可能
            # 留在后台，但只要进程最终退出就能触发断开
            if mode == "isolated":
                from yak_browser_use.cdp.launcher import get_launched_process
                proc = get_launched_process()
                if proc and engine_state.bridge:
                    engine_state.bridge.watch_process(proc)

            # 高亮注入是纯装饰性操作，不应阻塞连接成功响应
            if engine_state.bridge:
                try:
                    engine_state.bridge.set_highlight_config(highlight_mode)
                    await engine_state.bridge.ensure_highlights()
                except Exception:
                    logger.warning("Non-fatal: failed to set up initial highlights", exc_info=True)
            try:
                await _inject_initial_highlights()
            except Exception:
                logger.warning("Non-fatal: failed to inject initial highlights", exc_info=True)

            # 存活探测：用户可能在连接过程中关闭了浏览器，此时 bridge 虽已创建
            # 但 Playwright 的 disconnect 事件还在 asyncio 队列中未处理。
            # 如果不检查就直接返回 success，前端会先收到 connected=true，
            # 然后才收到 chrome_disconnected，造成"连接→断连→连接→断连"的闪烁。
            # 
            # 以下分三层检查：
            #   1) bridge._disconnected — _on_browser_disconnected 已同步执行完
            #   2) bridge.page is None  — _on_browser_disconnected 已清除 page
            #   3) page.evaluate("1+1") — 浏览器虽然还在但即将断开
            bridge = engine_state.bridge
            if bridge is None or bridge._disconnected or bridge.page is None:
                logger.warning("Browser already disconnected after bridge creation")
                await engine_state.disconnect_chrome()
                raise ServerError("Browser already disconnected after bridge creation")
            try:
                await asyncio.wait_for(bridge.page.evaluate("1+1"), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Browser health check timed out")
                await engine_state.disconnect_chrome()
                raise ServerError("Browser health check timed out")
            except Exception:
                logger.warning("Browser disconnected during connection setup")
                await engine_state.disconnect_chrome()
                raise ServerError("Browser disconnected during connection setup")

            return JSONResponse({"connected": True, "ws_url": actual_ws[:80]})
        except Exception as exc:
            logger.exception("Chrome connect failed")
            # 清理可能已创建但未完成的路由的 bridge
            if engine_state.bridge:
                await engine_state.disconnect_chrome()
            raise ServerError(str(exc))

    @app.get("/api/chrome/status")
    async def api_chrome_status() -> JSONResponse:
        """Return Chrome connection status and current engine state."""
        logger.debug("GET /api/chrome/status")
        connected = engine_state.chrome_connected
        rp = engine_state.running_pipeline
        return JSONResponse({
            "connected": connected,
            "current_state": engine_state.current_state,
            "active_pipeline": {
                "run_id": rp.run_id,
                "pipeline_name": rp.pipeline_name,
            } if rp else None,
        })

    @app.post("/api/chrome/disconnect")
    async def api_chrome_disconnect() -> JSONResponse:
        """Disconnect from Chrome."""
        logger.debug("POST /api/chrome/disconnect")

        if engine_state.running_pipeline is not None:
            raise APIError("A pipeline is currently running — cannot disconnect", status_code=409)

        if not engine_state.chrome_connected:
            return JSONResponse({"disconnected": True, "was_already": True})

        try:
            await engine_state.disconnect_chrome()
            return JSONResponse({"disconnected": True})
        except Exception as exc:
            logger.exception("POST /api/chrome/disconnect failed")
            raise ServerError(str(exc))

    @app.post("/api/chrome/save-page")
    async def api_chrome_save_page() -> JSONResponse:
        """Debug: save current page HTML + screenshot (all elements visible), overwriting previous dump."""
        if engine_state.bridge is None or not engine_state.bridge._page:
            raise APIError("No Chrome connected", status_code=400)
        import base64, json as _json
        bridge = engine_state.bridge
        page = bridge._page
        # Push ALL elements to page (bypass ensure_highlights cap), render, capture, then restore capped view
        full_list = list(bridge._last_highlight_elements)
        try:
            await page.evaluate(
                f"window.__ybu_last_elements = {_json.dumps(full_list)};"
            )
            await page.evaluate("window.__ybu_run && window.__ybu_run();")
            await asyncio.sleep(0.05)
        except Exception:
            logger.warning("save-page: pre-render failed", exc_info=True)

        debug_dir = project_root() / "debug-page"
        debug_dir.mkdir(parents=True, exist_ok=True)
        try:
            html = await page.content()
            (debug_dir / "page.html").write_text(html, encoding="utf-8")
        except Exception as e:
            logger.warning("save-page html failed: %s", e)
        try:
            png = await bridge.screenshot()
            (debug_dir / "screenshot.png").write_bytes(base64.b64decode(png))
        except Exception as e:
            logger.warning("save-page screenshot failed: %s", e)
        logger.info("Page saved to %s", debug_dir)

        # Restore capped view
        try:
            await bridge.ensure_highlights()
        except Exception:
            logger.warning("save-page: restore highlights failed", exc_info=True)
        return JSONResponse({"ok": True, "path": str(debug_dir)})

    @app.post("/api/chrome/restart")
    async def api_chrome_restart() -> JSONResponse:
        """Restart the user Chrome browser and reconnect."""
        logger.info("Chrome restart requested")

        if engine_state.running_pipeline is not None:
            raise APIError("A pipeline is currently running", status_code=409)

        try:
            from yak_browser_use.cdp.launcher import restart_user_chrome

            ws_url = await restart_user_chrome()
            if not ws_url:
                raise RuntimeError("Cannot restart Chrome")

            service = await _get_service()
            pipeline_name = service.sessions.active_pipeline

            captured_mode = engine_state.bridge._highlight_mode if engine_state.bridge else "a11y"

            await engine_state.disconnect_chrome()

            actual_ws = await engine_state.connect_chrome(ws_url, pipeline_name=pipeline_name)

            if engine_state.bridge:
                try:
                    engine_state.bridge.set_highlight_config(captured_mode)
                    await engine_state.bridge.ensure_highlights()
                except Exception:
                    logger.warning("Non-fatal: failed to set up highlights after restart", exc_info=True)
            try:
                await _inject_initial_highlights()
            except Exception:
                logger.warning("Non-fatal: failed to inject highlights after restart", exc_info=True)

            bridge = engine_state.bridge
            if bridge is None or bridge._disconnected or bridge.page is None:
                logger.warning("Browser already disconnected after restart setup")
                await engine_state.disconnect_chrome()
                raise ServerError("Browser disconnected during restart setup")
            try:
                await asyncio.wait_for(bridge.page.evaluate("1+1"), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Browser health check timed out after restart")
                await engine_state.disconnect_chrome()
                raise ServerError("Browser health check timed out after restart")
            except Exception:
                logger.warning("Browser disconnected during restart setup")
                await engine_state.disconnect_chrome()
                raise ServerError("Browser disconnected during restart setup")

            return JSONResponse({"connected": True, "ws_url": actual_ws[:80]})
        except Exception as exc:
            logger.exception("Chrome restart failed")
            if engine_state.bridge:
                await engine_state.disconnect_chrome()
            raise ServerError(str(exc))

    # =================================================================
    # HIGHLIGHT CONFIG
    # =================================================================

    @app.post("/api/highlight-config")
    async def api_highlight_config(request: dict) -> JSONResponse:
        """Set highlight mode: ``"a11y"``, ``"progressive"``, or ``"off"``.

        Request body: ``{"mode": "a11y|progressive|off"}``
        """
        mode = request.get("mode", "a11y")
        if mode not in ("a11y", "progressive", "off"):
            raise APIError(f"Invalid mode: {mode!r}, must be a11y/progressive/off")
        if engine_state.bridge:
            engine_state.bridge.set_highlight_config(mode)
            await engine_state.bridge.ensure_highlights()
            logger.info("Highlight mode set to %s", mode)
        return JSONResponse({"ok": True, "mode": mode})

    @app.post("/api/prog-label")
    async def api_prog_label(request: dict) -> JSONResponse:
        """Resolve a ref or prog_label to full element details.

        Request body: ``{"id": "p_175"}`` or ``{"id": "0-2-175"}

        Returns {ref, prog_label, selector, tag, text, role} or error.
        """
        rid = request.get("id", "")
        if not rid:
            raise APIError("missing 'id' field")
        bridge = engine_state.bridge
        if not bridge or not bridge.page:
            raise APIError("browser not connected")

        ref = None
        # Try direct ref lookup
        if rid.startswith("p_") or rid.startswith("a_"):
            ref = f"@{rid}"
        elif rid.startswith("@"):
            ref = rid

        el = bridge._ref_map.get(ref) if ref else None
        # Fallback: scan _ref_map for matching prog_label
        if not el and "-" in rid:
            for r, e in bridge._ref_map.items():
                if e.get("_prog_label") == rid:
                    el = e
                    ref = r
                    break

        if not el:
            return JSONResponse({"ok": False, "error": f"{rid} not found in current snapshot"})

        pub = {k: v for k, v in el.items() if not k.startswith("_")}
        pub["prog_label"] = el.get("_prog_label", ref.lstrip("@"))
        return JSONResponse({"ok": True, **pub})

    @app.get("/api/chrome/isolated-profiles")
    async def api_list_isolated_profiles() -> JSONResponse:
        """List all isolated Chrome profile directories."""
        from yak_browser_use.cdp.launcher import _ISO_PROFILES_DIR

        profiles = []
        if _ISO_PROFILES_DIR.exists():
            for entry in sorted(_ISO_PROFILES_DIR.iterdir()):
                if entry.is_dir():
                    profiles.append(entry.name)
        return JSONResponse({"profiles": profiles})

    @app.post("/api/chrome/isolated-profiles/{profile_name}")
    async def api_create_isolated_profile(profile_name: str) -> JSONResponse:
        """Create a new isolated Chrome profile directory."""
        from yak_browser_use.cdp.launcher import get_isolated_profile_dir

        profile_dir = get_isolated_profile_dir(profile_name)
        profile_dir.mkdir(parents=True, exist_ok=True)
        return JSONResponse({"created": True, "profile_name": profile_name})

    # =================================================================
    # PARAMS  (replaces the old /api/auth/* and /api/credentials/*)
    # =================================================================

    @app.get("/api/params")
    async def api_list_params() -> JSONResponse:
        """List all stored parameter keys."""
        try:
            from yak_browser_use.params.manager import list_param_keys
            keys = list_param_keys()
            return JSONResponse({"params": keys})
        except Exception as exc:
            raise ServerError(str(exc))

    @app.post("/api/params")
    async def api_set_param(request: dict) -> JSONResponse:
        """Set a parameter value.

        Request body: ``{"key": "name", "value": "val"}``
        """
        key = request.get("key", "")
        value = request.get("value", "")
        if not key or not value:
            raise APIError("'key' and 'value' are required")

        try:
            from yak_browser_use.params.manager import ParamManager
            pm = ParamManager()
            pm.set(key, value)
            logger.info("param set: %s", key)
            return JSONResponse({"key": key, "set": True})
        except Exception as exc:
            logger.exception("set param failed: %s", key)
            raise ServerError(str(exc))

    @app.delete("/api/params/{key:path}")
    async def api_delete_param(key: str) -> JSONResponse:
        """Delete a parameter by key."""
        try:
            from yak_browser_use.params.manager import delete_param, list_param_keys
            if key not in list_param_keys():
                return JSONResponse({"key": key, "deleted": False, "found": False})
            delete_param(key)
            logger.info("param deleted: %s", key)
            return JSONResponse({"key": key, "deleted": True, "found": True})
        except Exception as exc:
            raise ServerError(str(exc))

    # =================================================================
    # VERSIONS
    # =================================================================

    @app.get("/api/versions/{pipeline_name:path}")
    async def api_list_versions(pipeline_name: str) -> JSONResponse:
        """List all version snapshots for a pipeline."""
        try:
            from yak_browser_use.workspace.version_manager import VersionManager
            wm = _get_workspace_manager(pipeline_name)
            wm.ensure_workspace()
            vm = VersionManager(wm.versions_dir, pipeline_name)
            versions = vm.list_versions()
            return JSONResponse({"versions": versions})
        except Exception as exc:
            logger.exception("GET /api/versions/%s failed", pipeline_name)
            raise ServerError(str(exc))

    @app.get("/api/versions/{pipeline_name:path}/{version}")
    async def api_get_version(pipeline_name: str, version: str) -> JSONResponse:
        """Get the content of a specific version snapshot."""
        try:
            from yak_browser_use.workspace.version_manager import VersionManager
            wm = _get_workspace_manager(pipeline_name)
            wm.ensure_workspace()
            vm = VersionManager(wm.versions_dir, pipeline_name)
            loaded = vm.load_version(version)
            if loaded:
                pipeline_path, _ = loaded
                content = pipeline_path.read_text(encoding="utf-8")
                return JSONResponse({"version": version, "content": content})
            raise APIError("version not found", status_code=404)
        except APIError:
            raise
        except Exception as exc:
            logger.exception("GET /api/versions/%s/%s failed", pipeline_name, version)
            raise ServerError(str(exc))

    @app.post("/api/versions/{pipeline_name:path}/relearn")
    async def api_relearn(pipeline_name: str) -> JSONResponse:
        """Delete the LATEST version snapshot so it can be re-learned."""
        try:
            from yak_browser_use.workspace.version_manager import VersionManager
            wm = _get_workspace_manager(pipeline_name)
            wm.ensure_workspace()
            vm = VersionManager(wm.versions_dir, pipeline_name)
            latest = vm.get_latest()
            if not latest:
                return JSONResponse({"deleted": False, "error": "no LATEST version found"})
            ver_dir = vm.versions_dir / latest
            if ver_dir.exists():
                import shutil
                shutil.rmtree(str(ver_dir), ignore_errors=True)
            if vm.latest_file.exists():
                vm.latest_file.unlink()
            if vm.stale_file.exists():
                vm.stale_file.unlink()
            return JSONResponse({"deleted": True, "version": latest})
        except Exception as exc:
            logger.exception("POST /api/versions/%s/relearn failed", pipeline_name)
            raise ServerError(str(exc))

    # =================================================================
    # PIPELINE — restart / cancel / runs
    # =================================================================

    @app.post("/api/pipeline/{pipeline_name:path}/{run_id}/restart")
    async def api_restart_pipeline(pipeline_name: str, run_id: str) -> JSONResponse:
        """Restart a paused or failed pipeline from where it left off."""
        logger.debug("POST /api/pipeline/%s/%s/restart", pipeline_name, run_id)

        if not engine_state.chrome_connected:
            raise APIError("Chrome is not connected — connect first via POST /api/chrome/connect")

        try:
            wm = _get_workspace_manager(pipeline_name)
            run_dir = wm.root / run_id
            if not run_dir.exists():
                raise APIError("run not found", status_code=404)

            status = wm.get_status(run_dir)
            if status not in ("paused", "failed"):
                raise APIError(
                    f"pipeline status is '{status}', expected 'paused' or 'failed'"
                )

            resume_from_index = 0
            exec_tree_path = run_dir / "_execution_tree.json"
            if exec_tree_path.exists():
                tree = json.loads(exec_tree_path.read_text(encoding="utf-8"))
                nodes = tree.get("nodes", [])
                success_nodes = [n for n in nodes if n.get("status") == "success"]
                if success_nodes:
                    last_success = max(success_nodes, key=lambda n: n.get("index", 0))
                    resume_from_index = last_success.get("index", 0) + 1

            from yak_browser_use.workspace.version_manager import VersionManager
            vm = VersionManager(wm.versions_dir, pipeline_name)
            latest_ver = vm.get_latest()
            if not latest_ver:
                raise APIError("no version found for pipeline", status_code=404)

            loaded = vm.load_version(latest_ver)
            if not loaded:
                raise APIError("version data not found", status_code=404)
            pipeline_path, _ = loaded
            pipeline_text = pipeline_path.read_text(encoding="utf-8")

            parsed, steps = _prepare_steps(pipeline_text, pipeline_path)

            from yak_browser_use.engine._lifecycle.guardian import (
                create_guardian_from_frontmatter,
                inject_guardian_config_to_steps,
            )
            inject_guardian_config_to_steps(steps, parsed.frontmatter)
            guardian = create_guardian_from_frontmatter(parsed.frontmatter)

            ts = int(time.time())
            snapshot_path = wm.versions_dir / f"snapshot_{ts}.pipeline.yaml"
            snapshot_path.write_text(pipeline_text, encoding="utf-8")

            try:
                from yak_browser_use.engine.runner_preset import run_pipeline
            except ImportError:
                raise ServerError("engine.runner_preset is not yet available")

            from yak_browser_use.cdp.helpers import CDPHelpers
            browser = CDPHelpers(engine_state.bridge)

            ctx = await run_pipeline(
                pipeline_name=pipeline_name,
                steps=steps,
                cdp_helpers=browser,
                pipeline_path=snapshot_path,
                frontmatter=parsed.frontmatter,
                resume_from_index=resume_from_index,
                guardian=guardian,
            )

            final_status = "completed" if not ctx.errors else "failed"
            return JSONResponse({
                "status": "restarted",
                "run_id": ctx.run_id,
                "pipeline": ctx.pipeline_name,
                "resume_from_index": resume_from_index,
                "pipeline_status": final_status,
            })
        except APIError:
            raise
        except Exception as exc:
            logger.exception("POST /api/pipeline/%s/%s/restart failed", pipeline_name, run_id)
            raise ServerError(str(exc))

    @app.post("/api/pipeline/{pipeline_name:path}/{run_id}/cancel")
    async def api_cancel_pipeline(pipeline_name: str, run_id: str) -> JSONResponse:
        """Cancel a running or paused pipeline."""
        logger.debug("POST /api/pipeline/%s/%s/cancel", pipeline_name, run_id)

        try:
            wm = _get_workspace_manager(pipeline_name)
            run_dir = wm.root / run_id
            if not run_dir.exists():
                raise APIError("run not found", status_code=404)

            status = wm.get_status(run_dir)
            if status not in ("running", "paused"):
                raise APIError(f"pipeline status is '{status}', cannot cancel")

            wm.set_status(run_dir, "cancelled")
            logger.info("pipeline [%s] run %s cancelled via API", pipeline_name, run_id)
            return JSONResponse({
                "cancelled": True,
                "run_id": run_id,
                "pipeline": pipeline_name,
            })
        except Exception as exc:
            logger.exception("POST /api/pipeline/%s/%s/cancel failed", pipeline_name, run_id)
            raise ServerError(str(exc))

    @app.get("/api/pipeline/{pipeline_name:path}/runs")
    async def api_pipeline_runs(pipeline_name: str) -> JSONResponse:
        """List all runs for a pipeline."""
        logger.debug("GET /api/pipeline/%s/runs", pipeline_name)
        try:
            wm = _get_workspace_manager(pipeline_name)
            runs = wm.list_runs()
            return JSONResponse({"pipeline": pipeline_name, "runs": runs})
        except Exception as exc:
            logger.exception("GET /api/pipeline/%s/runs failed", pipeline_name)
            raise ServerError(str(exc))

    @app.post("/api/pipeline/{thread_id}/review")
    async def api_review_step(thread_id: str, request: dict) -> JSONResponse:
        """Review/approve/reject a pending pipeline operation.

        NOTE: Full implementation requires engine.checkpoint.MemorySaver
        which is not yet available in this project. Currently returns 501.
        """
        logger.warning("POST /api/pipeline/%s/review called but not implemented", thread_id)
        return JSONResponse(
            {"status": "error", "error": "review endpoint not implemented", "code": "NOT_IMPLEMENTED"},
            status_code=501,
        )

    # =================================================================
    # WORKSPACE — events
    # =================================================================

    @app.get("/api/workspace/{pipeline_name:path}/{run_id}/events")
    async def api_workspace_events(pipeline_name: str, run_id: str) -> JSONResponse:
        """Get the full event log for a specific pipeline run."""
        logger.debug("GET /api/workspace/%s/%s/events", pipeline_name, run_id)
        try:
            wm = _get_workspace_manager(pipeline_name)
            events_path = wm.root / run_id / "_events.jsonl"
            if not events_path.exists():
                return JSONResponse({"pipeline": pipeline_name, "run_id": run_id, "events": []})

            events: list[dict[str, Any]] = []
            with open(events_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))

            return JSONResponse({
                "pipeline": pipeline_name,
                "run_id": run_id,
                "events": events,
            })
        except Exception as exc:
            logger.exception("GET /api/workspace/%s/%s/events failed", pipeline_name, run_id)
            raise ServerError(str(exc))

    # =================================================================
    # CHAT — interactive conversation endpoints
    # =================================================================

    @app.post("/api/chat")
    async def chat_message(request: dict) -> JSONResponse:
        """Process a chat message through the conversation engine.

        Request: {"message": "open baidu and search coffee"}
        Response: {"ok": true, "response": "...", "turn_count": 3, ...}
        """
        from yak_browser_use.engine.agent import _create_chat_llm_call

        message = request.get("message", "").strip()
        if not message:
            raise APIError("message is required")

        pipeline_name = request.get("pipeline_name", "") or ""
        if pipeline_name:
            pipeline_name = Path(pipeline_name).name  # sanitize

        logger.info("Chat message: %s (pipeline=%s)", message[:120], pipeline_name or "none")
        service = await _get_service()

        session = service.get_session()
        if session is None:
            session = service.create_session()
        session_id = session.session_id
        turn_index = (len(session.messages) if session else 0) + 1

        def _push(event: dict) -> None:
            service.events.push(event)

        def _on_stream_start() -> None:
            _push({"type": "chat.stream_start", "turn_index": turn_index})

        def _on_stream_end(has_tool_calls: bool) -> None:
            _push({"type": "chat.stream_end", "has_tool_calls": has_tool_calls, "turn_index": turn_index})

        def _on_text_delta(text: str) -> None:
            _push({"type": "chat.text_chunk", "content": text, "turn_index": turn_index})

        def _on_reasoning_delta(text: str) -> None:
            _push({"type": "chat.think_chunk", "content": text, "turn_index": turn_index})

        def _on_tool_generated(name: str) -> None:
            _push({"type": "chat.tool_generated", "tool_name": name, "turn_index": turn_index})

        def _interrupt_check() -> bool:
            s = service.get_session()
            return s is not None and s.status == "cancelled"

        llm_call = _create_chat_llm_call(
            persist_id=session_id,
            on_stream_start=_on_stream_start,
            on_stream_end=_on_stream_end,
            on_text_delta=_on_text_delta,
            on_reasoning_delta=_on_reasoning_delta,
            on_tool_generated=_on_tool_generated,
            interrupt_check=_interrupt_check,
        )

        try:
            from yak_browser_use.cdp.helpers import CDPHelpers

            browser = CDPHelpers(engine_state.bridge) if engine_state.bridge else None
            if browser is not None:
                try:
                    await browser.add_dom_highlights()
                except Exception:
                    logger.debug("initial highlight injection failed", exc_info=True)

            result = await service.process_chat_message(
                message=message,
                cdp_helpers=browser,
                tools_dir=Path("tools"),
                pipeline_name=pipeline_name or "chat",
                llm_call=llm_call,
            )
            resp_preview = (result.get("response") or "")[:80]
            logger.info("Chat response (%s, %d turns, %dms): %s",
                        result.get("status", "?"),
                        result.get("turn_count", 0),
                        result.get("duration_ms", 0),
                        resp_preview)
            return JSONResponse(result)
        except Exception as exc:
            logger.exception("Chat processing failed")
            raise ServerError(str(exc))

    @app.post("/api/chat/reset")
    async def chat_reset() -> JSONResponse:
        """Reset the current chat session and start fresh."""
        service = await _get_service()
        session = service.reset_session()
        logger.info("Chat session reset: new session_id=%s", session.session_id)
        return JSONResponse({
            "ok": True,
            "session_id": session.session_id,
            "status": session.status,
        })

    @app.post("/api/chat/cancel")
    async def chat_cancel() -> JSONResponse:
        """Cancel the current chat session."""
        service = await _get_service()
        service.cancel_session()
        logger.info("Chat session cancelled")
        return JSONResponse({"ok": True})

    @app.post("/api/chat/confirm")
    async def chat_confirm(request: dict) -> JSONResponse:
        """Confirm a pipeline edit — delete the checkpoint file and sync preset to workspace.

        Request body: {"edit_id": "..."}

        Idempotent: repeated calls return {"status": "already_confirmed"}.
        """
        edit_id = request.get("edit_id", "").strip()
        if not edit_id:
            return JSONResponse({"status": "error", "error": "edit_id is required"}, status_code=400)

        try:
            from yak_browser_use.tools.edit_pipeline import (
                delete_checkpoint, get_checkpoint_path,
                get_edit_status, set_edit_status,
                get_edit_pipeline_name,
            )
            status = get_edit_status(edit_id)
            if status == "confirmed":
                return JSONResponse({"status": "already_confirmed"})
            if status == "reverted":
                return JSONResponse({"status": "error", "error": "Edit was already reverted"}, status_code=409)

            cp = get_checkpoint_path(edit_id)
            if cp and cp.exists():
                delete_checkpoint(edit_id)

            set_edit_status(edit_id, "confirmed")

            logger.info("Edit %s confirmed, checkpoint deleted", edit_id)
            return JSONResponse({"status": "confirmed"})
        except Exception as exc:
            logger.exception("Confirm edit %s failed", edit_id)
            raise ServerError(str(exc))

    @app.post("/api/chat/revert")
    async def chat_revert(request: dict) -> JSONResponse:
        """Revert a pipeline edit — restore the checkpoint file.

        Request body: {"edit_id": "..."}

        Copies the checkpoint back to pipeline.yaml and deletes the checkpoint.
        Idempotent: repeated calls return {"status": "already_reverted"}.
        Returns error if the edit was already confirmed.
        """
        edit_id = request.get("edit_id", "").strip()
        if not edit_id:
            return JSONResponse({"status": "error", "error": "edit_id is required"}, status_code=400)

        try:
            from yak_browser_use.tools.edit_pipeline import (
                delete_checkpoint, get_checkpoint_path,
                get_edit_status, set_edit_status,
                get_edit_pipeline_name,
            )
            status = get_edit_status(edit_id)
            if status == "confirmed":
                return JSONResponse({"status": "error", "error": "already_confirmed"}, status_code=409)
            if status == "reverted":
                return JSONResponse({"status": "already_reverted"})

            cp = get_checkpoint_path(edit_id)
            if not cp or not cp.exists():
                set_edit_status(edit_id, "reverted")
                return JSONResponse({"status": "already_reverted"})

            original = cp.read_text(encoding="utf-8")

            pipeline_name = get_edit_pipeline_name(edit_id)
            pipeline_path = cp.parent / "pipeline.yaml"
            pipeline_path.write_text(original, encoding="utf-8")

            if pipeline_name:
                logger.info("Edit %s reverted, pipeline restored", edit_id)

            delete_checkpoint(edit_id)
            set_edit_status(edit_id, "reverted")
            logger.info("Edit %s reverted, checkpoint restored to %s", edit_id, pipeline_path)
            return JSONResponse({"status": "reverted"})
        except Exception as exc:
            logger.exception("Revert edit %s failed", edit_id)
            raise ServerError(str(exc))

    @app.get("/api/session")
    async def get_session(pipeline: str = Query("")) -> JSONResponse:
        """Get the current session state for a pipeline."""
        service = await _get_service()
        session = service.get_session(pipeline if pipeline else None)
        if session is None:
            return JSONResponse({"session": None})
        return JSONResponse({
            "session": {
                "session_id": session.session_id,
                "pipeline_name": session.pipeline_name,
                "status": session.status,
                "message_count": len(session.messages),
            },
        })

    @app.post("/api/session/new")
    async def session_new(request: dict) -> JSONResponse:
        """Create a new session for a pipeline."""
        service = await _get_service()
        pipeline_name = request.get("pipeline_name", "")
        result = service.new_session(pipeline_name)
        return JSONResponse(result)

    @app.post("/api/session/switch")
    async def session_switch(request: dict) -> JSONResponse:
        """Switch active pipeline, save current session, load target."""
        service = await _get_service()
        pipeline_name = request.get("pipeline_name", "")
        sessions = service.switch_session(pipeline_name)

        if engine_state.bridge is not None:
            try:
                await engine_state.bridge.set_download_pipeline(pipeline_name)
            except Exception:
                logger.debug("session_switch: set_download_pipeline failed", exc_info=True)

        return JSONResponse({"sessions": sessions})

    @app.get("/api/session/{pipeline_name}/list")
    async def session_list(pipeline_name: str) -> JSONResponse:
        """List all sessions for a pipeline.

        Persists the current in-memory session first so the index reflects
        the latest message_count and updated_at before reading from disk.
        """
        service = await _get_service()
        mem = service.get_session(pipeline_name)
        if mem is not None:
            service.sessions.persist_session(mem, context="list")

        from yak_browser_use.workspace.session_store import SessionStore
        store = SessionStore(pipeline_name)
        store.ensure_session_dir()
        sessions = store.list_sessions()
        return JSONResponse({"sessions": sessions})

    @app.post("/api/session/{pipeline_name}/{session_id}/archive")
    async def session_archive(pipeline_name: str, session_id: str) -> JSONResponse:
        """Archive a session (soft-delete)."""
        service = await _get_service()
        ok = service.archive_session(pipeline_name, session_id)
        if not ok:
            return JSONResponse({"ok": False, "error": "Session not found"}, status_code=404)
        return JSONResponse({"ok": True})

    @app.get("/api/session/{pipeline_name}/{session_id}")
    async def session_get(pipeline_name: str, session_id: str) -> JSONResponse:
        """Get full session data (including messages) by ID.

        Checks in-memory session first (most up-to-date), falls back to disk.
        """
        service = await _get_service()
        mem = service.get_session(pipeline_name)
        if mem is not None and mem.session_id == session_id:
            return JSONResponse({"session": {
                "session_id": mem.session_id,
                "pipeline_name": mem.pipeline_name,
                "status": mem.status,
                "created_at": mem.created_at,
                "messages": mem.messages,
                "budget_snapshot": mem.budget_snapshot,
            }})

        from yak_browser_use.workspace.session_store import SessionStore
        store = SessionStore(pipeline_name)
        data = store.load_session(session_id)
        if data is None:
            return JSONResponse({"session": None})
        return JSONResponse({"session": data})

    # =================================================================
    # PRESET — save/load/list pipeline presets
    # =================================================================

    @app.get("/api/presets")
    async def list_presets() -> JSONResponse:
        """List all saved pipelines from workspaces/."""
        service = await _get_service()
        presets = service.list_presets()
        return JSONResponse({"presets": presets})

    @app.delete("/api/presets/{name}")
    async def delete_preset(name: str) -> JSONResponse:
        """Delete a pipeline workspace."""
        import shutil
        from yak_browser_use.workspace.manager import WORKSPACES_ROOT
        safe_name = Path(name).name
        workspace_dir = WORKSPACES_ROOT / safe_name
        if workspace_dir.exists() and workspace_dir.is_dir():
            shutil.rmtree(str(workspace_dir))
            return JSONResponse({"ok": True})
        raise APIError(f"Pipeline '{name}' not found", 404)

    # =================================================================
    # PIPELINES — list workspace pipelines
    # =================================================================

    @app.get("/api/pipelines")
    async def api_list_pipelines() -> JSONResponse:
        """List all pipelines from workspaces/."""
        from yak_browser_use.workspace.manager import WORKSPACES_ROOT
        workspaces_dir = WORKSPACES_ROOT
        pipelines: list[dict] = []
        if workspaces_dir.exists():
            for d in sorted(workspaces_dir.iterdir()):
                if not d.is_dir() or d.name.startswith("."):
                    continue
                pipe_file = d / "pipeline.yaml"
                if pipe_file.exists():
                    name = d.name
                    description = ""
                    stages: list[str] = []
                    step_count = 0
                    try:
                        import yaml
                        raw = yaml.safe_load(pipe_file.read_text(encoding="utf-8"))
                        if isinstance(raw, dict):
                            name = raw.get("name", name)
                            description = raw.get("description", "")
                            steps_raw = raw.get("steps", [])
                            if isinstance(steps_raw, list):
                                stages = [s.get("name", f"step_{i}") for i, s in enumerate(steps_raw)]
                                step_count = len(steps_raw)
                    except Exception:
                        pass
                    pipelines.append({
                        "name": name,
                        "title": name,
                        "description": description,
                        "stages": stages,
                        "step_count": step_count,
                    })
        return JSONResponse({"pipelines": pipelines})

    @app.get("/api/pipelines/{name}")
    async def api_get_pipeline(name: str) -> JSONResponse:
        """Get a specific pipeline's content from workspaces/."""
        from yak_browser_use.workspace.manager import WORKSPACES_ROOT
        safe_name = Path(name).name
        pipe_path = WORKSPACES_ROOT / safe_name / "pipeline.yaml"
        if not pipe_path.exists():
            raise APIError("pipeline not found", status_code=404)
        content = pipe_path.read_text(encoding="utf-8")
        meta: dict = {"name": name, "title": name, "description": "", "stages": [], "step_count": 0}
        try:
            import yaml
            raw = yaml.safe_load(content)
            if isinstance(raw, dict):
                meta["name"] = raw.get("name", name)
                meta["title"] = meta["name"]
                meta["description"] = raw.get("description", "")
                steps_raw = raw.get("steps", [])
                if isinstance(steps_raw, list):
                    meta["stages"] = [s.get("name", f"step_{i}") for i, s in enumerate(steps_raw)]
                    meta["step_count"] = len(steps_raw)
        except Exception:
            pass
        return JSONResponse({"name": name, "content": content, "meta": meta})

    @app.put("/api/pipelines/{name}")
    async def api_save_pipeline(name: str, request: dict) -> JSONResponse:
        """Save/update a pipeline's YAML content.

        Request body: ``{"content": "..."}``
        Validates that the content is parseable YAML before saving.
        """
        content = request.get("content", "")
        if not content or not content.strip():
            raise APIError("'content' is required and must not be empty")

        import yaml
        try:
            parsed = yaml.safe_load(content)
            if not isinstance(parsed, dict):
                raise APIError("Pipeline YAML must be a mapping (dict) at top level")
        except yaml.YAMLError as e:
            raise APIError(f"Invalid YAML: {e}")

        from yak_browser_use.workspace.manager import WORKSPACES_ROOT
        safe_name = Path(name).name
        workspace_dir = WORKSPACES_ROOT / safe_name
        workspace_dir.mkdir(parents=True, exist_ok=True)
        pipe_path = workspace_dir / "pipeline.yaml"
        pipe_path.write_text(content, encoding="utf-8")
        logger.info("Pipeline saved: %s", pipe_path)
        return JSONResponse({"ok": True, "name": name})

    @app.delete("/api/pipelines/{name}")
    async def api_delete_pipeline(name: str) -> JSONResponse:
        """Delete a pipeline workspace."""
        import shutil
        from yak_browser_use.workspace.manager import WORKSPACES_ROOT
        safe_name = Path(name).name
        workspace_dir = WORKSPACES_ROOT / safe_name
        if workspace_dir.exists() and workspace_dir.is_dir():
            shutil.rmtree(str(workspace_dir))
            return JSONResponse({"ok": True, "name": name})
        raise APIError(f"Pipeline '{name}' not found", 404)

    # =================================================================
    # WEB SOCKET — real-time event stream
    # =================================================================

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        """WebSocket endpoint for real-time pipeline event streaming.

        Each connected client receives event dicts as JSON text messages.
        """
        await websocket.accept()
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        engine_state.ws_clients.append(q)
        logger.debug("WebSocket client connected (%d total)", len(engine_state.ws_clients))

        try:
            while True:
                event = await q.get()
                try:
                    await websocket.send_json(event)
                except Exception:
                    break
        except WebSocketDisconnect:
            pass
        finally:
            if q in engine_state.ws_clients:
                engine_state.ws_clients.remove(q)
            logger.debug("WebSocket client disconnected (%d remaining)", len(engine_state.ws_clients))

    @app.websocket("/ws/logs")
    async def ws_logs(websocket: WebSocket) -> None:
        """WebSocket endpoint for log forwarding.

        Electron main process sends log lines as JSON messages here,
        and they are echoed to the backend console stdout.
        Expected message format: ``{"ts": "...", "level": "...", "name": "...", "msg": "..."}``
        """
        import sys
        await websocket.accept()
        logger.debug("Log relay connected")
        try:
            while True:
                data = await websocket.receive_json()
                level = data.get("level", "INFO")
                name = data.get("name", "electron")
                msg = data.get("msg", "")
                ts = data.get("ts", "")
                line = f"{ts} [{level:<5}] [{name}] {msg}"
                print(line, file=sys.stdout, flush=True)
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.debug("Log relay error", exc_info=True)
        finally:
            logger.debug("Log relay disconnected")

    @app.post("/api/logs/forward")
    async def api_logs_forward(request: dict) -> JSONResponse:
        """HTTP endpoint for batched log forwarding from Electron.

        Request body: ``{"entries": [{"ts": "...", "level": "...", "name": "...", "msg": "..."}, ...]}``
        """
        import sys
        entries = request.get("entries", [])
        for entry in entries:
            level = entry.get("level", "INFO")
            name = entry.get("name", "electron")
            msg = entry.get("msg", "")
            ts = entry.get("ts", "")
            line = f"{ts} [{level:<5}] [{name}] {msg}"
            print(line, file=sys.stdout, flush=True)
        return JSONResponse({"ok": True, "count": len(entries)})


# ── Internal helpers ────────────────────────────────────────────────


async def _get_service() -> Any:
    """Return the singleton Service instance, creating it if needed."""
    from yak_browser_use.api.service import Service

    async with engine_state._service_lock:
        if engine_state._service is None:
            engine_state._service = Service(engine_state)
        return engine_state._service


def _get_workspace_manager(pipeline_name: str) -> Any:
    """Return a WorkspaceManager for *pipeline_name*."""
    from yak_browser_use.workspace.manager import WorkspaceManager
    return WorkspaceManager(pipeline_name)


def _prepare_steps(content: str, pipeline_path: Path) -> tuple[Any, list[dict]]:
    """Parse pipeline.yaml and prepare ordered steps.

    Returns (parsed_frontmatter_plus, steps_data).
    """
    from yak_browser_use.compiler.prepare import prepare_steps
    return prepare_steps(content, pipeline_path)
