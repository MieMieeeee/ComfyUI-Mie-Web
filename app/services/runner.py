"""Run a render and keep track of it.

A job is a prompt submitted to ComfyUI. The web app does not wait for
it - ComfyUI owns the queue - so the job table here records what was
submitted and the status comes from ComfyUI's own history.

The queue is shared: a person submitting at 8188 and this app submitting
do not exclude each other. The plan's R21/R22 say the product layer
needs its own lock around "look at /queue + submit", and it must NOT be
held while waiting for an LLM. Here the lock only guards the submit
call itself.
"""

from __future__ import annotations

import json
import threading
import time
import uuid

from app import config
from app.services import comfy, library, workflow

#: The submit lock. It covers "look at the queue, then submit" - the
#: window in which two submissions could interleave.
_submit_lock = threading.Lock()

#: The jobs this process has started: {job_id: record}.
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _now() -> float:
    return time.time()


def submit(script_name: str, role_assets: dict[str, str], run_name: str = "",
           width: int = 960, height: int = 544, steps: int = 20,
           duration: int = 18) -> dict:
    """Build the workflow for a script and queue it.

    Returns the job record. The render itself takes minutes; the caller
    polls :func:`job`.
    """
    script = library.get_storyboard(script_name)
    graph = workflow.build(
        script_name, script["json"], role_assets, run_name=run_name,
        width=width, height=height, steps=steps, duration=duration)

    client_id = "mie-web-%s" % uuid.uuid4().hex[:12]
    with _submit_lock:
        result = comfy.submit(graph, client_id=client_id)

    record = {
        "job_id": result.get("prompt_id"),
        "number": result.get("number"),
        "script": script_name,
        "run_name": run_name or ("sb_web_%s" % script_name[:24]),
        "role_assets": role_assets,
        "submitted_at": _now(),
        "status": "queued",
        "error": "",
        "nodes": len(graph),
    }
    with _jobs_lock:
        _jobs[record["job_id"]] = record
    return record


def job(job_id: str) -> dict:
    """One job, with its current state read from ComfyUI."""
    with _jobs_lock:
        record = _jobs.get(job_id)
    if record is None:
        return {"job_id": job_id, "status": "unknown"}
    record = dict(record)
    entry = comfy.history(job_id)
    if not entry:
        record["status"] = "running"
        return record
    status = entry.get("status", {})
    record["status"] = status.get("status_str", "success")
    for message in status.get("messages") or []:
        if message[0] == "execution_error":
            record["status"] = "error"
            record["error"] = message[1].get("exception_message", "")
    outputs = entry.get("outputs") or {}
    texts = {}
    for node_id, node_out in outputs.items():
        pieces = node_out.get("text") or []
        if pieces:
            texts[node_id] = "".join(
                p if isinstance(p, str) else str(p) for p in pieces)
    record["texts"] = texts
    record["artifacts"] = comfy.collect_artifacts(record["run_name"])
    for node_out in outputs.values():
        if node_out.get("images"):
            record["artifacts"] = record.get("artifacts", []) + [
                {"name": image.get("filename", ""),
                 "relpath": "%s/%s" % (image.get("subfolder", ""),
                                       image.get("filename", "")),
                 "kind": "video" if image.get("type") == "output" else "image",
                 "size": 0}
                for image in node_out["images"]
            ]
    return record


def jobs() -> list[dict]:
    """Every job this process has started, newest first."""
    with _jobs_lock:
        records = list(_jobs.values())
    records.sort(key=lambda r: r.get("submitted_at", 0), reverse=True)
    return [job(r["job_id"]) for r in records]


def plan_preview(script_name: str, role_assets: dict[str, str]) -> dict:
    """The plan a run WOULD use, without running anything.

    The plan is assembled by the same builder the render uses, so what the
    preview shows is what the render will do.
    """
    script = library.get_storyboard(script_name)
    graph = workflow.build(
        script_name, script["json"], role_assets, run_name="preview")
    plan_node = next(
        (n for n in graph.values()
         if n["class_type"].endswith("ChainPlanModern|MieH3")), None)
    literal = plan_node["inputs"]["plan_json"] if plan_node else "{}"
    return {
        "script": script_name,
        "roles": workflow.script_roles(script["json"]),
        "fallback_plan": literal,
        "preview": script["preview"],
        "requirements": script["requirements"],
        "nodes": len(graph),
    }
