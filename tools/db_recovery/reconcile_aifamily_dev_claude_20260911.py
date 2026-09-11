"""One-off R0 drift reconciliation; only explicitly named rehearsal databases.

Requires the read-only source_before.json evidence snapshot recorded by
FAMILY-R0-DB-DRIFT-001A. No source connection, CREATE DATABASE or stamp exists
in this script. Every existing migration upgrade runs in its own transaction
with full pre/post schema and original-row projection verification.

Run with uv run python tools/db_recovery/reconcile_aifamily_dev_claude_20260911.py
--baseline-snapshot <source_before.json> [--apply]. The target URL is read only
from AIFAMILY_REHEARSAL_DATABASE_URL and must name a timestamped rehearsal.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import re
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

REPOSITORY_HEAD = "7e3041b53b98f7fd847810ad2d87d590af753080"

EXPECTED_HEAD = "0079_platform_notification_control_plane"

SOURCE_SCHEMA_HASH = "5a2ca02256e72169d73497441796ae270d8de49ffa0deffc15ff2b4643f77a29"

SOURCE_DATA_HASH = "75258e7f61971b60dc97cd6a6c653a0858524d518a551bcb6f349589dcd73c4f"

STEPS = [
    "0067_service_feedback_playbook",
    "0068_reviewed_understanding_signal",
    "0070_service_cases_scope_refs_string",
    "0071_identity_sessions_family_scope_ref",
    "0072_growth_hypothesis_decision_partial_edit_later",
    "0077_journey_adopted_growth_plans",
    "0078_ai_feedback_regression_jobs",
    "0079_platform_notification_control_plane",
]

STAGE_HASHES = [
    "5a2ca02256e72169d73497441796ae270d8de49ffa0deffc15ff2b4643f77a29",
    "8986a49eccd62e522a65171ab6102fe9aef5c622f70262d3f9965aaac24a9c28",
    "5c50eecf45cffad738960c0320afab5d90f6751517f13e8807266523e089e730",
    "cb98e70804764f5779486d13178479fda828beba06bf7ba94ccbfe9861a1f59c",
    "5f8871d6f13822be06c64c7432af9f89c8c3e003a96d906d314de26dc1d96700",
    "bc5df6ddb34bea41b468c9bdd36c4160a6f1052f362a8ab8f2fe6664ddab71e2",
    "580bb4e0bc6b9d2052f9d706b89304ed03a36ed5908e34fe48975c7818eb3806",
    "08c3e9e88de3fc3c9b315a8a1f2e77a1ae344e0b4ef2e8ff6d8b0c73b64cb898",
    "2437f8af0545d4b22247a472155e08bb40db30c52da11328a3a4cda145b0c3f4",
]

MIGRATION_SHA256 = {
    "0067": "bc75bdc99803b0241641dadcba06bde253636597390632e903f2de43ba177655",
    "0068": "a1154a5ad74ff6aa719b45f2a1160033f52c5c723353dd74ec5ab88d4e16e0d8",
    "0070": "40e94480a07ebeed7aad9106af040e36edec9605aee14c61a6c5a12c94c6c7bb",
    "0071": "2154d4b58ff927b049c257d056cb798667174ec7061399a1f737000136fc877d",
    "0072": "ccdd9a2abf806f4b338f911807cb58847b18119d529997d4bbdecfca23e73d8e",
    "0077": "fdc7e20966b578053d7de3190fde90ba880bfe92c6bc74d0e2dce3559800c46a",
    "0078": "fdebba9ba143c4b6008dcb0f94913aaf457644e9fa3f81bd951eacd99e657b6d",
    "0079": "2cb002312846660c4d821285532fb414aaa7d8427e1eb900254f4aa92a0a1ff4",
}

QUERIES = {
    "relations": (
        "select n.nspname as schema, c.relname as name, c.relkind::text as kind, "
        "c.relpersistence::text as persistence, c.relrowsecurity as rls, "
        "c.relforcerowsecurity as force_rls, c.reloptions as options from pg_class c "
        "join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and "
        "c.relkind in ('r','p','v','m','S') order by 1,2 "
    ),
    "columns": (
        "select n.nspname as schema,c.relname as relation,a.attname as name, "
        "format_type(a.atttypid,a.atttypmod) as type,a.attnotnull as not_null, "
        "pg_get_expr(d.adbin,d.adrelid) as default_expr,a.attidentity::text as "
        "identity, a.attgenerated::text as generated,co.collname as collation from "
        "pg_attribute a join pg_class c on c.oid=a.attrelid join pg_namespace n on "
        "n.oid=c.relnamespace left join pg_attrdef d on d.adrelid=c.oid and "
        "d.adnum=a.attnum left join pg_collation co on co.oid=a.attcollation where "
        "n.nspname='public' and c.relkind in ('r','p','v','m') and a.attnum>0 and not "
        "a.attisdropped order by 1,2,3 "
    ),
    "constraints": (
        "select n.nspname as schema,c.relname as relation,con.conname as name, "
        "con.contype::text as kind,pg_get_constraintdef(con.oid,true) as definition, "
        "con.convalidated as validated,con.condeferrable as "
        "deferrable,con.condeferred as deferred from pg_constraint con join pg_class "
        "c on c.oid=con.conrelid join pg_namespace n on n.oid=c.relnamespace where "
        "n.nspname='public' order by 1,2,3 "
    ),
    "indexes": (
        "select n.nspname as schema,c.relname as relation,ic.relname as name, "
        "pg_get_indexdef(i.indexrelid) as definition,i.indisvalid as "
        "valid,i.indisready as ready, i.indisunique as unique_index,i.indisprimary as "
        "primary_index from pg_index i join pg_class c on c.oid=i.indrelid join "
        "pg_class ic on ic.oid=i.indexrelid join pg_namespace n on "
        "n.oid=c.relnamespace where n.nspname='public' order by 1,2,3 "
    ),
    "enums": (
        "select n.nspname as schema,t.typname as name, array_agg(e.enumlabel order by "
        "e.enumsortorder) as labels from pg_type t join pg_namespace n on "
        "n.oid=t.typnamespace join pg_enum e on e.enumtypid=t.oid where "
        "n.nspname='public' group by 1,2 order by 1,2 "
    ),
    "triggers": (
        "select n.nspname as schema,c.relname as relation,t.tgname as name, "
        "pg_get_triggerdef(t.oid,true) as definition,t.tgenabled::text as enabled "
        "from pg_trigger t join pg_class c on c.oid=t.tgrelid join pg_namespace n on "
        "n.oid=c.relnamespace where n.nspname='public' and not t.tgisinternal order "
        "by 1,2,3 "
    ),
    "views": (
        "select schemaname as schema,viewname as name,definition from pg_views where "
        "schemaname='public' order by 1,2 "
    ),
    "functions": (
        "select n.nspname as schema,p.proname as name, "
        "pg_get_function_identity_arguments(p.oid) as "
        "arguments,pg_get_functiondef(p.oid) as definition from pg_proc p join "
        "pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and "
        "p.prokind in ('f','p') order by 1,2,3 "
    ),
    "sequences": (
        "select schemaname as schema,sequencename as name,data_type::text, "
        "start_value,min_value,max_value,increment_by,cycle,cache_size from "
        "pg_sequences where schemaname='public' order by 1,2 "
    ),
    "policies": (
        "select schemaname as schema,tablename as relation,policyname as name, "
        "permissive,roles,cmd,qual,with_check from pg_policies where "
        "schemaname='public' order by 1,2,3 "
    ),
    "extensions": ("select extname as name,extversion as version from pg_extension order by 1 "),
    "schemas": (
        "select nspname as name from pg_namespace where nspname not like 'pg_%' and "
        "nspname<>'information_schema' order by 1 "
    ),
}

LITERAL = r"'(?:[^']|'')*'"
VARCHAR_LITERAL = LITERAL + r"::character varying"
ARRAY_BODY = VARCHAR_LITERAL + r"(?:, " + VARCHAR_LITERAL + r")*"
ARRAY_CAST = re.compile(
    r"(?:\(ARRAY\[(" + ARRAY_BODY + r")\]\)|ARRAY\[(" + ARRAY_BODY + r")\])::text\[\]"
)
ELEMENT_CAST = re.compile(r"(?:\((" + VARCHAR_LITERAL + r")\)|(" + VARCHAR_LITERAL + r"))::text")


def normalize_definition(value):
    # Only lossless casts from unbounded varchar literal arrays to text[] are
    # equivalent to casting each literal to text. Preserve labels and order.
    value = ARRAY_CAST.sub(
        lambda m: "ARRAY[" + re.sub(r"::character varying", "::text", m[1] or m[2]) + "]", value
    )
    return ELEMENT_CAST.sub(
        lambda m: (m[1] or m[2]).replace("::character varying", "::text"), value
    )


def normalize(schema):
    result = copy.deepcopy(schema)
    for category in ("constraints", "indexes"):
        for row in result[category]:
            row["definition"] = normalize_definition(row["definition"])
    return {
        k: sorted(v, key=lambda row: json.dumps(row, sort_keys=True)) for k, v in result.items()
    }


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def inspect_schema(connection):
    return {
        name: [dict(row) for row in connection.exec_driver_sql(query).mappings()]
        for name, query in QUERIES.items()
    }


def original_data(connection, baseline):
    result = {}
    for table in baseline["data"]:
        if table == "alembic_version":
            continue
        columns = sorted(c["name"] for c in baseline["schema"]["columns"] if c["relation"] == table)
        column_sql = ",".join('"' + c.replace('"', '""') + '"' for c in columns)
        quoted = '"' + table.replace('"', '""') + '"'
        query = (
            "SELECT count(*) AS rows, "
            "md5(coalesce(string_agg(h,'' ORDER BY h),'')) AS content_md5 "
            "FROM (SELECT md5(row_to_json(q)::text) h FROM "
            f"(SELECT {column_sql} FROM public.{quoted}) q) r"
        )
        result[table] = dict(connection.exec_driver_sql(query).mappings().one())
    return result


def inspect(connection, baseline):
    physical = digest(normalize(inspect_schema(connection)))
    if physical not in STAGE_HASHES:
        raise RuntimeError("UNKNOWN_PHYSICAL_STATE: stop without repair")
    data_hash = digest(original_data(connection, baseline))
    if data_hash != SOURCE_DATA_HASH:
        raise RuntimeError("ORIGINAL_DATA_CHANGED: stop without repair")
    revision = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
    if revision not in {"0069_ai_run_ledger", EXPECTED_HEAD}:
        raise RuntimeError("UNKNOWN_BOOKKEEPING_STATE: stop without repair")
    stage = STAGE_HASHES.index(physical)
    if revision == EXPECTED_HEAD and stage != len(STEPS):
        raise RuntimeError("PREMATURE_STAMP: stop without repair")
    return {
        "stage": stage,
        "schema_sha256": physical,
        "data_sha256": data_hash,
        "revision": revision,
    }


def repair_step(connection, baseline, index):
    if not connection.exec_driver_sql(
        "SELECT pg_try_advisory_xact_lock(hashtext('family-r0-rehearsal-recovery'))"
    ).scalar_one():
        raise RuntimeError("RECOVERY_ALREADY_RUNNING")
    before = inspect(connection, baseline)
    if before["stage"] != index:
        raise RuntimeError("CONCURRENT_STATE_CHANGE")
    root = Path(__file__).resolve().parents[2]
    revision = ScriptDirectory(str(root / "database/migrations")).get_revision(STEPS[index])
    if (
        hashlib.sha256(Path(revision.path).read_bytes()).hexdigest()
        != MIGRATION_SHA256[STEPS[index][:4]]
    ):
        raise RuntimeError("MIGRATION_SOURCE_CHANGED")
    module = revision.module
    with Operations.context(MigrationContext.configure(connection)):
        module.upgrade()
    after = inspect(connection, baseline)
    if after["stage"] != index + 1 or after["revision"] != before["revision"]:
        raise RuntimeError("POSTCONDITION_FAILED: transaction rolls back")
    return {"migration": STEPS[index], "before": before, "after": after}


async def main(args):
    url = make_url(os.environ["AIFAMILY_REHEARSAL_DATABASE_URL"])
    if (
        url.get_backend_name() != "postgresql"
        or url.host != "127.0.0.1"
        or url.port != 55442
        or not re.fullmatch(r"aifamily_dev_claude_rehearsal_[0-9]{14}", url.database or "")
    ):
        raise RuntimeError("TARGET_NOT_APPROVED_REHEARSAL: no connection attempted")
    baseline = json.loads(args.baseline_snapshot.read_text(encoding="utf-8"))
    if digest(normalize(baseline["schema"])) != SOURCE_SCHEMA_HASH:
        raise RuntimeError("BASELINE_SCHEMA_MISMATCH")
    data = {k: v for k, v in baseline["data"].items() if k != "alembic_version"}
    if digest(data) != SOURCE_DATA_HASH:
        raise RuntimeError("BASELINE_DATA_MISMATCH")
    engine = create_async_engine(
        url,
        poolclass=NullPool,
        connect_args={
            "server_settings": {
                "lock_timeout": "2000",
                "statement_timeout": "30000",
                "timezone": "UTC",
            }
        },
    )
    try:
        async with engine.connect() as connection:
            actual_database = await connection.run_sync(
                lambda c: c.exec_driver_sql("SELECT current_database()").scalar_one()
            )
            if actual_database != url.database:
                raise RuntimeError("DATABASE_IDENTITY_MISMATCH")
            state = await connection.run_sync(inspect, baseline)
        print(encoded({"database": actual_database, "inspection": state}), flush=True)
        if args.apply:
            for index in range(state["stage"], len(STEPS)):
                async with engine.begin() as connection:
                    receipt = await connection.run_sync(repair_step, baseline, index)
                print(encoded({"committed": receipt}), flush=True)
        async with engine.connect() as connection:
            final = await connection.run_sync(inspect, baseline)
        print(encoded({"final": final, "stamp_performed": False}), flush=True)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-snapshot", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args()))
