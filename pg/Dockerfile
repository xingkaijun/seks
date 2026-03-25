FROM pgvector/pgvector:pg16

# Install pg_jieba for Chinese Full-Text Search
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential cmake git \
      postgresql-server-dev-16 && \
    git clone --depth 1 https://github.com/jaiminpan/pg_jieba.git /tmp/pg_jieba && \
    cd /tmp/pg_jieba && git submodule update --init && \
    mkdir build && cd build && cmake .. && make && make install && \
    apt-get remove -y build-essential cmake git postgresql-server-dev-16 && \
    apt-get autoremove -y && rm -rf /var/lib/apt/lists/* /tmp/pg_jieba
