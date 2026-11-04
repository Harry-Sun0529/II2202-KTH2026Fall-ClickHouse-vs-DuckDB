# One image for the DuckDB engine container and for the benchmark driver.
# The engine container runs scripts/duck_server.py under the 8 GiB / 4 core limits;
# the driver container runs scripts/bench.py without limits on the other cores.
FROM python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
RUN pip install --no-cache-dir duckdb==2.0.0 psutil==7.2.2 pyyaml==6.0.3 docker==7.2.0
# Bake the tpch extension into the image so runs do not depend on the network.
RUN python -c "import duckdb; c=duckdb.connect(); c.sql('INSTALL tpch'); c.sql('LOAD tpch'); print(duckdb.__version__)"
WORKDIR /work
