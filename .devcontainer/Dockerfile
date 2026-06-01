FROM mcr.microsoft.com/devcontainers/python:1-3.11-bullseye

# 必要な基本ツールのインストール
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends curl git

# Pythonデータ分析用ライブラリのインストール
RUN pip --no-cache-dir install \
    pandas \
    openpyxl \
    requests \
    beautifulsoup4 \
    lxml