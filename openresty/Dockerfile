# Pin to specific version for reproducibility and security
# Check https://hub.docker.com/r/openresty/openresty/tags for updates
FROM openresty/openresty:1.27.1.2-11-alpine-fat

# Use the default system tree
ENV TREE=/usr/local

# Configure paths explicitly
ENV LUA_PATH="$TREE/share/lua/5.1/?.lua;$TREE/share/lua/5.1/?/init.lua;;"
ENV LUA_CPATH="$TREE/lib/lua/5.1/?.so;;"

RUN apk add --no-cache \
    build-base \
    openssl \
    git \
    luarocks \
    curl

# Install Lua modules
RUN luarocks --tree=$TREE install lua-resty-http && \
    luarocks --tree=$TREE install lua-resty-jwt && \
    luarocks --tree=$TREE install lua-resty-openssl && \
    luarocks --tree=$TREE install lua-resty-mysql

# Directory for custom scripts and SSL certificates
RUN mkdir -p /etc/openresty/lua /etc/ssl/private

# Copy SSL initialization script
COPY init-ssl.sh /usr/local/bin/init-ssl.sh
RUN chmod +x /usr/local/bin/init-ssl.sh

EXPOSE 80 443

CMD ["/usr/local/bin/init-ssl.sh"]
