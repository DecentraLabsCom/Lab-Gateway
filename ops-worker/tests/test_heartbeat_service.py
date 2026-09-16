import json

import heartbeat_service


class Logger:
    def __init__(self):
        self.warning_calls = []
        self.error_calls = []
        self.debug_calls = []

    def warning(self, *args):
        self.warning_calls.append(args)

    def error(self, *args):
        self.error_calls.append(args)

    def debug(self, *args):
        self.debug_calls.append(args)


def test_poll_heartbeat_coordinates_reads_persistence_and_aas_sync():
    host = {
        "name": "lab-ws-01",
        "heartbeat_path": r"C:\heartbeat.json",
        "events_path": r"C:\events.jsonl",
        "labs": [101, 102],
    }
    heartbeat = {"summary": {"ready": True}}
    event = {"kind": "session-guard"}
    reads = {
        host["heartbeat_path"]: json.dumps(heartbeat),
        host["events_path"]: "{}\n" + json.dumps(event) + "\n",
    }
    persisted = []
    synced = []

    def read_remote_file(received_host, path, *_args):
        assert received_host is host
        return reads[path]

    def persist(engine, received_host, received_heartbeat, received_event):
        persisted.append((engine, received_host, received_heartbeat, received_event))

    def sync(lab_id, received_host, received_heartbeat):
        synced.append((lab_id, received_host, received_heartbeat))
        return {"disabled": True}

    result = heartbeat_service.poll_heartbeat(
        host,
        include_events=True,
        read_remote_file=read_remote_file,
        persist_heartbeat=persist,
        db_engine="db",
        sync_lab_to_basyx=sync,
        resolve_lab_ids_for_host=lambda _host: [101, 102],
        logger=Logger(),
        default_heartbeat_path="heartbeat-default",
        default_events_path="events-default",
    )

    assert result == {"heartbeat": heartbeat, "last_event": event}
    assert persisted == [("db", host, heartbeat, event)]
    assert synced == [("101", host, heartbeat)]


def test_poll_heartbeat_keeps_best_effort_failures_out_of_the_main_result():
    logger = Logger()
    host = {"name": "lab-ws-01", "labs": [101]}
    heartbeat = {"summary": {"ready": False}}

    def read_remote_file(_host, path, *_args):
        if path == "events-default":
            raise RuntimeError("events unavailable")
        return json.dumps(heartbeat)

    def persist(*_args):
        raise RuntimeError("database unavailable")

    def sync(*_args):
        raise RuntimeError("aas unavailable")

    result = heartbeat_service.poll_heartbeat(
        host,
        include_events=True,
        read_remote_file=read_remote_file,
        persist_heartbeat=persist,
        db_engine="db",
        sync_lab_to_basyx=sync,
        resolve_lab_ids_for_host=lambda _host: [101],
        logger=logger,
        default_heartbeat_path="heartbeat-default",
        default_events_path="events-default",
    )

    assert result == {"heartbeat": heartbeat, "last_event": None}
    assert len(logger.warning_calls) == 2
    assert len(logger.error_calls) == 1
