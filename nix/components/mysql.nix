{ config, lib, ... }:

let
  cfg = config.services.lab-gateway-components;
  inherit (lib) mkIf optionals;
  gatewayEnvFiles = optionals (cfg.envFile != null) [ cfg.envFile ];
  netOpt = "--network=${cfg.networkName}";
in
{
  config = mkIf cfg.enable {
    virtualisation.oci-containers.containers.mysql = {
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

    systemd.services."docker-mysql" = {
      wants = [ "lab-gateway-create-network.service" ];
      after = [ "lab-gateway-create-network.service" ];
    };
  };
}
