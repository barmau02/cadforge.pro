"""LLM hints for per-job FreeCAD document isolation."""

JOB_DOC_SUFFIX = """
IMPORTANT — document isolation:
- This design belongs ONLY to FreeCAD document "{doc_name}".
- Always start with: doc = App.getDocument("{doc_name}") or App.newDocument("{doc_name}")
- Never write to App.activeDocument() unless you first confirm it is "{doc_name}".
- When modifying, only remove/recreate objects inside document "{doc_name}".
"""


def job_doc_prompt_suffix(doc_name: str) -> str:
    return JOB_DOC_SUFFIX.format(doc_name=doc_name)