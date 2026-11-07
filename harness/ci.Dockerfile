# CI（ubuntu・Python 3.12・chromium）と同じ環境を手元に。harness/ci_local.sh が使う
FROM python:3.12-bookworm
COPY requirements.txt /tmp/requirements.txt
RUN apt-get update -qq && apt-get install -y -qq git nodejs fonts-noto-cjk >/dev/null \
 && pip install -q -r /tmp/requirements.txt playwright \
 && playwright install --with-deps chromium
