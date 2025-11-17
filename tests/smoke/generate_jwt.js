const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const header = { alg: "RS256", typ: "JWT" };
const payload = {
  sub: "smoke-user",
  jti: "smoke-jti-123",
  iss: "https://lab.test:18443/auth",
  aud: "https://lab.test:18443/guacamole",
  exp: 1893456000
};

function base64url(obj) {
  const json = typeof obj === "string" ? obj : JSON.stringify(obj);
  return Buffer.from(json).toString("base64url");
}

const signingInput = base64url(header) + "." + base64url(payload);
const keyPath = path.join(__dirname, "certs", "jwt-private.pem");
const key = fs.readFileSync(keyPath);
const signature = crypto
  .createSign("RSA-SHA256")
  .update(signingInput)
  .sign(key)
  .toString("base64url");

const outputPath = path.join(__dirname, "jwt.txt");
fs.writeFileSync(outputPath, signingInput + "." + signature);
