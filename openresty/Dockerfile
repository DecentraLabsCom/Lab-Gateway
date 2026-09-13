# Pin to specific version for reproducibility and security
# Check https://hub.docker.com/r/openresty/openresty/tags for updates
FROM openresty/openresty:1.31.1.1-2-alpine-fat

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

# Install Lua modules
RUN luarocks --tree=$TREE install lua-resty-http && \
    luarocks --tree=$TREE install lua-resty-jwt && \
    luarocks --tree=$TREE install lua-resty-openssl && \
    luarocks --tree=$TREE install lua-resty-mysql

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
COPY lab_access_health_internal.conf /etc/openresty/lab_access_health_internal.conf
COPY lab_access_auth_handoff.conf /etc/openresty/lab_access_auth_handoff.conf
COPY lab_access_auth_backend.conf /etc/openresty/lab_access_auth_backend.conf
COPY lab_access_billing.conf /etc/openresty/lab_access_billing.conf
COPY lab_access_wallet.conf /etc/openresty/lab_access_wallet.conf
COPY lab_access_wallet_dashboard.conf /etc/openresty/lab_access_wallet_dashboard.conf
COPY lab_access_institution_config.conf /etc/openresty/lab_access_institution_config.conf
COPY lab_access_admin_session.conf /etc/openresty/lab_access_admin_session.conf
COPY lab_access_intents.conf /etc/openresty/lab_access_intents.conf
COPY lab_access_ops.conf /etc/openresty/lab_access_ops.conf
COPY lab_access_onboarding_webauthn.conf /etc/openresty/lab_access_onboarding_webauthn.conf
COPY lab_access_lab_manager.conf /etc/openresty/lab_access_lab_manager.conf
COPY lab_access_lab_admin.conf /etc/openresty/lab_access_lab_admin.conf
COPY lab_access_lab_content.conf /etc/openresty/lab_access_lab_content.conf
COPY lab_access_guacamole_auth.conf /etc/openresty/lab_access_guacamole_auth.conf
COPY lab_access_guacamole_proxy.conf /etc/openresty/lab_access_guacamole_proxy.conf
COPY lab_access_guacamole_provisioner.conf /etc/openresty/lab_access_guacamole_provisioner.conf
COPY lab_access_aas_public.conf /etc/openresty/lab_access_aas_public.conf
COPY lab_access_aas_admin.conf /etc/openresty/lab_access_aas_admin.conf
COPY lab_access_aas_resolve.conf /etc/openresty/lab_access_aas_resolve.conf
COPY lab_access_gateway_mode.conf /etc/openresty/lab_access_gateway_mode.conf
COPY lab_access_fmu.conf /etc/openresty/lab_access_fmu.conf
RUN chmod +x /usr/local/bin/init-ssl.sh /usr/local/bin/init-ssl-secrets.sh /usr/local/bin/init-ssl-tls.sh /usr/local/bin/init-ssl-jwt-sync.sh /usr/local/bin/init-ssl-jwt-watchers.sh

EXPOSE 80 443

CMD ["/usr/local/bin/init-ssl.sh"]
