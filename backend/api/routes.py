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

from api.errors import APIError, ServerError
from api.state import engine_state
from tools.edit_pipeline import (
    delete_checkpoint, get_checkpoint_path,
    get_edit_status, set_edit_status,
)
from utils.logging import get_logger

logger = get_logger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────


def _extract_pipeline_name(pipeline_text: str) -> str:
    """Extract pipeline name from pipeline.yaml."""
    import yaml
    try:
        data = yaml.safe_load(pipeline_text)
        if isinstance(data, dict) and "name" in data:
            return str(data["name"]).strip().strip('"').strip("'")
    except Exception:
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
        from utils.browser import _get_config_path
        p = _get_config_path()
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return JSONResponse({"ok": True, "config": data})
            except Exception:
                pass
        return JSONResponse({"ok": True, "config": {}})

    @app.post("/api/provider-config")
    async def api_set_provider_config(request: dict) -> JSONResponse:
        """Save LLM provider configuration."""
        from utils.browser import _get_config_path
        p = _get_config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
        return JSONResponse({"ok": True})

    @app.post("/api/provider-test")
    async def api_test_provider(request: dict) -> JSONResponse:
        """Test an LLM provider config by making a simple call."""
        try:
            from browser_use.llm.openai.chat import ChatOpenAI
            from browser_use.llm.messages import UserMessage

            model = request.get("model", "gpt-4o")
            api_key = request.get("api_key", "")
            api_base = request.get("api_base", "")

            kwargs: dict = {"model": model}
            if api_key:
                kwargs["api_key"] = api_key
            if api_base:
                kwargs["base_url"] = api_base

            llm = ChatOpenAI(**kwargs)
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
    # CONVERT
    # =================================================================

    @app.post("/api/convert")
    async def api_convert(request: dict) -> JSONResponse:
        """Convert a natural language document to pipeline.yaml format.

        Request body: ``{"document": "...", "pipeline_name": "..."}``
        """
        from converter.convert import convert_document

        document = request.get("document", "")
        pipeline_name = request.get("pipeline_name")
        logger.debug("POST /api/convert: document=%s...", document[:80])
        try:
            result = await convert_document(document, pipeline_name=pipeline_name)
            return JSONResponse({"pipeline": result})
        except Exception as exc:
            logger.exception("POST /api/convert failed")
            raise ServerError(str(exc))

    # =================================================================
    # RUN
    # =================================================================

    @app.post("/api/run")
    async def api_run(request: dict) -> JSONResponse:
        """Execute a pipeline.yaml pipeline (runs as an async background task).

        Request body: ``{"pipeline": "...", "params": {...}, "engine": "programmatic"|"agent"}``

        Returns immediately with a ``run_id``.  Poll ``GET /api/status``
        or subscribe to ``/ws/events`` for completion.
        """
        pipeline_text = request.get("pipeline", "")
        params = request.get("params", {}) or {}
        engine = request.get("engine", "programmatic")
        if engine not in ("programmatic", "agent"):
            raise APIError("engine must be 'programmatic' or 'agent'", status_code=400)
        logger.debug("POST /api/run: pipeline=%s... params=%s engine=%s", pipeline_text[:80], params, engine)

        if not engine_state.chrome_connected:
            raise APIError("Chrome is not connected — connect first via POST /api/chrome/connect")

        try:
            pipeline_name = _extract_pipeline_name(pipeline_text)
            wm = _get_workspace_manager(pipeline_name)
            wm.ensure_workspace()
            ts = int(time.time())
            snapshot_path = wm.versions_dir / f"snapshot_{ts}.pipeline.yaml"
            snapshot_path.write_text(pipeline_text, encoding="utf-8")

            from compiler.parser import inject_params_to_pipeline
            pipeline_text = inject_params_to_pipeline(pipeline_text, params)

            parsed, steps = _prepare_steps(pipeline_text, snapshot_path)

            if params:
                for step in steps:
                    if step.get("is_goal"):
                        desc = step.get("goal_description", "") or step.get("description", "")
                        extras = " | ".join(f"{k}={v}" for k, v in params.items())
                        step["goal_description"] = f"{desc} (params: {extras})"

            from engine._lifecycle.guardian import (
                create_guardian_from_frontmatter,
                inject_guardian_config_to_steps,
            )
            inject_guardian_config_to_steps(steps, parsed.frontmatter)
            guardian = create_guardian_from_frontmatter(parsed.frontmatter)

            from cdp.helpers import CDPHelpers
            browser = CDPHelpers(engine_state.chrome_daemon)

            # Import run_pipeline with fallback (being written simultaneously)
            try:
                from engine.runner import run_pipeline
            except ImportError:
                raise ServerError(
                    "engine.runner is not yet available — pipeline execution cannot start. "
                    "Ensure engine/runner.py is implemented."
                )

            from engine.agent import create_pipeline_llm_call

            if engine == "agent":
                from engine._harness.conversation_loop import run_preset_loop
                from engine._harness.iteration_budget import IterationBudget
                from engine.state import RunContext

                run_dir = wm.create_run()
                wm.set_status(run_dir, "running")
                ctx = RunContext(
                    pipeline_name=parsed.name,
                    run_id=run_dir.name,
                    run_dir=run_dir,
                    version="0",
                )
                engine_state.running_pipeline = ctx

                llm_call = create_pipeline_llm_call(persist_id=run_dir.name)

                budget = IterationBudget(max_total=50)
                try:
                    result = await run_preset_loop(
                        step_defs=steps,
                        frontmatter=parsed.frontmatter,
                        llm_call=llm_call,
                        cdp_helpers=browser,
                        budget=budget,
                    )
                except Exception:
                    wm.set_status(run_dir, "failed")
                    raise
                finally:
                    engine_state.running_pipeline = None

                if result.interrupted:
                    ctx.errors.append({"step": "_agent_", "code": "AGENT_ERROR", "message": "agent interrupted"})
                    wm.set_status(run_dir, "failed")
                elif result.budget.is_exhausted:
                    pipeline_finished = any(
                        msg.get("role") == "tool" and msg.get("name") == "pipeline_finish"
                        for msg in result.messages
                    )
                    if pipeline_finished:
                        wm.set_status(run_dir, "completed")
                    else:
                        ctx.errors.append({"step": "_agent_", "code": "AGENT_ERROR", "message": "budget exhausted"})
                        wm.set_status(run_dir, "failed")
                else:
                    wm.set_status(run_dir, "completed")
            else:
                llm_call = create_pipeline_llm_call(persist_id=f"pipeline_{parsed.name}")
                ctx = await run_pipeline(
                    pipeline_name=parsed.name,
                    steps=steps,
                    cdp_helpers=browser,
                    pipeline_path=snapshot_path,
                    frontmatter=parsed.frontmatter,
                    guardian=guardian,
                    llm_call=llm_call,
                )

            status = "completed" if not ctx.errors else "failed"
            return JSONResponse({
                "run_id": ctx.run_id,
                "pipeline": ctx.pipeline_name,
                "status": status,
                "step_count": len(steps),
                "errors": ctx.errors,
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

    @app.post("/api/chrome/connect")
    async def api_chrome_connect(request: dict) -> JSONResponse:
        """Connect to Chrome via CDP WebSocket.

        Request body: ``{"mode": "user"|"isolated", "profile_name": "...", "ws_url": "..."}``
        """
        mode = request.get("mode", "user")
        profile_name = request.get("profile_name")
        ws_url = request.get("ws_url")
        logger.info("Chrome connect requested: mode=%s profile=%s", mode, profile_name or "none")

        if engine_state.running_pipeline is not None:
            raise APIError("A pipeline is currently running — cannot connect Chrome", status_code=409)

        try:
            if mode == "isolated" and profile_name:
                from cdp.launcher import launch_isolated_chrome
                ws_url = await launch_isolated_chrome(profile_name=profile_name)
            elif ws_url:
                pass
            else:
                from cdp.discover import discover_ws_url
                ws_url = await discover_ws_url(profile_name=profile_name)

            actual_ws = await engine_state.connect_chrome(ws_url)
            return JSONResponse({"connected": True, "ws_url": actual_ws[:80]})
        except Exception as exc:
            logger.exception("Chrome connect failed")
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

    @app.post("/api/chrome/restart")
    async def api_chrome_restart() -> JSONResponse:
        """Restart the user Chrome browser and reconnect."""
        logger.info("Chrome restart requested")

        if engine_state.running_pipeline is not None:
            raise APIError("A pipeline is currently running", status_code=409)

        try:
            from cdp.launcher import restart_user_chrome

            ws_url = await restart_user_chrome()
            if not ws_url:
                raise RuntimeError("Cannot restart Chrome")

            await engine_state.disconnect_chrome()

            actual_ws = await engine_state.connect_chrome(ws_url)
            return JSONResponse({"connected": True, "ws_url": str(actual_ws)[:80]})
        except Exception as exc:
            logger.exception("Chrome restart failed")
            raise ServerError(str(exc))

    @app.get("/api/chrome/isolated-profiles")
    async def api_list_isolated_profiles() -> JSONResponse:
        """List all isolated Chrome profile directories."""
        from cdp.launcher import _ISO_PROFILES_DIR

        profiles = []
        if _ISO_PROFILES_DIR.exists():
            for entry in sorted(_ISO_PROFILES_DIR.iterdir()):
                if entry.is_dir():
                    profiles.append(entry.name)
        return JSONResponse({"profiles": profiles})

    @app.post("/api/chrome/isolated-profiles/{profile_name}")
    async def api_create_isolated_profile(profile_name: str) -> JSONResponse:
        """Create a new isolated Chrome profile directory."""
        from cdp.launcher import get_isolated_profile_dir

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
            from params.manager import list_param_keys
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
            from params.manager import ParamManager
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
            from params.manager import delete_param, list_param_keys
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
            from workspace.version_manager import VersionManager
            wm = _get_workspace_manager(pipeline_name)
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
            from workspace.version_manager import VersionManager
            wm = _get_workspace_manager(pipeline_name)
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
            from workspace.version_manager import VersionManager
            wm = _get_workspace_manager(pipeline_name)
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

            from workspace.version_manager import VersionManager
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

            from engine._lifecycle.guardian import (
                create_guardian_from_frontmatter,
                inject_guardian_config_to_steps,
            )
            inject_guardian_config_to_steps(steps, parsed.frontmatter)
            guardian = create_guardian_from_frontmatter(parsed.frontmatter)

            ts = int(time.time())
            snapshot_path = wm.versions_dir / f"snapshot_{ts}.pipeline.yaml"
            snapshot_path.write_text(pipeline_text, encoding="utf-8")

            try:
                from engine.runner import run_pipeline
            except ImportError:
                raise ServerError("engine.runner is not yet available")

            from cdp.helpers import CDPHelpers
            browser = CDPHelpers(engine_state.chrome_daemon)

            from engine.agent import create_pipeline_llm_call
            llm_call = create_pipeline_llm_call(persist_id=run_id)

            ctx = await run_pipeline(
                pipeline_name=pipeline_name,
                steps=steps,
                cdp_helpers=browser,
                pipeline_path=snapshot_path,
                frontmatter=parsed.frontmatter,
                resume_from_index=resume_from_index,
                guardian=guardian,
                llm_call=llm_call,
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
        from engine.agent import _create_chat_llm_call

        message = request.get("message", "").strip()
        if not message:
            raise APIError("message is required")

        logger.info("Chat message: %s", message[:120])
        service = await _get_service()

        session = service.get_session()
        if session is None:
            session = service.create_session()
        session_id = session.session_id
        turn_index = (len(session.messages) if session else 0) + 1

        def _push(event: dict) -> None:
            if event.get("type") == "chat.message" and llm_call._streaming_active is not None:
                if llm_call._streaming_active():
                    return
            service._push_event(event)

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

        llm_call = _create_chat_llm_call(
            persist_id=session_id,
            on_stream_start=_on_stream_start,
            on_stream_end=_on_stream_end,
            on_text_delta=_on_text_delta,
            on_reasoning_delta=_on_reasoning_delta,
            on_tool_generated=_on_tool_generated,
        )

        _original_push = service._push_event

        def _filtered_push(event: dict) -> None:
            if event.get("type") == "chat.message" and llm_call._streaming_active():
                return
            _original_push(event)

        service._push_event = _filtered_push

        try:
            from cdp.helpers import CDPHelpers

            browser = CDPHelpers(engine_state.chrome_daemon) if engine_state.chrome_daemon else None

            result = await service.process_chat_message(
                message=message,
                cdp_helpers=browser,
                tools_dir=Path("tools"),
                pipeline_name="chat",
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
        finally:
            service._push_event = _original_push

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
        """Confirm a pipeline edit — delete the checkpoint file.

        Request body: {"edit_id": "..."}

        Idempotent: repeated calls return {"status": "already_confirmed"}.
        """
        edit_id = request.get("edit_id", "").strip()
        if not edit_id:
            return JSONResponse({"status": "error", "error": "edit_id is required"}, status_code=400)

        try:
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

            checkpoint_name = cp.name
            suffix = f".{edit_id}.orig"
            if checkpoint_name.endswith(suffix):
                preset_name = checkpoint_name[:-len(suffix)]
            else:
                preset_name = checkpoint_name.rsplit(".", 1)[0]

            preset_path = cp.parent / preset_name
            preset_path.write_text(original, encoding="utf-8")

            delete_checkpoint(edit_id)
            set_edit_status(edit_id, "reverted")
            logger.info("Edit %s reverted, checkpoint restored to %s", edit_id, preset_path)
            return JSONResponse({"status": "reverted"})
        except Exception as exc:
            logger.exception("Revert edit %s failed", edit_id)
            raise ServerError(str(exc))

    @app.get("/api/session")
    async def get_session() -> JSONResponse:
        """Get the current session state."""
        service = await _get_service()
        session = service.get_session()
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

    # =================================================================
    # PRESET — save/load/list pipeline presets
    # =================================================================

    @app.get("/api/presets")
    async def list_presets() -> JSONResponse:
        """List all saved preset pipelines."""
        service = await _get_service()
        presets = service.list_presets()
        return JSONResponse({"presets": presets})

    @app.post("/api/presets")
    async def save_preset(request: dict) -> JSONResponse:
        """Save a preset (pipeline.yaml format).

        Request: {"name": "my-preset", "content": "..."}
        """
        name = request.get("name", "").strip()
        content = request.get("content", "")
        if not name:
            raise APIError("name is required")
        if not content:
            raise APIError("content is required")

        service = await _get_service()
        path = service.save_preset(name, content)
        return JSONResponse({"ok": True, "path": str(path)})

    @app.delete("/api/presets/{name}")
    async def delete_preset(name: str) -> JSONResponse:
        """Delete a saved preset."""
        import os
        presets_dir = Path(__file__).resolve().parent.parent.parent / "userdata" / "presets"
        path = presets_dir / f"{name}.pipeline.yaml"
        if path.exists():
            os.remove(str(path))
            return JSONResponse({"ok": True})
        raise APIError(f"Preset '{name}' not found", 404)

    @app.post("/api/presets/compile")
    async def compile_preset(request: dict) -> JSONResponse:
        """Compile current session into pipeline.yaml and save as preset.

        Request: {"name": "my-preset"}
        """
        name = request.get("name", "").strip()
        if not name:
            raise APIError("name is required")

        service = await _get_service()
        session = service.get_session()
        if session is None:
            raise APIError("No active session to compile")

        pipeline_text = service.compile_session_to_preset(session)
        path = service.save_preset(name, pipeline_text)
        return JSONResponse({"ok": True, "path": str(path), "content": pipeline_text})

    # =================================================================
    # PIPELINES — list all workspace pipelines
    # =================================================================

    @app.get("/api/pipelines")
    async def api_list_pipelines() -> JSONResponse:
        """List all workspace pipelines."""
        workspaces_dir = Path(__file__).resolve().parent.parent.parent / "userdata" / "workspaces"
        pipelines = []
        if workspaces_dir.exists():
            for d in sorted(workspaces_dir.iterdir()):
                if not d.is_dir() or d.name.startswith("."):
                    continue
                pipe_yaml = d / "pipeline.yaml"
                if pipe_yaml.exists():
                    pipelines.append({"name": d.name, "title": d.name})
        return JSONResponse({"pipelines": pipelines})

    @app.get("/api/pipelines/{name}")
    async def api_get_pipeline(name: str) -> JSONResponse:
        """Get a specific pipeline's content."""
        pipe_path = Path(__file__).resolve().parent.parent.parent / "userdata" / "workspaces" / name / "pipeline.yaml"
        if not pipe_path.exists():
            raise APIError("pipeline not found", status_code=404)
        content = pipe_path.read_text(encoding="utf-8")
        return JSONResponse({"name": name, "content": content})

    # =================================================================
    # WEB SOCKET — real-time event stream
    # =================================================================

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        """WebSocket endpoint for real-time pipeline event streaming.

        Each connected client receives event dicts as JSON text messages.
        """
        await websocket.accept()
        q: asyncio.Queue = asyncio.Queue()
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


# ── Internal helpers ────────────────────────────────────────────────


async def _get_service() -> Any:
    """Return the singleton Service instance, creating it if needed."""
    from api.service import Service

    async with engine_state._service_lock:
        if engine_state._service is None:
            engine_state._service = Service(engine_state)
        return engine_state._service


def _get_workspace_manager(pipeline_name: str) -> Any:
    """Return a WorkspaceManager for *pipeline_name*."""
    from workspace.manager import WorkspaceManager
    return WorkspaceManager(pipeline_name)


def _prepare_steps(content: str, pipeline_path: Path) -> tuple[Any, list[dict]]:
    """Parse pipeline.yaml and prepare ordered steps.

    Returns (parsed_frontmatter_plus, steps_data).
    """
    from compiler.context import resolve_context
    from compiler.graph import build_graph, get_execution_order, validate_file_refs
    from compiler.parser import parse_pipeline
    from compiler.resolver import resolve

    parsed = parse_pipeline(content)
    context = resolve_context(parsed.frontmatter, pipeline_path)
    if context:
        for step in parsed.steps:
            step.system_prompt = context

    dag = build_graph(parsed.steps)
    validate_file_refs(parsed.steps)
    execution_order = get_execution_order(dag)

    step_key_map = {s.key: s for s in parsed.steps}
    ordered_steps = [step_key_map[k] for k in execution_order]

    steps_data: list[dict] = []
    for step in ordered_steps:
        handler = resolve(step, parsed.name)
        step_data = step.to_runtime_dict(handler)
        steps_data.append(step_data)

    logger.info(
        "Prepared %d steps for pipeline '%s'",
        len(steps_data), parsed.name,
    )
    return parsed, steps_data
