{
  description = "DecentraLabs Gateway flake (NixOS module and host configuration)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs, ... }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      formatter = forAllSystems (system:
        (import nixpkgs { inherit system; }).nixfmt-rfc-style
      );

      nixosModules = {
        default = import ./nix/nixos-module.nix;
        lab-gateway = self.nixosModules.default;
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

      };
    };
}
