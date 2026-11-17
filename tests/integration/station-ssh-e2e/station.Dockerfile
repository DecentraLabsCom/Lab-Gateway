FROM golang:1.27.0 AS build
WORKDIR /src
COPY --from=station_src . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/labstation-dispatcher ./cmd/labstation-dispatcher \
    && CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/labstation-helper ./cmd/labstation-helper

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-server sudo netcat-openbsd ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --home-dir /var/lib/labstation-ops --shell /bin/sh labstation-ops \
    && useradd --system --home-dir /var/lib/decentralabs/lab-station --no-create-home --shell /usr/sbin/nologin labstationd \
    && useradd --system --home-dir /var/lib/decentralabs/lab-station/tiny-desk-session --no-create-home --shell /usr/sbin/nologin labuser \
    && install -d -o root -g root -m 0755 /usr/local/lib/decentralabs /usr/local/sbin /usr/lib/decentralabs/lab-station /etc/ssh/authorized_keys \
    && install -d -o root -g root -m 0755 /var/lib/decentralabs/lab-station /var/lib/decentralabs/lab-station/tiny-desk-session \
    && install -d -o labuser -g labuser -m 0700 /var/lib/decentralabs/lab-station/tiny-desk-home \
        /var/lib/decentralabs/lab-station/tiny-desk-home/.cache \
        /var/lib/decentralabs/lab-station/tiny-desk-home/tmp \
        /var/lib/decentralabs/lab-station/tiny-desk-home/.config \
        /var/lib/decentralabs/lab-station/tiny-desk-home/.local \
        /var/lib/decentralabs/lab-station/tiny-desk-home/.local/share \
        /var/lib/decentralabs/lab-station/tiny-desk-home/Downloads \
        /var/lib/decentralabs/lab-station/tiny-desk-home/Documents \
        /var/lib/decentralabs/lab-station/tiny-desk-home/Documents/LabStationScratch \
        /var/lib/decentralabs/lab-station/tiny-desk-home/.local/share/Trash \
        /var/lib/decentralabs/lab-station/tiny-desk-home/.local/share/Trash/files \
        /var/lib/decentralabs/lab-station/tiny-desk-home/.local/share/Trash/info \
    && install -d -o labstationd -g labstationd -m 0750 /var/lib/decentralabs/lab-station/data \
    && install -d -o root -g root -m 0755 /etc/decentralabs/lab-station
COPY --from=build /out/labstation-dispatcher /usr/local/lib/decentralabs/labstation-dispatcher
COPY --from=build /out/labstation-helper /usr/lib/decentralabs/lab-station/labstation-helper
COPY station-entrypoint.sh /usr/local/sbin/station-entrypoint
COPY station-dispatcher-wrapper.sh /usr/local/sbin/labstation-ssh-dispatcher-wrapper
COPY loginctl-stub.sh /usr/bin/loginctl
RUN chmod 0755 /usr/local/lib/decentralabs/labstation-dispatcher /usr/lib/decentralabs/lab-station/labstation-helper \
      /usr/local/sbin/station-entrypoint \
      /usr/local/sbin/labstation-ssh-dispatcher-wrapper /usr/bin/loginctl \
    && printf 'labstation-ops ALL=(labstationd) NOPASSWD: /usr/local/lib/decentralabs/labstation-dispatcher ""\n' \
      > /etc/sudoers.d/labstation-e2e \
    && chmod 0440 /etc/sudoers.d/labstation-e2e

RUN printf 'labstationd ALL=(root) NOPASSWD: /usr/lib/decentralabs/lab-station/labstation-helper ""\n' \
    > /etc/sudoers.d/labstation-helper-e2e \
    && chmod 0440 /etc/sudoers.d/labstation-helper-e2e
EXPOSE 2222
ENTRYPOINT ["/usr/local/sbin/station-entrypoint"]
