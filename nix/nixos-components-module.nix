{ config, lib, pkgs, ... }:

let
  cfg = config.services.lab-gateway-components;
  inherit (lib) mkEnableOption mkIf mkOption types;
in
{
  imports = [
    ./components/mysql.nix
    ./components/guacd.nix
    ./components/guacamole.nix
    ./components/blockchain-services.nix
    ./components/ops-worker.nix
    ./components/openresty.nix
  ];

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

    buildLocalImages = mkOption {
      type = types.bool;
      default = true;
      description = ''
        Build Guacamole and blockchain-services images from local Dockerfiles
        before starting component containers.
      '';
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

    openrestyImage = mkOption {
      type = types.str;
      default = "lab-gateway-openresty:nix";
      description = "Docker image tag for OpenResty.";
    };

    openrestyImageFile = mkOption {
      type = types.package;
      default = pkgs.callPackage ./images/openresty-image.nix { };
      description = "Nix-built OCI image tarball for OpenResty.";
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
        docker build -t ${lib.escapeShellArg cfg.guacamoleImage} ${lib.escapeShellArg "${cfg.projectDir}/guacamole"}
        docker build -t ${lib.escapeShellArg cfg.blockchainImage} ${lib.escapeShellArg "${cfg.projectDir}/blockchain-services"}
      '';
    };
  };
}
