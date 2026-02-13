{ config, lib, ... }:

let
  cfg = config.services.lab-gateway-components;
  inherit (lib) mkIf optionals;
  gatewayEnvFiles = optionals (cfg.envFile != null) [ cfg.envFile ];
  blockchainEnvFiles =
    gatewayEnvFiles ++ optionals (cfg.blockchainEnvFile != null) [ cfg.blockchainEnvFile ];
  netOpt = "--network=${cfg.networkName}";
in
{
  config = mkIf cfg.enable {
    virtualisation.oci-containers.containers."blockchain-services" = {
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

    systemd.services."docker-blockchain-services" = {
      wants = [ "lab-gateway-create-network.service" ] ++
        optionals cfg.buildLocalImages [ "lab-gateway-build-images.service" ];
      after = [ "lab-gateway-create-network.service" ] ++
        optionals cfg.buildLocalImages [ "lab-gateway-build-images.service" ];
    };
  };
}
