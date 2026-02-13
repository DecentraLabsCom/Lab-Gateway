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
          labGatewayOpenrestyImage = pkgs.callPackage ./nix/images/openresty-image.nix { };
          labGatewayBundleImage = pkgs.callPackage ./nix/images/gateway-bundle-image.nix { };
        in
        {
          default = labGatewayDocker;
          lab-gateway-docker = labGatewayDocker;
          lab-gateway-ops-worker-image = labGatewayOpsWorkerImage;
          lab-gateway-openresty-image = labGatewayOpenrestyImage;
          lab-gateway-bundle-image = labGatewayBundleImage;
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
        components-mysql = import ./nix/components/mysql.nix;
        components-guacd = import ./nix/components/guacd.nix;
        components-guacamole = import ./nix/components/guacamole.nix;
        components-blockchain-services = import ./nix/components/blockchain-services.nix;
        components-ops-worker = import ./nix/components/ops-worker.nix;
        components-openresty = import ./nix/components/openresty.nix;
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
