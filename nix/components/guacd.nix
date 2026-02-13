{ config, lib, ... }:

let
  cfg = config.services.lab-gateway-components;
  inherit (lib) mkIf;
  netOpt = "--network=${cfg.networkName}";
in
{
  config = mkIf cfg.enable {
    virtualisation.oci-containers.containers.guacd = {
      image = "guacamole/guacd:1.5.5";
      extraOptions = [ netOpt ];
    };

    systemd.services."docker-guacd" = {
      wants = [ "lab-gateway-create-network.service" ];
      after = [ "lab-gateway-create-network.service" ];
    };
  };
}
