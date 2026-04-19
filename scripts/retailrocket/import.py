#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import clickhouse_connect

CHUNK_SIZE = 500_000
EXPECTED_FILES = (
    "events.csv",
    "item_properties_part1.csv",
    "item_properties_part2.csv",
    "category_tree.csv",
)


@dataclass(frozen=True)
class SourceFile:
    path: Path
    name: str
    size: int


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ms_to_iso8601(ms_value: str) -> str:
    dt = datetime.fromtimestamp(int(ms_value) / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def must_env(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    if not value:
        raise ValueError(f"Environment variable {name} is empty")
    return value


def get_source_files(data_dir: Path) -> tuple[SourceFile, ...]:
    files: list[SourceFile] = []
    for file_name in EXPECTED_FILES:
        file_path = data_dir / file_name
        if not file_path.is_file():
            raise FileNotFoundError(f"Missing required file: {file_path}")
        files.append(SourceFile(path=file_path, name=file_name, size=file_path.stat().st_size))
    return tuple(files)


def compute_load_batch_id(files: tuple[SourceFile, ...]) -> str:
    batch_fingerprint = "|".join(f"{f.name}:{f.size}" for f in files)
    return sha256_hex(batch_fingerprint)[:16]


def connect_client():
    return clickhouse_connect.get_client(
        host=must_env("CLICKHOUSE_HOST", "localhost"),
        port=int(must_env("CLICKHOUSE_PORT", "8123")),
        username=must_env("CLICKHOUSE_USER", "analytics"),
        password=must_env("CLICKHOUSE_PASSWORD", "analytics_password"),
        database="retailrocket_raw",
    )


def ensure_schema(client) -> None:
    schema_path = Path("infra/clickhouse/sql/003_retailrocket_schema.sql")
    if not schema_path.is_file():
        raise FileNotFoundError(f"Schema file missing: {schema_path}")
    ddl = schema_path.read_text(encoding="utf-8")
    for statement in [s.strip() for s in ddl.split(";") if s.strip()]:
        client.command(statement)


def batch_already_loaded(client, load_batch_id: str) -> bool:
    result = client.query(
        f"SELECT count() FROM retailrocket_raw.events WHERE load_batch_id = '{load_batch_id}' LIMIT 1"
    )
    return int(result.result_rows[0][0]) > 0


def insert_chunk(client, table: str, columns: list[str], rows: list[list], dedup_token: str) -> None:
    client.insert(
        table=table,
        column_names=columns,
        data=rows,
        settings={"insert_deduplication_token": dedup_token},
    )


def ingest_file(
    client,
    table: str,
    columns: list[str],
    source_file: SourceFile,
    load_batch_id: str,
    row_transformer: Callable[[dict[str, str], str, str, int], list],
) -> int:
    inserted = 0
    chunk_index = 0
    chunk_rows: list[list] = []
    source_name = source_file.name

    with source_file.path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for line_idx, row in enumerate(reader, start=2):
            row_hash_basis = f"{source_name}:{line_idx}:{'|'.join((row.get(k) or '') for k in reader.fieldnames or [])}"
            row_hash = sha256_hex(row_hash_basis)
            chunk_rows.append(row_transformer(row, row_hash, load_batch_id, line_idx))

            if len(chunk_rows) >= CHUNK_SIZE:
                token = f"{load_batch_id}:{table}:{source_name}:{chunk_index}"
                insert_chunk(client, table, columns, chunk_rows, token)
                inserted += len(chunk_rows)
                chunk_rows = []
                chunk_index += 1
                logging.info("Inserted %s rows into %s from %s", inserted, table, source_name)

    if chunk_rows:
        token = f"{load_batch_id}:{table}:{source_name}:{chunk_index}"
        insert_chunk(client, table, columns, chunk_rows, token)
        inserted += len(chunk_rows)

    logging.info("Finished %s => %s rows into %s", source_name, inserted, table)
    return inserted


def transform_events(row: dict[str, str], row_hash: str, load_batch_id: str, source_row_num: int) -> list:
    tx_raw = (row.get("transactionid") or "").strip()
    tx_value = int(tx_raw) if tx_raw else None
    return [
        ms_to_iso8601(row["timestamp"]),
        int(row["visitorid"]),
        int(row["itemid"]),
        row["event"],
        tx_value,
        row_hash,
        load_batch_id,
        "events.csv",
        source_row_num,
    ]


def transform_item_properties(source_name: str) -> Callable[[dict[str, str], str, str, int], list]:
    def _inner(row: dict[str, str], row_hash: str, load_batch_id: str, source_row_num: int) -> list:
        return [
            ms_to_iso8601(row["timestamp"]),
            int(row["itemid"]),
            row["property"],
            row["value"],
            row_hash,
            load_batch_id,
            source_name,
            source_row_num,
        ]

    return _inner


def transform_category_tree(row: dict[str, str], row_hash: str, load_batch_id: str, source_row_num: int) -> list:
    parent_raw = (row.get("parentid") or "").strip()
    parent_value = int(parent_raw) if parent_raw else None
    return [
        int(row["categoryid"]),
        parent_value,
        row_hash,
        load_batch_id,
        "category_tree.csv",
        source_row_num,
    ]


def validate_event_distribution(client) -> None:
    result = client.query(
        """
        SELECT event_type, count()
        FROM retailrocket_raw.events
        GROUP BY event_type
        ORDER BY event_type
        """
    )
    observed = {k: int(v) for k, v in result.result_rows}
    expected = {
        "addtocart": 69332,
        "transaction": 22457,
        "view": 2664312,
    }
    if observed != expected:
        raise RuntimeError(f"Unexpected event distribution: observed={observed}, expected={expected}")


def validate_row_totals(client) -> None:
    totals = {
        "events": 2_756_101,
        "item_properties": 20_275_902,
        "category_tree": 1_669,
    }
    for table, expected in totals.items():
        result = client.query(f"SELECT count() FROM retailrocket_raw.{table}")
        actual = int(result.result_rows[0][0])
        if actual != expected:
            raise RuntimeError(f"Row count mismatch for {table}: expected={expected}, actual={actual}")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    started = time.time()

    data_dir = Path(os.getenv("RETAILROCKET_DATA_DIR", "data/retailrocket"))
    source_files = get_source_files(data_dir)
    load_batch_id = compute_load_batch_id(source_files)

    logging.info("Starting Retailrocket import with load_batch_id=%s", load_batch_id)

    client = connect_client()
    ensure_schema(client)

    if batch_already_loaded(client, load_batch_id):
        logging.info("Batch already loaded (load_batch_id=%s). Exiting without inserts.", load_batch_id)
        return 0

    events_file = next(f for f in source_files if f.name == "events.csv")
    item_p1 = next(f for f in source_files if f.name == "item_properties_part1.csv")
    item_p2 = next(f for f in source_files if f.name == "item_properties_part2.csv")
    category_file = next(f for f in source_files if f.name == "category_tree.csv")

    events_cols = [
        "event_time",
        "visitor_id",
        "item_id",
        "event_type",
        "transaction_id",
        "row_hash",
        "load_batch_id",
        "source_file",
        "source_row_num",
    ]
    props_cols = [
        "event_time",
        "item_id",
        "property",
        "value",
        "row_hash",
        "load_batch_id",
        "source_file",
        "source_row_num",
    ]
    category_cols = [
        "category_id",
        "parent_id",
        "row_hash",
        "load_batch_id",
        "source_file",
        "source_row_num",
    ]

    ingest_file(client, "retailrocket_raw.events", events_cols, events_file, load_batch_id, transform_events)
    ingest_file(
        client,
        "retailrocket_raw.item_properties",
        props_cols,
        item_p1,
        load_batch_id,
        transform_item_properties("item_properties_part1.csv"),
    )
    ingest_file(
        client,
        "retailrocket_raw.item_properties",
        props_cols,
        item_p2,
        load_batch_id,
        transform_item_properties("item_properties_part2.csv"),
    )
    ingest_file(
        client,
        "retailrocket_raw.category_tree",
        category_cols,
        category_file,
        load_batch_id,
        transform_category_tree,
    )

    validate_row_totals(client)
    validate_event_distribution(client)

    elapsed = round(time.time() - started, 2)
    logging.info("Retailrocket import completed successfully in %ss", elapsed)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # pragma: no cover
        logging.exception("Import failed: %s", exc)
        sys.exit(1)
