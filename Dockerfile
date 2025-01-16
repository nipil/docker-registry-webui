FROM debian:bookworm-slim

# no-op : for information only
EXPOSE 8000

# mandatory configuration: set to a mounted volume for data
ENV REGISTRY_DIR=""

# optional configuration : networking and exposure
ENV APP_LISTEN_ADDR="0.0.0.0"
ENV APP_LISTEN_PORT="8000"

# minor configuration : for building and later reference)
ENV APP_DIR="/opt/docker-registry-webapp/webapp"
ENV APP_MODULE="main"
ENV APP_ATTRIBUTE="app"

# development configuration : interacting with the registry api
ENV REGISTRY_URL=""

# prevents APT interactions
ENV DEBIAN_FRONTEND=noninteractive

# install required package
ARG APP_PACKAGES="python3-fastapi procps"
RUN apt-get update && \
apt-get -y upgrade && \
apt-get -y install $APP_PACKAGES --no-install-recommends && \
rm -rf /var/lib/apt/lists/*

# install application
COPY webapp $APP_DIR/
COPY entrypoint.sh /

# define startup script
ENTRYPOINT [ "/entrypoint.sh" ]
