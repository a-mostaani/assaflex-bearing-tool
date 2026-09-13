# Build/run from the REPO ROOT (not this directory), since the app imports
# the sibling bearing_tool package:
#   docker build -f webapp/Dockerfile -t assaflex-bearing-webapp .
#   docker run -p 8000:8000 --env-file webapp/.env assaflex-bearing-webapp
#
# Railway (and most container platforms) inject a $PORT env var and expect
# the app to bind to it rather than a fixed port -- the shell-form CMD below
# picks that up, falling back to 8000 for local `docker run` where $PORT
# isn't set.
FROM python:3.11-slim

WORKDIR /app
COPY bearing_tool/ ./bearing_tool/
COPY webapp/ ./webapp/

RUN pip install --no-cache-dir -r webapp/requirements.txt

EXPOSE 8000
CMD uvicorn webapp.main:app --host 0.0.0.0 --port ${PORT:-8000}
