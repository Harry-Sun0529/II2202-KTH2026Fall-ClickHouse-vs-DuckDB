"""Stage 0: record the environment and check the plan's minimum requirements.

Writes results/env.json. Exits non-zero if gate 0 fails.
Only the standard library is used so that this runs before any setup.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GIB = 1024 ** 3

MIN_DISK_GB = 30
MIN_DOCKER_MEM_GIB = 10
MIN_HOST_CORES = 6
EXPECTED_MEMORY_MAX = 8 * GIB  # 8589934592


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def host_info() -> dict:
    info = {
        "os": f"{platform.system()} {platform.release()}",
        "os_version": platform.mac_ver()[0] or platform.version(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }
    if platform.system() == "Darwin":
        info["cpu_model"] = run(["sysctl", "-n", "machdep.cpu.brand_string"])
        info["cpu_cores"] = int(run(["sysctl", "-n", "hw.ncpu"]))
        info["cpu_perf_cores"] = int(run(["sysctl", "-n", "hw.perflevel0.physicalcpu"]))
        info["cpu_eff_cores"] = int(run(["sysctl", "-n", "hw.perflevel1.physicalcpu"]))
        info["mem_total_bytes"] = int(run(["sysctl", "-n", "hw.memsize"]))
    else:
        info["cpu_model"] = platform.processor()
        info["cpu_cores"] = os.cpu_count()
        info["mem_total_bytes"] = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    info["disk_free_bytes"] = shutil.disk_usage(ROOT).free
    return info


def docker_info() -> dict:
    fmt = (
        '{"server_version":"{{.ServerVersion}}","vm_mem_total_bytes":{{.MemTotal}},'
        '"vm_ncpu":{{.NCPU}},"kernel":"{{.KernelVersion}}","os":"{{.OperatingSystem}}",'
        '"cgroup_version":"{{.CgroupVersion}}","storage_driver":"{{.Driver}}"}'
    )
    info = json.loads(run(["docker", "info", "--format", fmt]))
    info["client_version"] = run(["docker", "version", "--format", "{{.Client.Version}}"])
    # Docker Desktop's configured VM memory (the kernel sees slightly less).
    settings = Path.home() / "Library/Group Containers/group.com.docker/settings-store.json"
    if settings.exists():
        s = json.loads(settings.read_text())
        info["desktop_memory_mib"] = s.get("MemoryMiB")
        info["desktop_cpus"] = s.get("Cpus")
    # Free space inside the Docker VM, where engine storage lives.
    df = run(["docker", "run", "--rm", "alpine", "df", "-B1", "/"]).splitlines()[-1].split()
    info["vm_disk_free_bytes"] = int(df[3])
    return info


def gate0_cgroup() -> dict:
    out = run([
        "docker", "run", "--rm", "--memory=8g", "--memory-swap=8g", "--cpus=4", "alpine",
        "sh", "-c", "cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/cpu.max /sys/fs/cgroup/memory.swap.max",
    ]).splitlines()
    return {"memory_max": int(out[0]), "cpu_max": out[1], "memory_swap_max": out[2]}


def main() -> int:
    env = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": host_info(),
        "docker": docker_info(),
        "gate0": gate0_cgroup(),
    }
    h, d, g = env["host"], env["docker"], env["gate0"]
    docker_mem_gib = (d.get("desktop_memory_mib") or d["vm_mem_total_bytes"] / 2**20) / 1024
    checks = {
        "disk_free_ge_30GB": min(h["disk_free_bytes"], d["vm_disk_free_bytes"]) >= MIN_DISK_GB * 1e9,
        "docker_mem_ge_10GiB": docker_mem_gib >= MIN_DOCKER_MEM_GIB,
        "host_cores_ge_6": h["cpu_cores"] >= MIN_HOST_CORES,
        "python_ge_3_10": sys.version_info >= (3, 10),
        "cgroup_memory_max_is_8GiB": g["memory_max"] == EXPECTED_MEMORY_MAX,
        "cgroup_cpu_max_is_4_cores": g["cpu_max"] == "400000 100000",
        "cgroup_no_swap": g["memory_swap_max"] == "0",
    }
    env["checks"] = checks
    env["fallback"] = {
        "sf_large": 10 if checks["disk_free_ge_30GB"] and checks["docker_mem_ge_10GiB"] else 3,
        "cores": 4 if checks["host_cores_ge_6"] else 2,
    }
    out = ROOT / "results" / "env.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(env, indent=2) + "\n")
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'}  {k}")
    print(f"fallback: {env['fallback']}  -> {out.relative_to(ROOT)}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
