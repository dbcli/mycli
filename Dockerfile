FROM python:3.14

RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends --no-install-suggests -qq \
    fzf \
    && \
    apt-get clean autoclean && \
    apt-get autoremove --yes && \
    rm -rf /var/lib/{apt,dpkg,cache,log}/

COPY . /app

RUN cd /app && pip install -e .[llm,dataframe]

CMD ["mycli", "--help"]
