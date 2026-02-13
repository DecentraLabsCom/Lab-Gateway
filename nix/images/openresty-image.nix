{ dockerTools
, fetchFromGitHub
, bash
, coreutils
, curl
, findutils
, gawk
, gnugrep
, gnused
, nginx
, openresty
, openssl
, certbot
}:

let
  luaRestyHttp = fetchFromGitHub {
    owner = "ledgetech";
    repo = "lua-resty-http";
    rev = "v0.17.2";
    hash = "sha256-PaGMqFgiQ+/ygwJZHjZlHcf6sEbnczaqSm+nGLzM5KI=";
  };

  luaRestyJwt = fetchFromGitHub {
    owner = "SkyLothar";
    repo = "lua-resty-jwt";
    rev = "v0.1.11";
    hash = "sha256-58KwuO3xTu11ac1WhPwAxvl6ir9tbA5GLNSbSyZuM5A=";
  };

  luaRestyOpenssl = fetchFromGitHub {
    owner = "fffonion";
    repo = "lua-resty-openssl";
    rev = "1.6.4";
    hash = "sha256-UfYnv/bjmhoH7KyS3tDu/H2mbxuX20DkiGELDTA55fs=";
  };

  luaRestyMysql = fetchFromGitHub {
    owner = "openresty";
    repo = "lua-resty-mysql";
    rev = "v0.27";
    hash = "sha256-7ort7///WpJMEhcsoCep2xX7ADTTi3GZF5XenNwLyXU=";
  };

  luaRestyString = fetchFromGitHub {
    owner = "openresty";
    repo = "lua-resty-string";
    rev = "v0.16";
    hash = "sha256-d/AGqX/Uo75Kgtzy1fFILjmbcPs1RUxbWtS5f/Hd7Q0=";
  };
in
dockerTools.buildLayeredImage {
  name = "lab-gateway-openresty";
  tag = "nix";

  contents = [
    bash
    coreutils
    curl
    findutils
    gawk
    gnugrep
    gnused
    nginx
    openresty
    openssl
    certbot
  ];

  extraCommands = ''
    mkdir -p usr/local/bin
    mkdir -p usr/local/openresty/bin
    mkdir -p usr/local/openresty/nginx/conf
    mkdir -p usr/local/openresty/site/lualib/resty
    mkdir -p etc/openresty
    mkdir -p etc/ssl/private
    mkdir -p var/www/html
    mkdir -p var/www/certbot

    cat > usr/local/openresty/bin/openresty <<'EOF'
    #!/bin/sh
    exec ${openresty}/bin/openresty -p /usr/local/openresty/nginx/ -c conf/nginx.conf "$@"
    EOF
    chmod +x usr/local/openresty/bin/openresty

    cp ${nginx}/conf/mime.types usr/local/openresty/nginx/conf/mime.types
    cp ${../../openresty/nginx.conf} usr/local/openresty/nginx/conf/nginx.conf
    cp ${../../openresty/lab_access.conf} etc/openresty/lab_access.conf
    cp ${../../openresty/init-ssl.sh} usr/local/bin/init-ssl.sh
    chmod +x usr/local/bin/init-ssl.sh

    cp -r ${../../openresty/lua} etc/openresty/lua
    cp -r ${../../web}/. var/www/html/

    cp -r ${luaRestyHttp}/lib/resty/. usr/local/openresty/site/lualib/resty/
    cp -r ${luaRestyJwt}/lib/resty/. usr/local/openresty/site/lualib/resty/
    cp -r ${luaRestyMysql}/lib/resty/. usr/local/openresty/site/lualib/resty/
    cp -r ${luaRestyString}/lib/resty/. usr/local/openresty/site/lualib/resty/
    cp -r ${luaRestyOpenssl}/lib/resty/. usr/local/openresty/site/lualib/resty/
  '';

  config = {
    WorkingDir = "/";
    Env = [
      "PATH=/usr/local/openresty/bin:/usr/local/bin:/bin"
    ];
    ExposedPorts = {
      "80/tcp" = { };
      "443/tcp" = { };
    };
    Cmd = [ "/usr/local/bin/init-ssl.sh" ];
  };
}
