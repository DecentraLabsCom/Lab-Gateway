{ config, lib, ... }:

let
  cfg = config.services.lab-gateway-components;
  inherit (lib) mkIf optionals;
  gatewayEnvFiles = optionals (cfg.envFile != null) [ cfg.envFile ];
  netOpt = "--network=${cfg.networkName}";
in
{
  config = mkIf cfg.enable {
    virtualisation.oci-containers.containers.guacamole = {
      image = cfg.guacamoleImage;
      dependsOn = [ "mysql" "guacd" ];
      environmentFiles = gatewayEnvFiles;
      environment = {
        GUACD_HOSTNAME = "guacd";
        MYSQL_HOSTNAME = "mysql";
      };
      extraOptions = [ netOpt ];
    };

    systemd.services."docker-guacamole" = {
      wants = [ "lab-gateway-create-network.service" ] ++
        optionals cfg.buildLocalImages [ "lab-gateway-build-images.service" ];
      after = [ "lab-gateway-create-network.service" ] ++
        optionals cfg.buildLocalImages [ "lab-gateway-build-images.service" ];
    };
  };
}
