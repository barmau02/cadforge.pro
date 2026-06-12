"""CAD execution facade: headless FreeCADCmd (default) or GUI RPC."""
from __future__ import annotations

from typing import Any

import headless_freecad as hl
import jobs as job_store
from freecad_client import FreeCADClient


class HeadlessCad:
    """Subset of FreeCADClient used by CadForge when freecad_mode=headless."""

    def __init__(self, job_id: str | None = None):
        self._job_id = job_id

    def with_job(self, job_id: str | None) -> HeadlessCad:
        return HeadlessCad(job_id=job_id)

    def ping(self) -> bool:
        return hl.is_ready()

    def ping_health(self) -> bool:
        return self.ping()

    def execute_code(self, code: str) -> dict[str, Any]:
        return hl.run_script(code)

    def execute_job_code(self, code: str, doc_name: str, job_id: str) -> dict[str, Any]:
        wrapped = job_store.headless_wrap_code_for_job(code, doc_name, job_id)
        return hl.run_script(wrapped)

    def list_documents(self) -> list[str]:
        if not self._job_id:
            return []
        job = job_store.load_job(self._job_id)
        if not job:
            return []
        fcstd = job_store.job_fcstd_path(self._job_id, job["freecad_doc"])
        if fcstd.is_file() and fcstd.stat().st_size > 0:
            return [job["freecad_doc"]]
        return []

    def get_objects(self, doc_name: str) -> list[dict[str, Any]]:
        if not self._job_id:
            return []
        body = hl.introspect_objects_script(doc_name)
        script = job_store.headless_open_document_code(doc_name, self._job_id).strip() + "\n\n" + body
        result = hl.run_script(script)
        return hl.parse_objects_json(result)


_headless_singleton = HeadlessCad()


def headless_cad(job_id: str | None = None) -> HeadlessCad:
    if job_id:
        return _headless_singleton.with_job(job_id)
    return _headless_singleton


def resolve_cad(
    *,
    use_headless: bool,
    rpc_client: FreeCADClient,
    job_id: str | None = None,
) -> FreeCADClient | HeadlessCad:
    if use_headless:
        return headless_cad(job_id)
    if not rpc_client.ping_health():
        raise RuntimeError("FreeCAD RPC not running")
    return rpc_client


def activate_job(
    cad: FreeCADClient | HeadlessCad,
    job: dict[str, Any],
    *,
    use_headless: bool,
) -> dict[str, Any]:
    if use_headless:
        job_store.job_fcstd_dir(job["id"]).mkdir(parents=True, exist_ok=True)
        return {"success": True, "message": "Headless job workspace ready"}
    return job_store.activate_job_in_freecad(cad, job)  # type: ignore[arg-type]


def run_wrapped_code(
    cad: FreeCADClient | HeadlessCad,
    code: str,
    doc_name: str | None,
    job: dict[str, Any] | None,
    *,
    use_headless: bool,
) -> dict[str, Any]:
    if job and doc_name:
        if use_headless:
            return cad.execute_job_code(code, doc_name, job["id"])  # type: ignore[union-attr]
        wrapped = job_store.wrap_code_for_job(code, doc_name)
        return cad.execute_code(wrapped)
    return cad.execute_code(code)


def count_solids(
    cad: FreeCADClient | HeadlessCad,
    doc_name: str,
    job: dict[str, Any] | None,
    *,
    use_headless: bool,
) -> int | None:
    if use_headless and job:
        body = hl.count_solids_script(doc_name)
        script = job_store.headless_open_document_code(doc_name, job["id"]).strip() + "\n\n" + body
        result = hl.run_script(script)
    else:
        result = cad.execute_code(hl.count_solids_script(doc_name))
    return hl.parse_solid_count(result)
