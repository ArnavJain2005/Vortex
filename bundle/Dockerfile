# Vortex, Samsung PRISM XR Hackathon 2026, Track 3. Standard library only: nothing is installed.
#   docker build -t vortex .
#   docker run --rm -v "<folder with the csv>:/data" vortex /data/data.csv /data/estimated_trajectory.txt
FROM python:3.12.7-slim-bookworm
WORKDIR /app
COPY main.py pathfinder.py ./
# Compile the estimator once at build time, so each run loads bytecode instead of compiling the source.
RUN python -c "import py_compile as p; p.compile('pathfinder.py', doraise=True, invalidation_mode=p.PycInvalidationMode.CHECKED_HASH)"
ENTRYPOINT ["python", "-S", "main.py"]
