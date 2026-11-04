# 01 Preflight and gate 0

Type: task
Status: resolved
Blocked by: -

## Question

Does this machine meet the plan's minimums (disk >= 30 GB, Docker VM >= 10 GiB, >= 6 cores, Python >= 3.10)? Write results/env.json and pass gate 0 (docker cgroup memory.max = 8589934592). Which fallback (SF3 / 2 cores), if any, applies?

## Answer

Host: Apple M1 Pro (6P+2E = 8 cores), 16 GiB, macOS 15.7.9, 141 GB free. Docker Desktop 29.0.1, VM memory raised by the user from 7.65 GiB to 10240 MiB (kernel sees 9.70 GiB), 8 vCPUs, kernel 6.12.54-linuxkit, cgroup v2. Gate 0 passed: memory.max = 8589934592, cpu.max = 400000 100000, memory.swap.max = 0. All checks pass, so no fallback: SF1 + SF10 at 8 GiB / 4 cores. Facts for later tickets: kernel 6.12 supports resetting memory.peak by writing to it. Evidence: results/env.json.

## Comments
