#!/bin/sh
set -eu

test -s /run/e2e/gateway.pub
public_key=$(cat /run/e2e/gateway.pub)
case "$public_key" in
    'ssh-ed25519 '*) ;;
    *) echo 'E2E key must be Ed25519' >&2; exit 2 ;;
esac

printf '%s\n' "restrict,command=\"/usr/local/sbin/labstation-ssh-dispatcher-wrapper\" $public_key" \
    > /etc/ssh/authorized_keys/labstation-ops
chmod 0644 /etc/ssh/authorized_keys/labstation-ops
chown root:root /etc/ssh/authorized_keys/labstation-ops

cat > /etc/decentralabs/lab-station/station.toml <<'CONFIG'
[station]
name = "linux-station-e2e"
profile = "dedicated"
version = "0.1.0"
state_dir = "/var/lib/decentralabs/lab-station/data"
config_dir = "/etc/decentralabs/lab-station"
log_dir = "/var/log/decentralabs/lab-station"
management_user = "labstation-ops"
management_port = 2222
transport = "ssh"
supervisor = "auto"
guard_grace_seconds = 0
allow_local_session_eviction = false

[application]
id = "lab-app"
command = ""
args = []
user = "labuser"
close_timeout_seconds = 15
CONFIG
chmod 0644 /etc/decentralabs/lab-station/station.toml

# OpenSSH rejects public-key logins for shadow-locked accounts on Ubuntu.
# Keep the test account unlocked with an unguessable password while password
# authentication remains disabled in sshd_config.
test_password=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
usermod --password "$(openssl passwd -6 "$test_password")" labstation-ops
unset test_password

ssh-keygen -A
install -d -m 0755 /run/sshd
cat > /etc/ssh/sshd_config <<'SSH'
Port 2222
HostKey /etc/ssh/ssh_host_ed25519_key
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
AuthenticationMethods publickey
AuthorizedKeysFile /etc/ssh/authorized_keys/%u
PermitRootLogin no
AllowUsers labstation-ops
PermitTTY no
PermitUserEnvironment no
PermitUserRC no
AllowTcpForwarding no
AllowAgentForwarding no
X11Forwarding no
PermitTunnel no
UsePAM no
SSH
/usr/sbin/sshd -t
exec /usr/sbin/sshd -D -e
