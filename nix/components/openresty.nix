{ config, lib, ... }:

let
  cfg = config.services.lab-gateway-components;
  inherit (lib) mkIf optionals;
  gatewayEnvFiles = optionals (cfg.envFile != null) [ cfg.envFile ];
  netOpt = "--network=${cfg.networkName}";
in
{
  config = mkIf cfg.enable {
    virtualisation.oci-containers.containers.openresty = {
      image = cfg.openrestyImage;
      imageFile = cfg.openrestyImageFile;
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

    systemd.services."docker-openresty" = {
      wants = [ "lab-gateway-create-network.service" ];
      after = [ "lab-gateway-create-network.service" ];
    };
  };
}
