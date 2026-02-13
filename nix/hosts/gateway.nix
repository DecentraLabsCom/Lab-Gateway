{ lib, pkgs, ... }:

{
  networking.hostName = lib.mkDefault "lab-gateway";
  time.timeZone = lib.mkDefault "UTC";

  services.openssh = {
    enable = lib.mkDefault true;
    settings = {
      PasswordAuthentication = lib.mkDefault false;
      KbdInteractiveAuthentication = lib.mkDefault false;
    };
  };

  networking.firewall = {
    enable = lib.mkDefault true;
    allowedTCPPorts = [ 22 80 443 ];
  };

  virtualisation.docker = {
    enable = lib.mkDefault true;
    autoPrune = {
      enable = lib.mkDefault true;
      dates = lib.mkDefault "weekly";
    };
  };

  systemd.tmpfiles.rules = [
    "d /srv/lab-gateway 0755 root root -"
    "d /srv/lab-gateway/blockchain-data 0750 root root -"
    "d /srv/lab-gateway/certs 0750 root root -"
    "d /srv/lab-gateway/certbot 0755 root root -"
    "d /srv/lab-gateway/certbot/www 0755 root root -"
  ];

  services.lab-gateway = {
    enable = true;
    projectDir = "/srv/lab-gateway";
    envFile = "/srv/lab-gateway/.env";
    buildOnStart = true;
    removeOrphansOnStart = true;
    removeVolumesOnStop = false;
  };

  environment.systemPackages = [
    pkgs.git
    pkgs.docker-compose
    (pkgs.callPackage ../lab-gateway-docker.nix { })
  ];

  # Keep this aligned with the value already used by your host.
  system.stateVersion = lib.mkDefault "24.11";
}
