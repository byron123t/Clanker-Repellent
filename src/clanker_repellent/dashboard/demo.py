"""Build a clearly labeled, entirely benign demonstration journal."""
from pathlib import Path

from ..payload.carrier_deploy import remove_deployment
from ..payload.retained_deploy import deploy_retained, html_carrier, _frame, WASM_HEADER
from ..payload.traffic import TrafficArchive


def create_demo(directory):
    root = Path(directory).absolute()
    root.mkdir(parents=True, exist_ok=False)
    root = root.resolve()
    store = root / "journal"
    note = root / "control.txt"
    note.write_text("Project note: include the documentation when sharing this example.\n", encoding="utf-8")
    archive = root / "documentation"
    archive.mkdir()
    for name in ["readme.md", "guides/setup.md", "guides/build.md", "guides/testing.md", "notes.txt"]:
        target = archive / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Project documentation\n\nAn ordinary example project.\n")
    deploy_retained(repository=archive, payloads=[note], benign=True, apply=True, count=3, randomize=True, seed=7, store_path=store)
    remove_deployment(repository=archive, apply=True)
    native = root / "native-toolkit"
    native.mkdir()
    for index, name in enumerate(["src/main.c", "src/format.c", "src/parse.c", "src/network.c", "lib/buffer.c", "lib/reader.c", "lib/writer.c", "tests/smoke.c"]):
        target = native / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"int example_{index}(void) {{\n  return {index};\n}}\n")
    deploy_retained(repository=native, payloads=[note], benign=True, apply=True, count=5, randomize=True, seed=42, store_path=store)
    web = root / "orbital-arcade"
    web.mkdir()
    names = ["src/main.js", "src/game.js", "src/scene.js", "src/controls.js", "src/physics.js", "src/audio.js",
             "src/ui/menu.js", "src/ui/hud.js", "src/ui/settings.js", "src/shaders/index.js", "src/shaders/lighting.js",
             "src/levels/intro.js", "src/levels/arena.js", "src/levels/finale.js", "src/worker.js", "src/loader.js"]
    for index, name in enumerate(names):
        target = web / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"// Example module {index}\nexport const settings = {{ score: {index}, enabled: true }};\n"
                          + "\n".join(f"export const item_{j} = {j};" for j in range(8 + index)) + "\n")
    (web / "index.html").write_text('<!doctype html>\n<html lang="en"><body><canvas id="game"></canvas></body></html>\n')
    (web / "game.wasm").write_bytes(WASM_HEADER)
    (web / "readme.md").write_text("# Orbital Arcade\n\nBenign dashboard demonstration.\n")
    (web / "credits.txt").write_text("Example project credits.\n")
    deploy_retained(repository=web, payloads=[note], benign=True, apply=True, count=14, randomize=True, seed=17, store_path=store)
    traffic = TrafficArchive(store)
    for path in ["/", "/play", "/settings"]:
        original = b"<!doctype html><body>Benign example response.</body>"
        after = html_carrier(original.decode(), [_frame(note.read_text())]).encode()
        traffic.record(original, after, status="200 OK", headers_before=[("Content-Type", "text/html")],
                       headers_after=[("Content-Type", "text/html"), ("Content-Length", str(len(after)))],
                       request={"method": "GET", "path": path})
    (store / "dashboard-demo.json").write_text('{"kind":"repel_dashboard_demo","benign":true}\n')
    return store
