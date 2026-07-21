FROM python:3.12-slim

WORKDIR /app
COPY monitor.py /app/monitor.py

# No external dependencies. Run as an unprivileged user.
USER nobody

EXPOSE 8080
ENTRYPOINT ["python", "-u", "/app/monitor.py"]
