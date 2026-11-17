# Vortex, Samsung PRISM XR Hackathon 2026, Track 3. Python only (organisers' FAQ, 17 Nov 2026). Zip layout: sources in src/.
#   docker build -t vortex .
#   docker run --rm -v "<folder with the csv>:/data" vortex /data/data.csv /data/estimated_trajectory.txt
# main.py and pathfinder.py use the standard library only: nothing is installed.
FROM python:3.12.7-slim-bookworm
WORKDIR /app
COPY src/main.py src/pathfinder.py ./
# Compile the estimator once, so each run loads bytecode instead of compiling the source.
RUN python -c "import py_compile as p; p.compile('pathfinder.py', doraise=True, invalidation_mode=p.PycInvalidationMode.CHECKED_HASH)"
ENTRYPOINT ["python", "-S", "/app/main.py"]
