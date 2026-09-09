FROM python:3.14

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends --no-install-suggests -qq \
    fzf \
    mariadb-server \
    && \
    apt-get clean autoclean && \
    apt-get autoremove --yes && \
    rm -rf /var/lib/{apt,dpkg,cache,log}/

COPY . /app

RUN service mariadb restart && \
    cd /app/docker/resources && \
    gunzip -c test_db-1.0.7.tar.gz | tar -xf - && \
    cd test_db && \
    mariadb < employees.sql && \
    cd .. && \
    rm -r -- ./test_db

RUN cd /app && pip install --root-user-action=ignore -e .[llm,dataframe]

CMD ["sh", "-c", "service mariadb start && mycli --database employees"]
