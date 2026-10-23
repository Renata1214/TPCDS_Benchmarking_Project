FROM debian:bookworm-slim

ARG DUCKDB_VERSION=1.4.3
ARG TARGETARCH

ENV DEBIAN_FRONTEND=noninteractive
ENV DSDGEN_BIN=/usr/local/bin/dsdgen
ENV DSQGEN_BIN=/usr/local/bin/dsqgen

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        bison \
        build-essential \
        ca-certificates \
        coreutils \
        curl \
        flex \
        gawk \
        grep \
        python3 \
        time \
        unzip \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "$TARGETARCH" in \
        amd64) duckdb_arch=amd64 ;; \
        arm64) duckdb_arch=arm64 ;; \
        *) echo "Unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/duckdb/duckdb/releases/download/v${DUCKDB_VERSION}/duckdb_cli-linux-${duckdb_arch}.zip" -o /tmp/duckdb.zip; \
    unzip -q /tmp/duckdb.zip -d /tmp/duckdb; \
    install -m 0755 /tmp/duckdb/duckdb /usr/local/bin/duckdb; \
    rm -rf /tmp/duckdb /tmp/duckdb.zip

COPY Kit/DSGen-software-code-4.0.0/tools/ /opt/tpcds-tools/
RUN make -C /opt/tpcds-tools -f Makefile.suite clean \
    && make -C /opt/tpcds-tools -f Makefile.suite \
        CFLAGS="-D_FILE_OFFSET_BITS=64 -D_LARGEFILE_SOURCE -DYYDEBUG -DLINUX -g -Wall -fcommon" \
        dsdgen dsqgen \
    && install -m 0755 /opt/tpcds-tools/dsdgen /usr/local/bin/dsdgen \
    && install -m 0755 /opt/tpcds-tools/dsqgen /usr/local/bin/dsqgen

COPY docker-entrypoint.sh /usr/local/bin/tpcds-entrypoint
RUN chmod 0755 /usr/local/bin/tpcds-entrypoint

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/tpcds-entrypoint"]
CMD ["bash", "scripts/run_tpcds.sh"]
