{ writeShellApplication, docker, docker-compose }:

writeShellApplication {
  name = "lab-gateway";
  runtimeInputs = [ docker docker-compose ];
  text = ''
    set -euo pipefail

    project_dir="''${LAB_GATEWAY_PROJECT_DIR:-}"
    project_name="''${LAB_GATEWAY_PROJECT_NAME:-lab-gateway}"
    env_file="''${LAB_GATEWAY_ENV_FILE:-}"
    profiles=()

    usage() {
      cat <<'EOF'
Usage:
  lab-gateway [--project-dir DIR] [--project-name NAME] [--env-file FILE] [--profile NAME]... <compose-subcommand> [args...]

Examples:
  lab-gateway --project-dir . up -d --build
  lab-gateway --project-dir /srv/lab-gateway --env-file /srv/lab-gateway/.env logs -f openresty
EOF
    }

    while [[ $# -gt 0 ]]; do
      case "$1" in
        --project-dir)
          shift
          if [[ $# -eq 0 ]]; then
            echo "Missing value for --project-dir" >&2
            exit 1
          fi
          project_dir="$1"
          ;;
        --project-name)
          shift
          if [[ $# -eq 0 ]]; then
            echo "Missing value for --project-name" >&2
            exit 1
          fi
          project_name="$1"
          ;;
        --env-file)
          shift
          if [[ $# -eq 0 ]]; then
            echo "Missing value for --env-file" >&2
            exit 1
          fi
          env_file="$1"
          ;;
        --profile)
          shift
          if [[ $# -eq 0 ]]; then
            echo "Missing value for --profile" >&2
            exit 1
          fi
          profiles+=("$1")
          ;;
        -h|--help)
          usage
          exit 0
          ;;
        --)
          shift
          break
          ;;
        -*)
          echo "Unknown option: $1" >&2
          usage >&2
          exit 1
          ;;
        *)
          break
          ;;
      esac
      shift
    done

    if [[ $# -lt 1 ]]; then
      usage >&2
      exit 1
    fi

    if [[ -z "$project_dir" ]]; then
      project_dir="$(pwd)"
    fi

    compose_file="$project_dir/docker-compose.yml"
    if [[ ! -f "$compose_file" ]]; then
      echo "docker-compose.yml not found: $compose_file" >&2
      exit 1
    fi

    subcommand="$1"
    shift

    compose_cmd=()
    if docker compose version >/dev/null 2>&1; then
      compose_cmd=(docker compose)
    elif command -v docker-compose >/dev/null 2>&1; then
      compose_cmd=(docker-compose)
    else
      echo "Docker Compose not found (tried 'docker compose' and 'docker-compose')." >&2
      exit 1
    fi

    compose_args=(--project-name "$project_name")
    if [[ -n "$env_file" ]]; then
      compose_args+=(--env-file "$env_file")
    fi
    for profile in "''${profiles[@]}"; do
      compose_args+=(--profile "$profile")
    done
    compose_args+=(-f "$compose_file")

    exec "''${compose_cmd[@]}" "''${compose_args[@]}" "$subcommand" "$@"
  '';
}
