"""
e2e_driver.py — drive the full signup -> upload -> ask flow against a running backend.

Usage:
    .venv\\Scripts\\python.exe scripts\\e2e_driver.py \\
        --file "..\\Chapter1_HRM_With_Cartoons_Icons_and_Video.pptx" \\
        --base http://localhost:8000 \\
        --out logs/e2e_report.json

Emits a JSON report with all ids, per-stage timings, final answer and sources.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

import httpx

DEFAULT_QUESTION = (
    "Based on the diagrams and figures in this chapter, what are the core HRM "
    "functions being illustrated, and how do the visuals tie together with the "
    "textual explanations of strategic HR planning?"
)


def step(label: str, fn, *a, **kw) -> tuple[Any, float]:
    t0 = time.monotonic()
    r = fn(*a, **kw)
    dt = time.monotonic() - t0
    print(f"[{label}] {dt*1000:.0f}ms")
    return r, dt


def must_ok(resp: httpx.Response, what: str) -> dict:
    if resp.status_code >= 400:
        raise RuntimeError(
            f"{what} failed: HTTP {resp.status_code} body={resp.text[:500]}"
        )
    try:
        return resp.json()
    except Exception:
        raise RuntimeError(f"{what} returned non-JSON: {resp.text[:500]}")


def run(base: str, file_path: str, question: str, poll_budget_s: int,
        out_path: str) -> int:
    epoch = int(time.time())
    username = f"e2e_{epoch}"
    email    = f"{username}@example.com"
    password = "PassE2e123!"
    report: dict[str, Any] = {
        "started_at": epoch,
        "base": base,
        "file": os.path.abspath(file_path),
        "credentials": {"username": username, "email": email},
    }

    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    with httpx.Client(base_url=base, timeout=60) as c:
        # 1. Signup
        r, dt = step("signup", c.post, "/auth/signup", json={
            "username": username, "email": email, "password": password,
        })
        user = must_ok(r, "signup")
        report["user"] = {"id": user.get("id"), "email": user.get("email")}
        report["t_signup_s"] = dt

        # 2. Login
        r, dt = step("login", c.post, "/auth/login", json={
            "email": email, "password": password,
        })
        login = must_ok(r, "login")
        token = login["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        report["t_login_s"] = dt

        # 3. Create classroom
        r, dt = step("classroom", c.post, "/classrooms/create", json={
            "name": f"E2E Run {epoch}",
            "description": "Automated end-to-end test classroom",
        }, headers=auth)
        classroom = must_ok(r, "create classroom")
        classroom_id = classroom["id"]
        report["classroom"] = {"id": classroom_id, "code": classroom.get("code")}
        report["t_classroom_s"] = dt

        # 4. Create folder
        r, dt = step("folder", c.post, f"/folders/classroom/{classroom_id}",
                     json={"name": "Test Folder"}, headers=auth)
        folder = must_ok(r, "create folder")
        folder_id = folder["id"]
        report["folder"] = {"id": folder_id}
        report["t_folder_s"] = dt

        # 5. Upload file
        with open(file_path, "rb") as fh:
            files = {
                "file": (
                    os.path.basename(file_path),
                    fh,
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )
            }
            t_upload_start = time.monotonic()
            r = c.post(f"/files/upload/{folder_id}", files=files, headers=auth)
            t_upload_dt = time.monotonic() - t_upload_start
        print(f"[upload] {t_upload_dt*1000:.0f}ms")
        up = must_ok(r, "upload")
        file_id = up["id"]
        report["file"] = {
            "id": file_id,
            "filename": up.get("filename"),
            "file_url": up.get("file_url"),
            "initial_status": up.get("processing_status"),
        }
        report["t_upload_s"] = t_upload_dt

        # 6. Poll status until COMPLETED or budget exhausted
        print(f"[poll] polling /files/{file_id}/status every 2s, budget={poll_budget_s}s")
        t_poll_start = time.monotonic()
        last_status = None
        final_status: dict | None = None
        while True:
            elapsed = time.monotonic() - t_poll_start
            if elapsed > poll_budget_s:
                print(f"[poll] TIMEOUT after {elapsed:.1f}s, last_status={last_status}")
                break
            rr = c.get(f"/files/{file_id}/status", headers=auth)
            if rr.status_code >= 400:
                print(f"[poll] HTTP {rr.status_code}: {rr.text[:200]}")
                time.sleep(2)
                continue
            js = rr.json()
            s = (js.get("status") or "").lower()
            if s != last_status:
                print(f"[poll] t={elapsed:5.1f}s status={s}")
                last_status = s
            if s in ("completed", "failed"):
                final_status = js
                break
            time.sleep(2)

        report["t_processing_s"] = time.monotonic() - t_poll_start
        report["final_status"] = final_status
        if not final_status or final_status.get("status", "").lower() != "completed":
            print(f"[poll] did not reach COMPLETED — aborting retrieval.")
            _write(out_path, report)
            return 2

        # 7. Ask the retrieval question
        r, dt = step("ask", c.post, f"/chat/files/{file_id}/ask",
                     json={"question": question}, headers=auth,
                     timeout=180)
        ask = must_ok(r, "ask")
        report["question"] = question
        report["answer"] = ask.get("answer")
        report["sources"] = ask.get("sources")
        report["chunks_used"] = ask.get("chunks_used")
        report["confidence"] = ask.get("confidence")
        report["message_id"] = ask.get("message_id")
        report["t_ask_s"] = dt

    _write(out_path, report)
    print("\n=== E2E SUMMARY ===")
    print(f"processing_time_s = {report['t_processing_s']:.1f}")
    print(f"ask_time_s        = {report['t_ask_s']:.1f}")
    print(f"classroom_id      = {classroom_id}")
    print(f"folder_id         = {folder_id}")
    print(f"file_id           = {file_id}")
    print(f"answer (first 400): {(report.get('answer') or '')[:400]}")
    print(f"sources: {report.get('sources')}")
    return 0


def _write(path: str, report: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"[report] written to {path}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True, help="pptx file path (absolute or relative)")
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--question", default=DEFAULT_QUESTION)
    p.add_argument("--poll-budget", type=int, default=600)
    p.add_argument("--out", default="logs/e2e_report.json")
    args = p.parse_args()
    return run(args.base, args.file, args.question, args.poll_budget, args.out)


if __name__ == "__main__":
    sys.exit(main())
