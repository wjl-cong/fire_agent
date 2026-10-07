# -*- coding: utf-8 -*-
"""渲染 docs/puml/*.puml 到 docs/puml/png/*.png（PlantUML 官方服务器，自定义编码）"""
import os, sys, zlib, urllib.request, urllib.parse

PUML_DIR = os.path.dirname(os.path.abspath(__file__))
PNG_DIR = os.path.join(PUML_DIR, "png")
os.makedirs(PNG_DIR, exist_ok=True)

# PlantUML 自定义 Base64 字母表（- 和 _ 替代 + 和 /）
_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"

def encode_plantuml(text: str) -> str:
    data = zlib.compress(text.encode("utf-8"), 9)[2:-4]  # raw deflate
    pad = (-len(data)) % 3
    data += b"\x00" * pad
    out = []
    for i in range(0, len(data), 3):
        b = data[i:i+3]
        n = (b[0] << 16) | (b[1] << 8) | b[2]
        out.append(_ALPHABET[(n >> 18) & 0x3F])
        out.append(_ALPHABET[(n >> 12) & 0x3F])
        out.append(_ALPHABET[(n >> 6) & 0x3F])
        out.append(_ALPHABET[n & 0x3F])
    return "".join(out)

def main():
    files = sorted(f for f in os.listdir(PUML_DIR) if f.endswith(".puml"))
    ok, fail = 0, 0
    for name in files:
        path = os.path.join(PUML_DIR, name)
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        enc = encode_plantuml(src)
        url = f"https://www.plantuml.com/plantuml/png/{enc}"
        out = os.path.join(PNG_DIR, name[:-5] + ".png")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            if len(data) < 500 or not data.startswith(b"\x89PNG"):
                raise RuntimeError(f"响应异常 size={len(data)} head={data[:40]!r}")
            with open(out, "wb") as fo:
                fo.write(data)
            print(f"OK   {name} -> {len(data)//1024} KB")
            ok += 1
        except Exception as e:
            print(f"FAIL {name}: {e}")
            fail += 1
    print(f"\n渲染完成: 成功 {ok}, 失败 {fail}")
    sys.exit(1 if fail else 0)

if __name__ == "__main__":
    main()
