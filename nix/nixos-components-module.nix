{ config, lib, pkgs, ... }:

let
  cfg = config.services.lab-gateway-components;
  inherit (lib) mkEnableOption mkIf mkOption optionalAttrs optionals types;

  gatewayEnvFiles = optionals (cfg.envFile != null) [ cfg.envFile ];
  blockchainEnvFiles =
    gatewayEnvFiles ++
    optionals (cfg.blockchainEnvFile != null) [ cfg.blockchainEnvFile ];

  netOpt = "--network=${cfg.networkName}";
in
{
  options.services.lab-gateway-components = {
    enable = mkEnableOption "DecentraLabs Gateway (componentized OCI containers)";

    projectDir = mkOption {
      type = types.str;
      default = "/srv/lab-gateway";
      description = "Project directory where gateway files are located.";
    };

    envFile = mkOption {
      type = types.nullOr types.str;
      default = "/srv/lab-gateway/.env";
      description = "Main gateway .env file.";
    };

    blockchainEnvFile = mkOption {
      type = types.nullOr types.str;
      default = "/srv/lab-gateway/blockchain-services/.env";
      description = "Blockchain-specific .env file.";
    };

    networkName = mkOption {
      type = types.str;
      default = "guacnet";
      description = "Docker network used by gateway containers.";
    };

    openrestyImage = mkOption {
      type = types.str;
      default = "lab-gateway/openresty:local";
      description = "Docker image tag for OpenResty.";
    };

    guacamoleImage = mkOption {
      type = types.str;
      default = "lab-gateway/guacamole:local";
      description = "Docker image tag for Guacamole web.";
    };

    blockchainImage = mkOption {
      type = types.str;
      default = "lab-gateway/blockchain-services:local";
      description = "Docker image tag for blockchain-services.";
    };

    opsWorkerImageName = mkOption {
      type = types.str;
      default = "lab-gateway-ops-worker:nix";
      description = "Docker tag for the Nix-built ops-worker image.";
    };

    opsWorkerImageFile = mkOption {
      type = types.package;
      default = pkgs.callPackage ./images/ops-worker-image.nix { };
      description = "Nix-built OCI image tarball for ops-worker.";
    };

    buildLocalImages = mkOption {
      type = types.bool;
      default = true;
      description = ''
        Build OpenResty, Guacamole and blockchain-services images from local Dockerfiles
        before starting component containers.
      '';
    };

    openrestyBindAddress = mkOption {
      type = types.str;
      default = "127.0.0.1";
      description = "Host bind address for OpenResty ports.";
    };

    openrestyHttpsPort = mkOption {
      type = types.int;
      default = 443;
      description = "Host HTTPS port exposed by OpenResty.";
    };

    openrestyHttpPort = mkOption {
      type = types.int;
      default = 80;
      description = "Host HTTP port exposed by OpenResty.";
    };

    opsConfigPath = mkOption {
      type = types.str;
      default = "/srv/lab-gateway/ops-worker/hosts.empty.json";
      description = "Path to ops-worker hosts.json source file.";
    };

    opsMysqlDsn = mkOption {
      type = types.nullOr types.str;
      default = null;
      description = ''
        Optional DSN used by ops-worker for reservation automation.
        Example: mysql+pymysql://user:password@mysql:3306/guacamole_db
      '';
    };
  };

  config = mkIf cfg.enable {
    virtualisation.docker.enable = lib.mkDefault true;
    virtualisation.oci-containers.backend = "docker";

    systemd.services.lab-gateway-create-network = {
      description = "Create Docker network for DecentraLabs Gateway";
      wantedBy = [ "multi-user.target" ];
      wants = [ "docker.service" ];
      after = [ "docker.service" ];
      path = [ pkgs.docker ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      script = ''
        if ! docker network inspect ${lib.escapeShellArg cfg.networkName} >/dev/null 2>&1; then
          docker network create ${lib.escapeShellArg cfg.networkName}
        fi
      '';
    };

    systemd.services.lab-gateway-build-images = mkIf cfg.buildLocalImages {
      description = "Build gateway component images from local Dockerfiles";
      wantedBy = [ "multi-user.target" ];
      wants = [ "docker.service" "network-online.target" ];
      after = [ "docker.service" "network-online.target" ];
      path = [ pkgs.docker ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      script = ''
        docker build -t ${lib.escapeShellArg cfg.openrestyImage} ${lib.escapeShellArg "${cfg.projectDir}/openresty"}
        docker build -t ${lib.escapeShellArg cfg.guacamoleImage} ${lib.escapeShellArg "${cfg.projectDir}/guacamole"}
        docker build -t ${lib.escapeShellArg cfg.blockchainImage} ${lib.escapeShellArg "${cfg.projectDir}/blockchain-services"}
      '';
    };

    virtualisation.oci-containers.containers = {
      mysql = {
        image = "mysql:8.0.41";
        entrypoint = [ "/bin/bash" "/usr/local/bin/ensure-user-entrypoint.sh" ];
        cmd = [ "mysqld" ];
        environmentFiles = gatewayEnvFiles;
        environment = {
          BLOCKCHAIN_MYSQL_DATABASE = "blockchain_services";
        };
        volumes = [
          "mysql_data:/var/lib/mysql"
          "${cfg.projectDir}/mysql/ensure-user-entrypoint.sh:/usr/local/bin/ensure-user-entrypoint.sh:ro"
          "${cfg.projectDir}/mysql/000-ensure-user.sh:/docker-entrypoint-initdb.d/000-ensure-user.sh:ro"
          "${cfg.projectDir}/mysql/001-create-schema.sql:/docker-entrypoint-initdb.d/001-create-schema.sql:ro"
          "${cfg.projectDir}/mysql/002-labstation-ops.sql:/docker-entrypoint-initdb.d/002-labstation-ops.sql:ro"
        ];
        extraOptions = [ netOpt ];
      };

      guacd = {
        image = "guacamole/guacd:1.5.5";
        extraOptions = [ netOpt ];
      };

      guacamole = {
        image = cfg.guacamoleImage;
        dependsOn = [ "mysql" "guacd" ];
        environmentFiles = gatewayEnvFiles;
        environment = {
          GUACD_HOSTNAME = "guacd";
          MYSQL_HOSTNAME = "mysql";
        };
        extraOptions = [ netOpt ];
      };

      "blockchain-services" = {
        image = cfg.blockchainImage;
        dependsOn = [ "mysql" ];
        environmentFiles = blockchainEnvFiles;
        environment = {
          SPRING_DATASOURCE_URL = "jdbc:mysql://mysql:3306/blockchain_services?serverTimezone=UTC&characterEncoding=UTF-8&useSSL=false&allowPublicKeyRetrieval=true";
          PROVIDER_CONFIG_PATH = "/app/data/provider.properties";
        };
        volumes = [
          "${cfg.projectDir}/certs:/app/config/keys"
          "${cfg.projectDir}/blockchain-data:/app/data"
        ];
        extraOptions = [ netOpt ];
      };

      "ops-worker" = {
        image = cfg.opsWorkerImageName;
        imageFile = cfg.opsWorkerImageFile;
        dependsOn = [ "mysql" ];
        environmentFiles = gatewayEnvFiles;
        environment = {
          OPS_BIND = "0.0.0.0";
          OPS_PORT = "8081";
          OPS_CONFIG = "/app/hosts.json";
          OPS_POLL_ENABLED = "true";
          OPS_POLL_INTERVAL = "60";
          OPS_RESERVATION_AUTOMATION = "true";
          OPS_RESERVATION_SCAN_INTERVAL = "30";
          OPS_RESERVATION_START_LEAD = "120";
          OPS_RESERVATION_END_DELAY = "60";
        } // optionalAttrs (cfg.opsMysqlDsn != null) {
          MYSQL_DSN = cfg.opsMysqlDsn;
        };
        volumes = [
          "${cfg.opsConfigPath}:/app/hosts.json:ro"
        ];
        extraOptions = [ netOpt "--read-only" "--tmpfs=/tmp:size=32m,mode=1777" ];
      };

      openresty = {
        image = cfg.openrestyImage;
        dependsOn = [ "guacamole" "blockchain-services" "ops-worker" ];
        environmentFiles = gatewayEnvFiles;
        volumes = [
          "${cfg.projectDir}/certs:/etc/ssl/private"
          "${cfg.projectDir}/certbot/www:/var/www/certbot"
          "${cfg.projectDir}/openresty/nginx.conf:/usr/local/openresty/nginx/conf/nginx.conf:ro"
          "${cfg.projectDir}/openresty/lab_access.conf:/etc/openresty/lab_access.conf:ro"
          "${cfg.projectDir}/openresty/lua:/etc/openresty/lua:ro"
          "${cfg.projectDir}/web:/var/www/html:ro"
        ];
        ports = [
          "${cfg.openrestyBindAddress}:${toString cfg.openrestyHttpsPort}:443"
          "${cfg.openrestyBindAddress}:${toString cfg.openrestyHttpPort}:80"
        ];
        extraOptions = [ netOpt "--tmpfs=/tmp:size=64m,mode=1777" "--tmpfs=/var/run:size=16m,mode=755" ];
      };
    };

    systemd.services."docker-mysql" = {
      wants = [ "lab-gateway-create-network.service" ];
      after = [ "lab-gateway-create-network.service" ];
    };

    systemd.services."docker-guacd" = {
      wants = [ "lab-gateway-create-network.service" ];
      after = [ "lab-gateway-create-network.service" ];
    };

    systemd.services."docker-guacamole" = {
      wants = [ "lab-gateway-create-network.service" ] ++
        optionals cfg.buildLocalImages [ "lab-gateway-build-images.service" ];
      after = [ "lab-gateway-create-network.service" ] ++
        optionals cfg.buildLocalImages [ "lab-gateway-build-images.service" ];
    };

    systemd.services."docker-blockchain-services" = {
      wants = [ "lab-gateway-create-network.service" ] ++
        optionals cfg.buildLocalImages [ "lab-gateway-build-images.service" ];
      after = [ "lab-gateway-create-network.service" ] ++
        optionals cfg.buildLocalImages [ "lab-gateway-build-images.service" ];
    };

    systemd.services."docker-ops-worker" = {
      wants = [ "lab-gateway-create-network.service" ];
      after = [ "lab-gateway-create-network.service" ];
    };

    systemd.services."docker-openresty" = {
      wants = [ "lab-gateway-create-network.service" ] ++
        optionals cfg.buildLocalImages [ "lab-gateway-build-images.service" ];
      after = [ "lab-gateway-create-network.service" ] ++
        optionals cfg.buildLocalImages [ "lab-gateway-build-images.service" ];
    };
  };
}
