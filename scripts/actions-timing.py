#!/usr/bin/env python3
"""用 gh 留存 Actions 基线，区分依赖等待、runner 排队、准备和实际执行。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True)


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def seconds(start, end):
    return max(0, (stamp(end) - stamp(start)).total_seconds()) if start and end else 0


def execution_step(name):
    return bool(re.search(r"^(Run |Build |Build\+|Verify |Validate |Create |Compute |Generate |Publish |Upload |Delete |Export |Get |Resolve |Patch |Import |Clean |Collect )", name))


def job_row(run, job, log):
    created = job.get("created_at") or run["createdAt"]
    start, end = job.get("started_at"), job.get("completed_at")
    elapsed = seconds(start, end)
    execution = compilation = 0
    # gh run view --log prefixes every line with job name, step name and timestamp.
    lines = []
    for line in log.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4 and parts[0] == job["name"]:
            lines.append((parts[2], parts[3]))
    for step in job.get("steps", []):
        if step.get("conclusion") == "skipped" or not execution_step(step["name"]):
            continue
        lo, hi = step.get("started_at"), step.get("completed_at")
        duration = seconds(lo, hi)
        compile_seconds = 0
        # Cargo's Finished line is emitted before test/scenario execution. Compilation
        # belongs to preparation even when it happens inside a step named Run tests.
        if "test" in step["name"].lower() and lo and hi:
            for ts, message in lines:
                if lo <= ts[:19] + "Z" <= hi and re.search(r"Finished.*(?:test|dev).*target\(s\)", message):
                    compile_seconds = min(duration, seconds(lo, ts))
                    break
        compilation += compile_seconds
        execution += duration - compile_seconds
    return {
        "run_id": run["databaseId"], "workflow": run["workflowName"],
        "commit": run["headSha"], "job_id": job["id"], "job": job["name"],
        "conclusion": job.get("conclusion"), "runner": job.get("runner_name"),
        "dependency_wait_s": seconds(run["createdAt"], created),
        "queue_s": seconds(created, start), "prepare_s": round(max(0, elapsed-execution), 3),
        "compile_in_prepare_s": round(compilation, 3),
        "execute_s": round(execution, 3), "job_elapsed_s": elapsed,
        "log_available": bool(log), "url": run["url"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="Voice-Wise/release")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--run", action="append", type=int, default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    fields = "databaseId,workflowName,event,status,conclusion,headBranch,headSha,createdAt,startedAt,updatedAt,url"
    index = args.output / "runs.json"
    if index.exists():
        runs = json.loads(index.read_text())
    elif args.run:
        runs = [json.loads(gh("run", "view", str(run), "--repo", args.repo, "--json", fields)) for run in args.run]
    else:
        runs = json.loads(gh("run", "list", "--repo", args.repo, "--limit", str(args.limit), "--json", fields))
    index.write_text(json.dumps(runs, indent=2) + "\n")

    def collect(run):
        run_id = run["databaseId"]
        jobs_file, log_file = args.output / f"{run_id}.json", args.output / f"{run_id}.log"
        if not jobs_file.exists():
            pages = json.loads(gh("api", "--paginate", "--slurp", f"repos/{args.repo}/actions/runs/{run_id}/jobs?per_page=100"))
            jobs_file.write_text(json.dumps({"jobs": [j for page in pages for j in page["jobs"]]}))
        if not log_file.exists():
            result = subprocess.run(["gh", "run", "view", str(run_id), "--repo", args.repo, "--log"], text=True, capture_output=True)
            if result.returncode == 0:
                log_file.write_text(result.stdout)
            else:
                print(f"{run_id}: 日志不可用，测试步骤含编译；{result.stderr.strip()}", flush=True)
        log = log_file.read_text() if log_file.exists() else ""
        return [job_row(run, job, log) for job in json.loads(jobs_file.read_text())["jobs"]]

    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = [row for group in pool.map(collect, runs) for row in group]
    if rows:
        with (args.output / "jobs.csv").open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(f"已采集 {len(runs)} 次运行、{len(rows)} 个 job：{args.output / 'jobs.csv'}")


if __name__ == "__main__":
    main()
