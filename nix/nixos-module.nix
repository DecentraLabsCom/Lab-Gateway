{ config, lib, pkgs, ... }:

let
  cfg = config.services.lab-gateway;
  inherit (lib) concatMapStrings mkEnableOption mkIf mkOption optionalString types;
  envFileArg =
    optionalString (cfg.envFile != null) " --env-file ${lib.escapeShellArg cfg.envFile}";
  profileArgs =
    concatMapStrings (profile: " --profile ${lib.escapeShellArg profile}") cfg.profiles;
  buildArg = optionalString cfg.buildOnStart " --build";
  removeOrphansArg = optionalString cfg.removeOrphansOnStart " --remove-orphans";
  removeVolumesArg = optionalString cfg.removeVolumesOnStop " --volumes";
  commonArgs = ''
    --project-dir ${lib.escapeShellArg cfg.projectDir}
    --project-name ${lib.escapeShellArg cfg.projectName}${envFileArg}${profileArgs}
  '';
in
{
  options.services.lab-gateway = {
    enable = mkEnableOption "DecentraLabs Gateway (Docker Compose stack)";

    package = mkOption {
      type = types.package;
      default = pkgs.callPackage ./lab-gateway-docker.nix { };
      description = "Helper package that wraps docker compose for this stack.";
    };

    projectDir = mkOption {
      type = types.str;
      default = "/srv/lab-gateway";
      description = "Path where docker-compose.yml and project files are located.";
    };

    projectName = mkOption {
      type = types.str;
      default = "lab-gateway";
      description = "Compose project name used for container and network naming.";
    };

    envFile = mkOption {
      type = types.nullOr types.str;
      default = null;
      description = ''
        Optional path to the main .env file to pass to docker compose.
        If null, compose uses default environment resolution.
      '';
    };

    profiles = mkOption {
      type = types.listOf types.str;
      default = [ ];
      description = "Optional docker compose profiles to enable (for example: cloudflare).";
    };

    buildOnStart = mkOption {
      type = types.bool;
      default = true;
      description = "Whether to run compose with --build during service start.";
    };

    removeOrphansOnStart = mkOption {
      type = types.bool;
      default = true;
      description = "Whether to pass --remove-orphans to compose up.";
    };

    removeVolumesOnStop = mkOption {
      type = types.bool;
      default = false;
      description = "Whether to pass --volumes to compose down.";
    };
  };

  config = mkIf cfg.enable {
    virtualisation.docker.enable = lib.mkDefault true;

    systemd.services.lab-gateway = {
      description = "DecentraLabs Gateway";
      wantedBy = [ "multi-user.target" ];
      wants = [ "docker.service" "network-online.target" ];
      after = [ "docker.service" "network-online.target" ];

      path = [ pkgs.docker cfg.package ];

      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        WorkingDirectory = cfg.projectDir;
        TimeoutStartSec = "0";
      };

      script = ''
        ${cfg.package}/bin/lab-gateway ${commonArgs} up -d${buildArg}${removeOrphansArg}
      '';

      preStop = ''
        ${cfg.package}/bin/lab-gateway ${commonArgs} down${removeVolumesArg}
      '';
    };
  };
}
