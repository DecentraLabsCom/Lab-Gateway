# Pin to specific version for reproducibility and security
# Check https://hub.docker.com/r/openresty/openresty/tags for updates
FROM openresty/openresty:1.31.1.1-3-alpine-fat

# Use the default system tree
ENV TREE=/usr/local

# Configure paths explicitly
ENV LUA_PATH="$TREE/share/lua/5.1/?.lua;$TREE/share/lua/5.1/?/init.lua;;"
ENV LUA_CPATH="$TREE/lib/lua/5.1/?.so;;"

RUN apk add --no-cache \
    build-base \
    openssl \
    ca-certificates \
    git \
    luarocks \
    curl

# Install pinned Lua modules. Download the artifacts with curl because the
# bundled LuaRocks 3.13 client can crash when a transient CDN response omits
# the error filename while fetching a remote rock.
RUN set -eux; \
    install_luarock() { \
        package="$1"; \
        checksum="$2"; \
        curl --fail --location --retry 5 --retry-all-errors --retry-delay 2 \
            --connect-timeout 15 --max-time 120 \
            --output "/tmp/${package}" "https://luarocks.org/${package}"; \
        echo "${checksum}  /tmp/${package}" | sha256sum -c -; \
        luarocks --tree="$TREE" install "/tmp/${package}"; \
        rm -f "/tmp/${package}"; \
    }; \
    install_luarock lua-resty-openssl-1.9.0-1.src.rock 7b33ddc6a5125049ae6e17116924f79246ec158bd0eaf8e77bef2b040bc33dd4; \
    install_luarock lua-resty-http-0.18.0-0.src.rock 9059fb963c1db4a2328b65307f5b09fd0decfa414da7bf842d95795e845d6827; \
    install_luarock lua-resty-jwt-0.3.2-1.src.rock 3facb248244a28357710629b072f7742ab89527a39ce2a825e613a094a640be8; \
    install_luarock lua-resty-mysql-0.15-0.rockspec b23be63861fb7109459e6edd41938415ffb667f7a2361030f65d7e588b0fd474

# Directory for custom scripts and SSL certificates
RUN mkdir -p /etc/openresty/lua /etc/openresty/jwt-keys /etc/ssl/private /var/lib/openresty/fmu-access \
    && chown nobody:nobody /var/lib/openresty/fmu-access \
    && chmod 700 /var/lib/openresty/fmu-access

# Copy SSL initialization script
COPY init-ssl.sh /usr/local/bin/init-ssl.sh
COPY init-ssl-secrets.sh /usr/local/bin/init-ssl-secrets.sh
COPY init-ssl-tls.sh /usr/local/bin/init-ssl-tls.sh
COPY init-ssl-jwt-sync.sh /usr/local/bin/init-ssl-jwt-sync.sh
COPY init-ssl-jwt-watchers.sh /usr/local/bin/init-ssl-jwt-watchers.sh
COPY conf.d/gateway_health_internal.conf /etc/openresty/conf.d/gateway_health_internal.conf
COPY conf.d/gateway_auth_handoff.conf /etc/openresty/conf.d/gateway_auth_handoff.conf
COPY conf.d/gateway_auth_backend.conf /etc/openresty/conf.d/gateway_auth_backend.conf
COPY conf.d/gateway_billing.conf /etc/openresty/conf.d/gateway_billing.conf
COPY conf.d/gateway_wallet.conf /etc/openresty/conf.d/gateway_wallet.conf
COPY conf.d/gateway_wallet_dashboard.conf /etc/openresty/conf.d/gateway_wallet_dashboard.conf
COPY conf.d/gateway_institution_config.conf /etc/openresty/conf.d/gateway_institution_config.conf
COPY conf.d/gateway_admin_session.conf /etc/openresty/conf.d/gateway_admin_session.conf
COPY conf.d/gateway_intents.conf /etc/openresty/conf.d/gateway_intents.conf
COPY conf.d/gateway_ops.conf /etc/openresty/conf.d/gateway_ops.conf
COPY conf.d/gateway_lab_status.conf /etc/openresty/conf.d/gateway_lab_status.conf
COPY conf.d/gateway_onboarding_webauthn.conf /etc/openresty/conf.d/gateway_onboarding_webauthn.conf
COPY conf.d/gateway_lab_manager.conf /etc/openresty/conf.d/gateway_lab_manager.conf
COPY conf.d/gateway_lab_admin.conf /etc/openresty/conf.d/gateway_lab_admin.conf
COPY conf.d/gateway_lab_content.conf /etc/openresty/conf.d/gateway_lab_content.conf
COPY conf.d/gateway_guacamole_auth.conf /etc/openresty/conf.d/gateway_guacamole_auth.conf
COPY conf.d/gateway_guacamole_proxy.conf /etc/openresty/conf.d/gateway_guacamole_proxy.conf
COPY conf.d/gateway_guacamole_provisioner.conf /etc/openresty/conf.d/gateway_guacamole_provisioner.conf
COPY conf.d/gateway_aas_public.conf /etc/openresty/conf.d/gateway_aas_public.conf
COPY conf.d/gateway_aas_admin.conf /etc/openresty/conf.d/gateway_aas_admin.conf
COPY conf.d/gateway_aas_resolve.conf /etc/openresty/conf.d/gateway_aas_resolve.conf
COPY conf.d/gateway_gateway_mode.conf /etc/openresty/conf.d/gateway_gateway_mode.conf
COPY conf.d/gateway_fmu.conf /etc/openresty/conf.d/gateway_fmu.conf
RUN chmod +x /usr/local/bin/init-ssl.sh /usr/local/bin/init-ssl-secrets.sh /usr/local/bin/init-ssl-tls.sh /usr/local/bin/init-ssl-jwt-sync.sh /usr/local/bin/init-ssl-jwt-watchers.sh

EXPOSE 80 443

CMD ["/usr/local/bin/init-ssl.sh"]
