FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive WINEDEBUG=-all WINEPREFIX=/wine WINEARCH=win64
# CPython's amd64 installer has a 32-bit Burn bootstrapper; Wine needs both architectures.
RUN dpkg --add-architecture i386 && apt-get update && apt-get install -y --no-install-recommends \
    wine wine64 wine32:i386 xvfb curl ca-certificates cabextract unzip && \
    rm -rf /var/lib/apt/lists/*
RUN mkdir -p /wine /build && \
    curl -fL --retry 3 -o /tmp/python.exe https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
# Build invoked via build-windows.sh; Wine prefix and Python provisioned there.
WORKDIR /work
