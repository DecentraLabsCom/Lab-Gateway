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
  stateEnvFile = if cfg.envFile != null then cfg.envFile else "${cfg.projectDir}/.env";
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

      path = [ pkgs.coreutils pkgs.docker cfg.package ];

      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        WorkingDirectory = cfg.projectDir;
        TimeoutStartSec = "0";
      };

      # Compose bind mounts keep host ownership. Prepare every writable state
      # path using the same HOST_UID/HOST_GID that Compose passes to services;
      # otherwise a fresh NixOS host lets Docker create root-owned directories
      # and the non-root containers fail on their first write.
      preStart = ''
        set -eu
        project_dir=${lib.escapeShellArg cfg.projectDir}
        env_file=${lib.escapeShellArg stateEnvFile}
        if [ ! -f "$env_file" ]; then
          echo "Lab Gateway environment file not found: $env_file" >&2
          exit 1
        fi

        host_uid="$(sed -n -E 's/^HOST_UID=([0-9]+)[[:space:]]*$/\1/p' "$env_file" | tail -n 1)"
        host_gid="$(sed -n -E 's/^HOST_GID=([0-9]+)[[:space:]]*$/\1/p' "$env_file" | tail -n 1)"
        host_uid="''${host_uid:-1000}"
        host_gid="''${host_gid:-1000}"
        case "$host_uid$host_gid" in
          *[!0-9]*)
            echo "HOST_UID and HOST_GID must be numeric in $env_file" >&2
            exit 1
            ;;
        esac

        mkdir -p "$project_dir/ops-data/guac-revocation-spool" \
          "$project_dir/ops-data/winrm-certificates"

        for state_dir in \
          "$project_dir/certs" \
          "$project_dir/blockchain-data" \
          "$project_dir/fmu-access-state" \
          "$project_dir/lab-content" \
          "$project_dir/ops-data"
        do
          mkdir -p "$state_dir"
          chown -R "$host_uid:$host_gid" "$state_dir"
        done

        chmod 700 "$project_dir/certs" "$project_dir/blockchain-data" \
          "$project_dir/fmu-access-state" "$project_dir/ops-data" \
          "$project_dir/ops-data/guac-revocation-spool" \
          "$project_dir/ops-data/winrm-certificates"
        chmod 755 "$project_dir/lab-content"
      '';

      script = ''
        ${cfg.package}/bin/lab-gateway ${commonArgs} up -d${buildArg}${removeOrphansArg}
      '';

      preStop = ''
        ${cfg.package}/bin/lab-gateway ${commonArgs} down${removeVolumesArg}
      '';
    };
  };
}
