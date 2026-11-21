"""Pinned optional CPU cross-encoder assets. Downloads are explicit and contain only published model files."""

import argparse
import hashlib
import os
import tempfile
from pathlib import Path

REVISION = "81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc"
MODEL = "cross-encoder/ms-marco-TinyBERT-L2-v2"
ASSETS = {
    "model.onnx": (
        "onnx/model.onnx",
        17604619,
        "0eac39ee56a3edf98d0beee17fa1bb368a5a1d8c8671b5afd6dd71677f8d8496",
    ),
    "tokenizer.json": (
        "tokenizer.json",
        711396,
        "688882a79f44442ddc1f60d70334a7ff5df0fb47",
    ),
}


def check(path):
    _, size, expected = ASSETS[path.name]
    data = path.read_bytes()
    actual = (
        hashlib.sha256(data).hexdigest()
        if path.name.endswith(".onnx")
        else hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    )
    if len(data) != size or actual != expected:
        raise ValueError("cross-encoder asset failed pinned digest verification")


def download(root):
    import httpx

    root.mkdir(parents=True, exist_ok=True)
    for name, (remote, size, _) in ASSETS.items():
        path = root / name
        if path.exists():
            check(path)
            continue
        url = f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{remote}"
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            candidate = Path(tmp) / name
            with (
                httpx.stream("GET", url, follow_redirects=True, timeout=60) as r,
                candidate.open("xb") as f,
            ):
                r.raise_for_status()
                for block in r.iter_bytes():
                    if f.tell() + len(block) > size:
                        raise ValueError("asset exceeds pinned byte count")
                    f.write(block)
            check(candidate)
            os.replace(candidate, path)


class CrossEncoder:
    def __init__(self, root):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        for name in ASSETS:
            check(root / name)
        self.tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(root / "model.onnx"), options, providers=["CPUExecutionProvider"]
        )

    def rank(self, query, candidates, sources):
        import numpy as np

        pairs = [(query, sources[c]["text"]) for c in candidates]
        if not pairs:
            return []
        tokens = self.tokenizer.encode_batch(pairs)
        inputs = {
            "input_ids": [t.ids for t in tokens],
            "attention_mask": [t.attention_mask for t in tokens],
            "token_type_ids": [t.type_ids for t in tokens],
        }
        feed = {
            i.name: np.array(inputs[i.name], dtype=np.int64)
            for i in self.session.get_inputs()
        }
        logits = self.session.run(None, feed)[0].reshape(-1)
        if len(logits) != len(candidates) or not np.isfinite(logits).all():
            raise ValueError("unexpected cross-encoder scores")
        return [
            cid
            for _, cid in sorted(
                zip(logits, candidates), key=lambda pair: (-pair[0], pair[1])
            )
        ]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--download", type=Path, required=True)
    download(p.parse_args().download)
