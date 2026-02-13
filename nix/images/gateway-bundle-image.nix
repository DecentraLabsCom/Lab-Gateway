{ dockerTools
, stdenvNoCC
, lib
, bash
, coreutils
, docker
, docker-compose
, callPackage
}:

let
  gatewayCli = callPackage ../lab-gateway-docker.nix { };

  bundleSource = lib.cleanSourceWith {
    src = ../../.;
    filter = path: type:
      let
        rel = lib.removePrefix (toString ../../.) (toString path);
      in
      !(lib.hasInfix "/.git" rel || lib.hasInfix "/dist" rel || lib.hasInfix "/result" rel);
  };

  bundleFiles = stdenvNoCC.mkDerivation {
    pname = "lab-gateway-bundle-files";
    version = "1.0";
    src = bundleSource;
    dontConfigure = true;
    dontBuild = true;
    installPhase = ''
      mkdir -p $out/opt/lab-gateway
      cp -r . $out/opt/lab-gateway/
    '';
  };
in
dockerTools.buildLayeredImage {
  name = "lab-gateway-bundle";
  tag = "nix";

  contents = [
    bash
    coreutils
    docker
    docker-compose
    gatewayCli
    bundleFiles
  ];

  extraCommands = ''
    mkdir -p usr/local/bin
    cat > usr/local/bin/lab-gateway-bundle <<'EOF'
    #!/bin/sh
    set -eu
    project_dir="${LAB_GATEWAY_PROJECT_DIR:-/opt/lab-gateway}"
    exec ${gatewayCli}/bin/lab-gateway --project-dir "$project_dir" "$@"
    EOF
    chmod +x usr/local/bin/lab-gateway-bundle
  '';

  config = {
    WorkingDir = "/opt/lab-gateway";
    Entrypoint = [ "/usr/local/bin/lab-gateway-bundle" ];
  };
}
