FROM openresty/openresty:alpine-fat

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
    luarocks --tree=$TREE install lua-resty-openssl

# Directory for custom scripts
RUN mkdir -p /etc/openresty/lua

EXPOSE 80 443

CMD ["/usr/local/openresty/bin/openresty", "-g", "daemon off;"]