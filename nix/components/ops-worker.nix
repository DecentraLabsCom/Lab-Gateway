{ config, lib, ... }:

let
  cfg = config.services.lab-gateway-components;
  inherit (lib) mkIf optionalAttrs optionals;
  gatewayEnvFiles = optionals (cfg.envFile != null) [ cfg.envFile ];
  netOpt = "--network=${cfg.networkName}";
in
{
  config = mkIf cfg.enable {
    virtualisation.oci-containers.containers."ops-worker" = {
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

    systemd.services."docker-ops-worker" = {
      wants = [ "lab-gateway-create-network.service" ];
      after = [ "lab-gateway-create-network.service" ];
    };
  };
}
