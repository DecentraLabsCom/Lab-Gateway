{ dockerTools
, python3
, bash
, coreutils
, iputils
, cacert
}:

let
  pythonEnv = python3.withPackages (ps: with ps; [
    flask
    pywinrm
    requests
    requests-ntlm
    wakeonlan
    apscheduler
    sqlalchemy
    pymysql
    cryptography
    pytz
    tzlocal
    urllib3
    xmltodict
    ntlm-auth
  ]);
in
dockerTools.buildLayeredImage {
  name = "lab-gateway-ops-worker";
  tag = "nix";

  contents = [
    pythonEnv
    bash
    coreutils
    iputils
    cacert
  ];

  extraCommands = ''
    mkdir -p app
    cp ${../../ops-worker/worker.py} app/worker.py
  '';

  config = {
    WorkingDir = "/app";
    Env = [
      "PYTHONDONTWRITEBYTECODE=1"
      "PYTHONUNBUFFERED=1"
      "OPS_BIND=0.0.0.0"
      "OPS_PORT=8081"
      "OPS_CONFIG=/app/hosts.json"
      "SSL_CERT_FILE=${cacert}/etc/ssl/certs/ca-bundle.crt"
    ];
    Cmd = [ "${pythonEnv}/bin/python" "/app/worker.py" ];
  };
}
