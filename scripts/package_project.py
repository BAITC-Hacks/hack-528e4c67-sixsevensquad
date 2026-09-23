"""Build a source-only handoff archive; never include credentials or runtime data."""
from pathlib import Path
import hashlib
import json
import zipfile
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
template = dotenv_values(ROOT / ".env.example")
if any(template.get(key) for key in ("OPENAI_API_KEY", "MONGODB_URI")):
    raise ValueError("Refusing to package nonempty credentials from .env.example")
OUTPUT = ROOT / "runtime" / "release" / "hackalem-orgkontur.zip"
EXCLUDED = {".venv", "node_modules", "__pycache__", ".pytest_cache", "dist", ".git"}
files = [ROOT / name for name in ("README.md", "dev.sh", ".gitignore", ".env.example")]
files += list(ROOT.glob("*.txt"))
for folder in ("backend", "frontend", "data/samples", "docs", "scripts"):
    files.extend(p for p in (ROOT / folder).rglob("*") if p.is_file()
                 and not EXCLUDED.intersection(p.relative_to(ROOT).parts)
                 and p.name not in {".DS_Store", "tsconfig.tsbuildinfo"}
                 and not p.name.startswith(".env"))
files = sorted(set(files))
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
manifest = {}
with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        if path.is_symlink():
            raise ValueError(f"Refusing symlink: {path.name}")
        name = path.relative_to(ROOT).as_posix()
        content = path.read_bytes()
        manifest[name] = hashlib.sha256(content).hexdigest()
        archive.writestr("hackalem-orgkontur/" + name, content)
    archive.writestr("hackalem-orgkontur/MANIFEST.json", json.dumps(manifest, indent=2, ensure_ascii=False))
with zipfile.ZipFile(OUTPUT) as archive:
    assert archive.testzip() is None
    assert not any(Path(name).name == ".env" or "runtime" in Path(name).parts for name in archive.namelist())
print(json.dumps({"archive": str(OUTPUT), "files": len(files), "bytes": OUTPUT.stat().st_size,
                  "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}, ensure_ascii=False))
