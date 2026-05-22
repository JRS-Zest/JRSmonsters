from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import importlib.util
import sys

from PIL import Image


@dataclass
class Result:
    stem: str
    sad: Path | None
    frame_count: int
    written: int
    skipped: int
    failed: bool
    error: str = ""


def load_decoder_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("sad_frame_extractor", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load decoder script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    # Ensure decorators such as @dataclass can resolve module metadata.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def collect_target_stems(image_dir: Path) -> list[str]:
    stems: list[str] = []
    for p in image_dir.glob("*.png"):
        s = p.stem
        if "__" in s:
            continue
        stems.append(s)
    return sorted(set(stems), key=str.lower)


def build_sad_index(sad_root: Path) -> dict[str, Path]:
    idx: dict[str, Path] = {}
    for p in sad_root.rglob("*.sad"):
        key = p.stem.lower()
        if key not in idx:
            idx[key] = p
    return idx


def write_all_frames_for_stem(stem: str, sad_path: Path, out_dir: Path, SadDecoder) -> Result:
    try:
        raw = sad_path.read_bytes()
        dec = SadDecoder(raw)
        dec.analyze()

        frame_count = int(dec.frame_count)
        written = 0
        skipped = 0

        for i in range(frame_count):
            out_file = out_dir / f"{stem}__f{i:03d}.png"
            if out_file.exists():
                skipped += 1
                continue

            w, h, rgba = dec.render_body(i)
            image = Image.frombytes("RGBA", (w, h), rgba)
            image.save(out_file, "PNG")
            written += 1

        return Result(stem=stem, sad=sad_path, frame_count=frame_count, written=written, skipped=skipped, failed=False)
    except Exception as ex:
        return Result(stem=stem, sad=sad_path, frame_count=0, written=0, skipped=0, failed=True, error=str(ex))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate all frame PNGs for bundle monster images")
    parser.add_argument("--sad-root", default=r"C:\JRS\RED STONE\Data", help="Root path to search .sad files")
    parser.add_argument("--image-dir", default="monster_viewer_bundle/monster_image", help="Output image directory")
    parser.add_argument("--decoder-script", default="JRS_monsters/monster_image/sad_frame_extractor.py", help="Path to sad_frame_extractor.py")
    args = parser.parse_args()

    work = Path.cwd()
    sad_root = Path(args.sad_root)
    image_dir = (work / args.image_dir).resolve()
    decoder_script = (work / args.decoder_script).resolve()

    if not sad_root.is_dir():
        print(f"[ERROR] SAD root not found: {sad_root}")
        return 2
    if not image_dir.is_dir():
        print(f"[ERROR] Image dir not found: {image_dir}")
        return 2
    if not decoder_script.is_file():
        print(f"[ERROR] Decoder script not found: {decoder_script}")
        return 2

    module = load_decoder_module(decoder_script)
    SadDecoder = module.SadDecoder

    stems = collect_target_stems(image_dir)
    sad_index = build_sad_index(sad_root)

    print(f"[INFO] stems={len(stems)} sad_index={len(sad_index)}")

    results: list[Result] = []
    missing: list[str] = []

    for stem in stems:
        sad_path = sad_index.get(stem.lower())
        if sad_path is None:
            missing.append(stem)
            results.append(Result(stem=stem, sad=None, frame_count=0, written=0, skipped=0, failed=True, error="sad_not_found"))
            print(f"[MISS] {stem} -> sad_not_found")
            continue

        r = write_all_frames_for_stem(stem, sad_path, image_dir, SadDecoder)
        results.append(r)
        if r.failed:
            print(f"[FAIL] {stem} -> {sad_path.name} ({r.error})")
        else:
            print(f"[OK] {stem} -> {sad_path.name} frame_count={r.frame_count} written={r.written} skipped={r.skipped}")

    ok = sum(1 for r in results if not r.failed)
    fail = sum(1 for r in results if r.failed)
    total_written = sum(r.written for r in results)
    total_skipped = sum(r.skipped for r in results)

    print("[SUMMARY]")
    print(f"ok={ok} fail={fail} written={total_written} skipped={total_skipped} missing={len(missing)}")
    if missing:
        print("[MISSING_STEMS] " + ", ".join(missing))

    return 0


if __name__ == "__main__":
    sys.exit(main())
