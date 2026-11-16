# Vortex, Samsung PRISM XR Hackathon 2026, Track 3 (repository layout; the zip carries bundle/Dockerfile).
#   docker build -t vortex .
#   docker run --rm -v "<folder with the csv>:/data" vortex /data/data.csv /data/estimated_trajectory.txt
# The entry point is the C core (peak RSS within 8 MB). The Python entry point gives the same output:
#   docker run --rm -v "<folder>:/data" --entrypoint python vortex -S /app/main.py /data/data.csv /data/out.txt
FROM python:3.12.7-slim-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends g++ && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY main.cpp ./
RUN g++ -O2 -std=c++17 -ffp-contract=off -o vortex main.cpp

FROM python:3.12.7-slim-bookworm
WORKDIR /app
COPY main.py pathfinder.py ./
# Compile the Python estimator once, so its runs load bytecode instead of compiling the source.
RUN python -c "import py_compile as p; p.compile('pathfinder.py', doraise=True, invalidation_mode=p.PycInvalidationMode.CHECKED_HASH)"
COPY --from=build /src/vortex ./vortex
ENTRYPOINT ["/app/vortex"]
