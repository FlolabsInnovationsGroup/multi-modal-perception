"""T4.2 import-safety and route tests (TC-14 local part).

Every new module imports in a clean subprocess with no key, sockets disabled
and environment reads recorded (E2). Legacy routes are checked statically:
``main.py`` is never imported because it calls ``load_dotenv()``.
"""

import ast
import json
import os
import pathlib
import subprocess
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE_DIR = REPO_ROOT / "services" / "provider_integration"
MODULES = (
    "services.provider_integration",
    "services.provider_integration.types",
    "services.provider_integration.errors",
    "services.provider_integration.config",
    "services.provider_integration.ports",
    "services.provider_integration.orchestrator",
    "services.provider_integration.handler",
    "services.provider_integration.wiring",
    "services.provider_integration.adapters",
    "services.provider_integration.adapters.openai",
)
CREDENTIAL_ENV = {"OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORG_ID", "OPENAI_PROJECT_ID", "OPENAI_WEBHOOK_SECRET",
                  "AZURE_OPENAI_API_KEY"}
# Reads the installed SDK (openai 1.109.1) performs at import for its module-level client and logging,
# which this package never uses. AZURE_OPENAI_AD_TOKEN is credential-like: recorded as a residual risk.
SDK_IMPORT_READS = {"OPENAI_LOG", "OPENAI_API_TYPE", "OPENAI_API_VERSION", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_AD_TOKEN"}

PROBE = r"""
import json, os, socket, sys
sys.path.insert(0, ROOT)
reads = []
environ_type = type(os.environ)
original_getitem = environ_type.__getitem__
original_contains = environ_type.__contains__
def getitem(self, key):
    reads.append(key)
    return original_getitem(self, key)
def contains(self, key):
    reads.append(key)
    return original_contains(self, key)
environ_type.__getitem__ = getitem
environ_type.__contains__ = contains
def deny(*args, **kwargs):
    raise RuntimeError("network denied")
socket.socket.connect = deny
socket.create_connection = deny
socket.getaddrinfo = deny
import importlib
for name in MODULES:
    importlib.import_module(name)
print(json.dumps({
    "openai_reads": sorted({key for key in reads if key.startswith(("OPENAI", "AZURE"))}),
    "loaded": sorted(m for m in ("fastapi", "starlette", "dotenv", "api", "main", "requests") if m in sys.modules),
    "routers": sorted(name for name, module in sys.modules.items()
                      if module is not None and hasattr(module, "router") and name.startswith("services.provider_integration")),
}))
"""


def _clean_env():
    return {name: os.environ[name] for name in ("SYSTEMROOT", "PATH", "TEMP", "TMP") if name in os.environ}


class ImportSafetyTests(unittest.TestCase):
    def run_probe(self, env):
        script = PROBE.replace("ROOT", repr(str(REPO_ROOT)), 1).replace("MODULES", repr(MODULES), 1)
        completed = subprocess.run([sys.executable, "-I", "-c", script], env=env, cwd=str(REPO_ROOT),
                                   capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(completed.returncode, 0, "import probe failed")
        return json.loads(completed.stdout.strip().splitlines()[-1])

    def test_no_public_wiring(self):
        """TC-14: every module imports without a key or network and registers no route."""
        report = self.run_probe(_clean_env())
        self.assertFalse(set(report["openai_reads"]) & CREDENTIAL_ENV, report["openai_reads"])
        self.assertTrue(set(report["openai_reads"]) <= SDK_IMPORT_READS, report["openai_reads"])
        self.assertEqual(report["loaded"], [])
        self.assertEqual(report["routers"], [])

    def test_import_ignores_credential_environment(self):
        env = _clean_env()
        env.update({name: "test-provider-key-env-canary" for name in CREDENTIAL_ENV})
        report = self.run_probe(env)
        self.assertFalse(set(report["openai_reads"]) & CREDENTIAL_ENV, report["openai_reads"])

    def test_package_defines_no_routes_or_fakes(self):
        for path in sorted(PACKAGE_DIR.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.add(node.module or "")
            with self.subTest(file=str(path.relative_to(REPO_ROOT))):
                self.assertFalse({name for name in imported if name.split(".")[0] in {"fastapi", "starlette", "fakes", "tests", "dotenv"}})
                names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
                self.assertNotIn("APIRouter", names)

    def test_legacy_routes_unchanged_and_disconnected(self):
        """Static check (E2): the three existing routes remain; nothing reaches the new module."""
        main = ast.parse((REPO_ROOT / "main.py").read_text(encoding="utf-8"))
        included = sorted(ast.unparse(node.args[0]) for node in ast.walk(main)
                          if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "include_router")
        self.assertEqual(included, ["health.router", "openAI.router", "process.router"])
        routes = {}
        for path in sorted((REPO_ROOT / "api").glob("*.py")):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("provider_integration", source)
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for decorator in node.decorator_list:
                        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                            routes[(decorator.func.attr, ast.literal_eval(decorator.args[0]))] = path.name
        self.assertEqual(set(routes), {("get", "/health"), ("post", "/process"), ("post", "/openAI")})
        self.assertNotIn("provider_integration", (REPO_ROOT / "main.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
