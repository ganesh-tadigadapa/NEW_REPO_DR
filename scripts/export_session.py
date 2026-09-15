"""Export a Claude Code session transcript to something you can send.

Two outputs:
  <id>.slim.jsonl  the transcript with base64 blobs replaced by placeholders. Still a
                   valid session file, ~4x smaller, and it will resume.
  <id>.md          a readable log for a human: prompts, replies, and the commands run.

Base64 image/PDF payloads are ~73% of a typical session file here and are useless to a
reader, so both outputs drop them.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

B64 = re.compile(r'[A-Za-z0-9+/]{500,}={0,2}')


def scrub(obj):
    if isinstance(obj, str):
        return B64.sub(lambda m: f'<{len(m.group(0))} bytes of base64 stripped>', obj)
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    return obj


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    out = []
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t == "text":
                out.append(b.get("text", ""))
            elif t == "thinking":
                pass                                   # private reasoning, not exported
            elif t == "tool_use":
                name = b.get("name", "?")
                inp = b.get("input", {}) or {}
                arg = inp.get("command") or inp.get("file_path") or inp.get("pattern") or ""
                arg = str(arg)
                if len(arg) > 400:
                    arg = arg[:400] + " …"
                out.append(f"`[{name}]` {arg}".rstrip())
            elif t == "tool_result":
                pass                                   # output is long and rarely useful
    return "\n\n".join(x for x in out if x.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--outdir", default=".")
    a = ap.parse_args()

    src = Path(a.transcript)
    if not src.exists():
        sys.exit(f"no such transcript: {src}")
    outdir = Path(a.outdir); outdir.mkdir(parents=True, exist_ok=True)
    slim_p = outdir / (src.stem + ".slim.jsonl")
    md_p = outdir / (src.stem + ".md")

    kept, md = 0, ["# Claude Code session", f"\n`{src.name}`\n"]
    with src.open() as fh, slim_p.open("w") as slim:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            slim.write(json.dumps(scrub(rec)) + "\n")
            kept += 1

            msg = rec.get("message") or {}
            role = msg.get("role") or rec.get("type")
            body = text_of(msg.get("content"))
            if not body.strip():
                continue
            body = B64.sub("<image stripped>", body)
            if role == "user":
                if body.lstrip().startswith(("<system-reminder", "<command-name",
                                             "[SYSTEM NOTIFICATION")):
                    continue
                md.append(f"\n---\n\n## User\n\n{body.strip()}\n")
            elif role == "assistant":
                md.append(f"\n### Claude\n\n{body.strip()}\n")

    md_p.write_text("\n".join(md))
    print(f"records      : {kept}")
    print(f"slim jsonl   : {slim_p}  ({slim_p.stat().st_size/1e6:.2f} MB, "
          f"was {src.stat().st_size/1e6:.2f} MB)")
    print(f"readable md  : {md_p}  ({md_p.stat().st_size/1e6:.2f} MB)")


if __name__ == "__main__":
    main()
