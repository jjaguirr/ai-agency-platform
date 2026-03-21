"""
Lightweight mutation testing for n8n integration modules.

Applies targeted mutations to source files, runs the corresponding test file,
and verifies the tests catch the mutation (i.e., at least one test fails).
A surviving mutant means the tests are too weak for that code path.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def _run_tests(test_file: str) -> bool:
    """Run a test file, return True if all tests pass."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_file, "-x", "-q", "--tb=no", "--timeout=10"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _mutate_and_test(
    src_file: Path,
    test_file: str,
    original: str,
    mutant: str,
    label: str,
) -> dict:
    """Apply a mutation, run tests, restore. Returns result dict."""
    content = src_file.read_text()
    if original not in content:
        return {"label": label, "status": "SKIPPED", "reason": "pattern not found"}

    mutated = content.replace(original, mutant, 1)
    src_file.write_text(mutated)
    try:
        tests_pass = _run_tests(test_file)
    finally:
        src_file.write_text(content)

    if tests_pass:
        return {"label": label, "status": "SURVIVED", "reason": "tests still pass with mutation"}
    return {"label": label, "status": "KILLED"}


def main():
    mutations = [
        # --- models.py ---
        (SRC / "integrations/n8n/models.py", "tests/unit/test_workflow_ir.py", [
            ("required: bool = True", "required: bool = False", "ParameterSpec.required default flipped"),
            ("default: str | None = None", 'default: str | None = "bogus"', "ParameterSpec.default changed"),
        ]),
        # --- config.py ---
        (SRC / "integrations/n8n/config.py", "tests/unit/test_n8n_client.py", [
            ('"base_url": self.base_url', '"base_url": "WRONG"', "Config save corrupts base_url"),
            ('return cls(base_url=data["base_url"], api_key=data["api_key"])', 'return cls(base_url=data["api_key"], api_key=data["base_url"])', "Config load swaps fields"),
            ("return None", 'return cls(base_url="", api_key="")', "Config load returns empty instead of None"),
        ]),
        # --- client.py ---
        (SRC / "integrations/n8n/client.py", "tests/unit/test_n8n_client.py", [
            ('resp.status_code >= 400', 'resp.status_code >= 500', "Client ignores 4xx errors"),
            ('"X-N8N-API-KEY": config.api_key', '"X-N8N-API-KEY": "wrong"', "Client sends wrong API key"),
            ('"/api/v1/workflows"', '"/api/v2/workflows"', "Client uses wrong API path"),
            ("return resp.json().get(\"data\", [])", "return resp.json()", "list_workflows returns raw response"),
            ('f"/api/v1/workflows/{workflow_id}/activate"', 'f"/api/v1/workflows/{workflow_id}/deactivate"', "activate calls deactivate endpoint"),
            ('"DELETE"', '"POST"', "delete sends POST instead of DELETE"),
        ]),
        # --- renderer.py ---
        (SRC / "integrations/n8n/renderer.py", "tests/unit/test_n8n_renderer.py", [
            ('kind == "cron"', 'kind == "webhook"', "Renderer swaps cron/webhook trigger mapping"),
            ("name=definition.name", 'name="WRONG"', "Renderer ignores definition name"),
            ("connections[prev] = ", "# connections[prev] = ", "Renderer skips wiring connections"),
        ]),
        # --- catalog.py ---
        (SRC / "integrations/n8n/catalog.py", "tests/unit/test_workflow_catalog.py", [
            ("if hits > 0:", "if hits > 999:", "Catalog never returns results"),
            ("scored.sort(key=lambda x: x[0], reverse=True)", "scored.sort(key=lambda x: x[0], reverse=False)", "Catalog sorts ascending instead of descending"),
            ("_CACHE_TTL_SECONDS = 300", "_CACHE_TTL_SECONDS = 0", "Community cache TTL disabled"),
            ("_MAX_RESULTS = 10", "_MAX_RESULTS = 0", "Catalog max results set to 0"),
        ]),
        # --- customizer.py ---
        (SRC / "integrations/n8n/customizer.py", "tests/unit/test_workflow_customizer.py", [
            ("if spec.required and name not in applied", "if not spec.required and name not in applied", "Customizer inverts missing param logic"),
            ("return params[key]", 'return "WRONG"', "Customizer substitutes wrong value"),
            ("effective[name] = spec.default", 'effective[name] = "WRONG_DEFAULT"', "Customizer uses wrong default"),
            ("new_trigger = TriggerNode(kind=template.trigger.kind, config=new_trigger_config)", "new_trigger = TriggerNode(kind='webhook', config=new_trigger_config)", "Customizer corrupts trigger kind"),
        ]),
        # --- tracking.py ---
        (SRC / "integrations/n8n/tracking.py", "tests/unit/test_workflow_tracking.py", [
            ('f"customer_workflows:{customer_id}"', 'f"customer_workflows:GLOBAL"', "Tracker ignores customer isolation"),
            ("wf.status = status", "pass", "update_status is a no-op"),
            ("await self._r.hdel", "# await self._r.hdel", "remove is a no-op"),
            ("q in wf.name.lower()", "q not in wf.name.lower()", "find_by_name inverts match logic"),
        ]),
        # --- workflow specialist ---
        (SRC / "agents/specialists/workflow.py", "tests/unit/test_workflow_specialist.py", [
            ("confidence += 0.60", "confidence += 0.0", "Specialist unambiguous boost removed"),
            ("                    confidence -= _DAMP", "                    confidence += _DAMP", "Specialist damping inverted (boosts instead)"),
            ("is_strategic = any(", "is_strategic = not any(", "Specialist strategic gate inverted"),
            ('return "list"', 'return "discover"', "Specialist list intent misclassified"),
            ('return "pause"', 'return "discover"', "Specialist pause intent misclassified"),
            ('return "delete"', 'return "discover"', "Specialist delete intent misclassified"),
            ("await self._n8n.deactivate_workflow", "await self._n8n.activate_workflow", "Pause handler calls activate"),
            ("await self._tracker.remove(", "# await self._tracker.remove(", "Delete skips tracker removal"),
        ]),
        # --- routes/workflows.py ---
        (SRC / "api/routes/workflows.py", "tests/unit/api/test_workflows.py", [
            ("tracker = request.app.state.workflow_tracker", "tracker = None", "Route always returns empty"),
        ]),
    ]

    total = 0
    killed = 0
    survived = []
    skipped = []

    for src_file, test_file, mutant_list in mutations:
        print(f"\n{'='*60}")
        print(f"Module: {src_file.relative_to(ROOT)}")
        print(f"Tests:  {test_file}")
        print(f"{'='*60}")
        for original, mutant, label in mutant_list:
            total += 1
            result = _mutate_and_test(src_file, test_file, original, mutant, label)
            status = result["status"]
            icon = {"KILLED": "✓", "SURVIVED": "✗", "SKIPPED": "⊘"}[status]
            print(f"  {icon} {label}: {status}")
            if status == "SURVIVED":
                survived.append(result)
            elif status == "SKIPPED":
                skipped.append(result)
            else:
                killed += 1

    print(f"\n{'='*60}")
    print(f"RESULTS: {killed}/{total} killed, {len(survived)} survived, {len(skipped)} skipped")
    print(f"Mutation score: {killed/max(total - len(skipped), 1)*100:.0f}%")
    if survived:
        print(f"\nSURVIVORS (weak tests):")
        for s in survived:
            print(f"  ✗ {s['label']}")
    print(f"{'='*60}")

    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
