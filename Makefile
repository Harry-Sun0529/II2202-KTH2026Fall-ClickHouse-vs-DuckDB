# One command per stage; `make all` reruns everything from scratch.
SHELL := /bin/bash
PWD := $(shell pwd)
IMG := ii2202/duckdb-bench:2.0.0
PY := .venv/bin/python
DRIVER := docker run --rm --privileged --cgroupns=host --network ii2202-net \
	--cpuset-cpus=4-7 -v /var/run/docker.sock:/var/run/docker.sock \
	-v $(PWD):/work -e HOST_REPO=$(PWD) -w /work -v ii2202-parquet:/data $(IMG)

.PHONY: all env image infra data verify load bench check analyze test figures report venv clean-engines

all: env image data verify load bench check analyze report

env:            ## stage 0: preflight, writes results/env.json
	python3 scripts/preflight.py

image:          ## build the DuckDB/driver image and pull ClickHouse
	docker build -t $(IMG) docker/duckdb
	docker pull clickhouse/clickhouse-server:26.8.36.3

infra:
	docker network inspect ii2202-net >/dev/null 2>&1 || docker network create ii2202-net
	for v in ii2202-parquet ii2202-ch-data ii2202-duck-data; do docker volume inspect $$v >/dev/null 2>&1 || docker volume create $$v; done

data: infra     ## stage 1: TPC-H Parquet for SF1 and SF10
	$(DRIVER) python scripts/gen_data.py

verify: infra   ## stage 1 gate: query results vs reference answers and across engines
	$(DRIVER) python scripts/verify.py

load: infra     ## stage 2: 3 timed loads per engine and SF
	$(DRIVER) python scripts/load.py

bench: infra    ## stage 2: 1 cold + 20 warm runs per engine x SF x query
	$(DRIVER) python scripts/bench.py

check:          ## stage 2 gate: completeness and sanity of the raw CSVs
	$(PY) scripts/check_runs.py

venv:
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements-analysis.txt

analyze: venv   ## stage 3: statistics, figures, tests
	$(PY) -m pytest -q analysis/tests
	$(PY) analysis/eda.py
	$(PY) analysis/figures.py
	$(PY) analysis/check_figures.py

report:         ## stage 4: LaTeX in the texlive container, then gates
	$(MAKE) -C report

clean-engines:
	-docker rm -f ii2202-clickhouse ii2202-duckdb
