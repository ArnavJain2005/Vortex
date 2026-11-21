# Vortex, Samsung PRISM XR Hackathon 2026, Track 3. Python only (organisers' FAQ, 17 Nov 2026).
#   docker build -t vortex .
#   docker run --rm -v "<folder with the csv>:/data" -w /data vortex            (searches /data, writes estimated_trajectory.txt there)
#   docker run --rm -v "<folder with the csv>:/data" vortex /data/data.csv /data/estimated_trajectory.txt
# The image runs the SAME single self-contained src/main.py the submission zip ships: stage 1 generates it from
# pathfinder.py with tools/make_bundle.py (standard library only); stage 2 holds that one file and nothing else.
# No bytecode ships (submission ledger A1/B7); nothing is installed.
FROM python:3.12.7-slim-bookworm AS build
WORKDIR /build
COPY pathfinder.py ./
COPY tools/make_bundle.py tools/
RUN python tools/make_bundle.py single --out /build/src/main.py

FROM python:3.12.7-slim-bookworm
COPY --from=build /build/src/main.py /app/main.py
ENTRYPOINT ["python", "-S", "/app/main.py"]
