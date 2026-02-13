{
  description = "DecentraLabs Gateway flake (Docker helpers, OCI images, and NixOS modules)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs, ... }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      packages = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          labGatewayDocker = pkgs.callPackage ./nix/lab-gateway-docker.nix { };
          labGatewayOpsWorkerImage = pkgs.callPackage ./nix/images/ops-worker-image.nix { };
        in
        {
          default = labGatewayDocker;
          lab-gateway-docker = labGatewayDocker;
          lab-gateway-ops-worker-image = labGatewayOpsWorkerImage;
        });

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.lab-gateway-docker}/bin/lab-gateway";
        };
        lab-gateway-docker = {
          type = "app";
          program = "${self.packages.${system}.lab-gateway-docker}/bin/lab-gateway";
        };
      });

      formatter = forAllSystems (system:
        (import nixpkgs { inherit system; }).nixfmt-rfc-style
      );

      nixosModules = {
        default = import ./nix/nixos-module.nix;
        lab-gateway = self.nixosModules.default;
        components = import ./nix/nixos-components-module.nix;
        gateway-host = import ./nix/hosts/gateway.nix;
      };

      nixosConfigurations = {
        gateway = nixpkgs.lib.nixosSystem {
          system = "x86_64-linux";
          modules = [
            (if builtins.pathExists "/etc/nixos/configuration.nix"
             then /etc/nixos/configuration.nix
             else ({ ... }: {
               # Fallback only for evaluation outside a NixOS host.
               boot.isContainer = true;
               fileSystems."/" = {
                 device = "none";
                 fsType = "tmpfs";
               };
             }))
            self.nixosModules.default
            self.nixosModules.gateway-host
          ];
        };

        gateway-components = nixpkgs.lib.nixosSystem {
          system = "x86_64-linux";
          modules = [
            (if builtins.pathExists "/etc/nixos/configuration.nix"
             then /etc/nixos/configuration.nix
             else ({ ... }: {
               boot.isContainer = true;
               fileSystems."/" = {
                 device = "none";
                 fsType = "tmpfs";
               };
             }))
            self.nixosModules.default
            self.nixosModules.components
            self.nixosModules.gateway-host
            ({ lib, ... }: {
              services.lab-gateway.enable = lib.mkForce false;
              services.lab-gateway-components.enable = true;
            })
          ];
        };
      };
    };
}
