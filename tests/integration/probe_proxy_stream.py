#!/usr/bin/env python3
"""Probe a downloaded proxy.fmu through the public realtime WebSocket API.

This deliberately exercises the same session lifecycle used by the native
proxy runtime, but talks to the Gateway protocol directly so that streaming
events are visible in the terminal.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import ssl
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree


class ProxyProbeError(RuntimeError):
    """An actionable validation or protocol failure."""


@dataclass(frozen=True)
class ProxyMetadata:
    proxy_path: Path
    model_name: str
    fmi_version: str
    output_names: list[str]
    gateway_ws_url: str
    lab_id: str
    reservation_key: str
    session_ticket: str
    ticket_expires_at: float


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _required_string(config: dict[str, Any], name: str) -> str:
    value = str(config.get(name) or "").strip()
    if not value:
        raise ProxyProbeError(f"Falta '{name}' en resources/config.json")
    return value


def load_proxy_metadata(
    proxy_path: Path,
    now: float | None = None,
    *,
    validate_ticket: bool = True,
) -> ProxyMetadata:
    """Read and validate the non-secret metadata needed for a realtime probe."""

    proxy_path = Path(proxy_path).expanduser().resolve()
    if not proxy_path.is_file():
        raise ProxyProbeError(f"No existe el proxy FMU: {proxy_path}")

    try:
        with zipfile.ZipFile(proxy_path) as archive:
            names = set(archive.namelist())
            for required in ("modelDescription.xml", "resources/config.json"):
                if required not in names:
                    raise ProxyProbeError(f"El FMU no contiene {required}")
            if not any(
                name.startswith("binaries/") and name.rsplit("/", 1)[-1].startswith("decentralabs_proxy.")
                for name in names
            ):
                raise ProxyProbeError("El FMU no contiene el runtime decentralabs_proxy")

            try:
                root = ElementTree.fromstring(archive.read("modelDescription.xml"))
                config = json.loads(archive.read("resources/config.json"))
            except (ElementTree.ParseError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProxyProbeError(f"No se puede leer la metadata del proxy: {exc}") from exc
    except zipfile.BadZipFile as exc:
        raise ProxyProbeError(f"El fichero no es un archivo FMU/ZIP válido: {proxy_path}") from exc

    if not isinstance(config, dict):
        raise ProxyProbeError("resources/config.json no contiene un objeto JSON")

    model_name = str(root.attrib.get("modelName") or "").strip()
    fmi_version = str(root.attrib.get("fmiVersion") or "").strip()
    if not model_name or not fmi_version:
        raise ProxyProbeError("modelDescription.xml no declara modelName/fmiVersion")
    if not any(_local_name(element.tag) == "CoSimulation" for element in root):
        raise ProxyProbeError("El proxy no declara una interfaz Co-Simulation")

    output_names = [
        str(element.attrib["name"])
        for element in root.iter()
        if _local_name(element.tag) in {"Float32", "Float64", "Int8", "UInt8", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64", "Boolean", "String", "Binary", "Enumeration"}
        and str(element.attrib.get("causality") or "").lower() == "output"
        and element.attrib.get("name")
    ]
    if not output_names:
        raise ProxyProbeError("El proxy no declara ninguna salida FMI")

    gateway_ws_url = _required_string(config, "gatewayWsUrl")
    if not gateway_ws_url.startswith(("ws://", "wss://")):
        raise ProxyProbeError("gatewayWsUrl debe empezar por ws:// o wss://")
    session_ticket = _required_string(config, "sessionTicket")
    try:
        ticket_expires_at = float(config.get("ticketExpiresAt"))
    except (TypeError, ValueError) as exc:
        raise ProxyProbeError("ticketExpiresAt no es un timestamp válido") from exc
    if not math.isfinite(ticket_expires_at):
        raise ProxyProbeError("ticketExpiresAt no es finito")
    if validate_ticket and (now if now is not None else time.time()) >= ticket_expires_at:
        expires = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(ticket_expires_at))
        raise ProxyProbeError(
            f"El sessionTicket está caducado ({expires}). Descarga/genera un proxy nuevo."
        )

    return ProxyMetadata(
        proxy_path=proxy_path,
        model_name=model_name,
        fmi_version=fmi_version,
        output_names=output_names,
        gateway_ws_url=gateway_ws_url,
        lab_id=_required_string(config, "labId"),
        reservation_key=_required_string(config, "reservationKey"),
        session_ticket=session_ticket,
        ticket_expires_at=ticket_expires_at,
    )


def validate_stream_samples(samples: list[dict[str, Any]], output_names: list[str]) -> dict[str, Any]:
    """Validate monotonic streamed samples and return a compact report."""

    if not samples:
        raise ProxyProbeError("El Gateway no entregó ningún evento sim.outputs")

    previous_seq: int | None = None
    previous_time: float | None = None
    dropped = 0
    for sample in samples:
        if not isinstance(sample, dict):
            raise ProxyProbeError("El stream contiene un evento sim.outputs inválido")
        try:
            sequence = int(sample["seq"])
            simulation_time = float(sample["simTime"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProxyProbeError("Un evento sim.outputs no contiene seq/simTime válidos") from exc
        if previous_seq is not None and sequence <= previous_seq:
            raise ProxyProbeError("La secuencia del stream no es estrictamente creciente")
        if previous_time is not None and simulation_time <= previous_time:
            raise ProxyProbeError("El tiempo de simulación del stream no es creciente")
        values = sample.get("values")
        if not isinstance(values, dict):
            raise ProxyProbeError("Un evento sim.outputs no contiene values")
        for output_name in output_names:
            if output_name not in values:
                raise ProxyProbeError(f"Falta la salida {output_name} en un evento sim.outputs")
        try:
            dropped += max(0, int(sample.get("dropped", 0)))
        except (TypeError, ValueError) as exc:
            raise ProxyProbeError("El contador dropped del stream no es válido") from exc
        previous_seq = sequence
        previous_time = simulation_time

    return {
        "count": len(samples),
        "firstSequence": samples[0]["seq"],
        "lastSequence": samples[-1]["seq"],
        "firstTime": float(samples[0]["simTime"]),
        "lastTime": float(samples[-1]["simTime"]),
        "dropped": dropped,
        "outputNames": output_names,
        "firstValues": samples[0]["values"],
        "lastValues": samples[-1]["values"],
    }


def _request_id(counter: int) -> str:
    return f"probe-{counter:04d}-{uuid4().hex[:8]}"


async def _send_command(
    websocket: Any,
    message_type: str,
    payload: dict[str, Any],
    counter: int,
    events: list[dict[str, Any]],
    timeout: float,
) -> dict[str, Any]:
    request_id = _request_id(counter)
    await websocket.send(json.dumps({"type": message_type, "requestId": request_id, **payload}))
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProxyProbeError(f"Timeout esperando respuesta a {message_type}")
        raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
        try:
            response = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ProxyProbeError("El Gateway devolvió un mensaje WebSocket no JSON") from exc
        if not isinstance(response, dict):
            raise ProxyProbeError("El Gateway devolvió un mensaje WebSocket inválido")
        if response.get("requestId") == request_id:
            if response.get("type") == "error":
                code = response.get("code", "UNKNOWN")
                message = response.get("message", "sin detalle")
                raise ProxyProbeError(f"{message} [{code}]")
            return response
        events.append(response)


async def _receive_stream_samples(
    websocket: Any,
    events: list[dict[str, Any]],
    count: int,
    timeout: float,
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    deadline = time.monotonic() + timeout
    while len(samples) < count:
        if events:
            event = events.pop(0)
        else:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProxyProbeError(f"Solo llegaron {len(samples)}/{count} eventos sim.outputs")
            raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
            try:
                event = json.loads(raw)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ProxyProbeError("El stream devolvió un mensaje no JSON") from exc
        if not isinstance(event, dict):
            continue
        if event.get("type") == "error":
            raise ProxyProbeError(f"{event.get('message', 'Error en stream')} [{event.get('code', 'UNKNOWN')}]")
        if event.get("type") == "sim.outputs":
            samples.append(event)
    return samples


async def run_probe(
    metadata: ProxyMetadata,
    *,
    gateway_ws_url: str | None,
    session_ticket: str | None,
    lab_id: str | None,
    reservation_key: str | None,
    sample_count: int,
    stop_time: float,
    step_size: float,
    period_ms: int,
    timeout: float,
    insecure: bool,
) -> dict[str, Any]:
    try:
        import websockets
    except ImportError as exc:
        raise ProxyProbeError("Falta la dependencia 'websockets'. Ejecuta: python -m pip install websockets") from exc

    url = gateway_ws_url or metadata.gateway_ws_url
    ticket = session_ticket or metadata.session_ticket
    effective_lab_id = lab_id or metadata.lab_id
    effective_reservation_key = reservation_key or metadata.reservation_key
    ssl_context = None
    if url.startswith("wss://"):
        ssl_context = ssl.create_default_context()
        if insecure:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

    events: list[dict[str, Any]] = []
    counter = 0
    try:
        connect_kwargs: dict[str, Any] = {
            "open_timeout": timeout,
            "close_timeout": timeout,
            "max_size": 4 * 1024 * 1024,
        }
        if ssl_context is not None:
            connect_kwargs["ssl"] = ssl_context
        async with websockets.connect(url, **connect_kwargs) as websocket:
            counter += 1
            created = await _send_command(
                websocket,
                "session.create",
                {
                    "labId": effective_lab_id,
                    "reservationKey": effective_reservation_key,
                    "sessionTicket": ticket,
                },
                counter,
                events,
                timeout,
            )
            session_id = created.get("sessionId")
            if not session_id:
                raise ProxyProbeError("session.created no contiene sessionId")

            counter += 1
            described = await _send_command(websocket, "model.describe", {}, counter, events, timeout)
            if described.get("type") != "model.description":
                raise ProxyProbeError("La respuesta de model.describe no es model.description")

            counter += 1
            await _send_command(
                websocket,
                "sim.initialize",
                {"options": {"startTime": 0.0, "stopTime": stop_time, "stepSize": step_size, "timeMode": "simtime"}},
                counter,
                events,
                timeout,
            )

            counter += 1
            await _send_command(
                websocket,
                "sim.subscribeOutputs",
                {"variables": metadata.output_names, "periodMs": period_ms, "maxBatchSize": sample_count},
                counter,
                events,
                timeout,
            )

            counter += 1
            await _send_command(websocket, "sim.start", {}, counter, events, timeout)
            samples = await _receive_stream_samples(websocket, events, sample_count, timeout)
            stream_summary = validate_stream_samples(samples, metadata.output_names)

            counter += 1
            await _send_command(websocket, "sim.pause", {}, counter, events, timeout)
            counter += 1
            await _send_command(websocket, "session.terminate", {}, counter, events, timeout)

            return {
                "status": "PASS",
                "proxy": str(metadata.proxy_path),
                "modelName": metadata.model_name,
                "fmiVersion": metadata.fmi_version,
                "gatewayWsUrl": url,
                "labId": effective_lab_id,
                "sessionId": session_id,
                "stream": stream_summary,
            }
    except ProxyProbeError:
        raise
    except Exception as exc:
        hint = (
            " Usa --insecure si el gateway local usa un certificado autofirmado."
            if url.startswith("wss://") and not insecure
            else ""
        )
        raise ProxyProbeError(f"Falló la conexión/protocolo WebSocket: {exc}.{hint}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prueba el stream realtime de un proxy.fmu descargado.")
    parser.add_argument("proxy", type=Path, help="Ruta al proxy.fmu descargado")
    parser.add_argument("--gateway-ws-url", help="Sobrescribe gatewayWsUrl del proxy")
    parser.add_argument("--session-ticket", help="Sobrescribe el ticket embebido en el proxy")
    parser.add_argument("--lab-id", help="Sobrescribe labId del proxy")
    parser.add_argument("--reservation-key", help="Sobrescribe reservationKey del proxy")
    parser.add_argument("--samples", type=int, default=5, help="Eventos sim.outputs que se esperan (default: 5)")
    parser.add_argument("--stop-time", type=float, default=1.0)
    parser.add_argument("--step-size", type=float, default=0.01)
    parser.add_argument("--period-ms", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--insecure", action="store_true", help="Acepta certificados TLS autofirmados (solo local)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.samples < 1 or args.period_ms < 1 or args.step_size <= 0 or args.stop_time <= 0:
        print("ERROR: samples, period-ms, step-size y stop-time deben ser positivos", file=sys.stderr)
        return 2
    try:
        metadata = load_proxy_metadata(args.proxy, validate_ticket=not bool(args.session_ticket))
        print(json.dumps({
            "proxy": str(metadata.proxy_path),
            "modelName": metadata.model_name,
            "fmiVersion": metadata.fmi_version,
            "outputs": metadata.output_names,
            "gatewayWsUrl": args.gateway_ws_url or metadata.gateway_ws_url,
            "ticket": "present",
        }, indent=2, ensure_ascii=False))
        result = asyncio.run(run_probe(
            metadata,
            gateway_ws_url=args.gateway_ws_url,
            session_ticket=args.session_ticket,
            lab_id=args.lab_id,
            reservation_key=args.reservation_key,
            sample_count=args.samples,
            stop_time=args.stop_time,
            step_size=args.step_size,
            period_ms=args.period_ms,
            timeout=args.timeout,
            insecure=args.insecure,
        ))
    except ProxyProbeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print("PASS: session, model description, initialization and realtime output stream funcionan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
