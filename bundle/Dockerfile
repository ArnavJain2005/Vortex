# Vortex, Samsung PRISM XR Hackathon 2026, Track 3. Python only (organisers' FAQ, 17 Nov 2026).
#   docker build -t vortex .
#   docker run --rm -v "<folder with the csv>:/data" -w /data vortex            (searches /data, writes estimated_trajectory.txt there)
#   docker run --rm -v "<folder with the csv>:/data" vortex /data/data.csv /data/estimated_trajectory.txt
# src/main.py is one self-contained file using the standard library only: nothing is installed, no bytecode ships.
FROM python:3.12.7-slim-bookworm
COPY src/main.py /app/main.py
ENTRYPOINT ["python", "-S", "/app/main.py"]
