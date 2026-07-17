import fs from 'node:fs';
import tls from 'node:tls';

const [host, portValue, servername] = process.argv.slice(2);
const port = Number(portValue);

if (!host || !servername || !Number.isInteger(port) || port < 1 || port > 65535) {
  process.stdout.write('000\n');
  process.exit(0);
}

let socket;
let timeout;
let completed = false;
let response = '';
const testCa = fs.readFileSync(new URL('./certs/fullchain.pem', import.meta.url));

function finish(status) {
  if (completed) return;
  completed = true;
  if (timeout) clearTimeout(timeout);
  if (socket && !socket.destroyed) socket.destroy();
  process.stdout.write(`${status}\n`);
}

socket = tls.connect(
  { host, port, servername, ca: testCa, rejectUnauthorized: true },
  () => {
    const cookie = process.env.SMOKE_WEBSOCKET_COOKIE;
    const request = [
      'GET /guacamole/websocket-tunnel?token=admin-token HTTP/1.1',
      `Host: ${servername}:${port}`,
      'Connection: Upgrade',
      'Upgrade: websocket',
      'Sec-WebSocket-Key: c21va2Uta2V5',
      'Sec-WebSocket-Version: 13',
      ...(cookie ? [`Cookie: ${cookie}`] : []),
      '',
      '',
    ].join('\r\n');
    socket.write(request);
  }
);

timeout = setTimeout(() => finish('000'), 2000);
socket.on('data', (chunk) => {
  response += chunk.toString('latin1');
  if (response.includes('\r\n')) {
    finish(/^HTTP\/1\.1 101(?:\s|$)/.test(response) ? '101' : '000');
  }
});
socket.on('end', () => finish(/^HTTP\/1\.1 101(?:\s|$)/.test(response) ? '101' : '000'));
socket.on('error', () => finish('000'));
