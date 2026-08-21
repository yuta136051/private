# -*- coding: utf-8 -*-
"""Chrome の PDF 書き出しが一部の漢字を康熙部首(U+2E80-U+2FDF)にマップしてしまう問題を、
ToUnicode CMap を書き換えて修正する。見た目は一切変えず、抽出/検索されるテキストだけ直す。"""
import re, sys, unicodedata
import pikepdf

MANUAL = {'⻑': '長', '⻫': '斉', '⺠': '民', '⻭': '歯', '⻤': '鬼',
          '戶': '戸', '黑': '黒', 'ﬁ': 'fi', 'ﬂ': 'fl'}

def fix_char(ch):
    if ch in MANUAL:
        return MANUAL[ch]
    if 0x2E80 <= ord(ch) <= 0x2FDF:
        n = unicodedata.normalize('NFKC', ch)
        return n if n != ch else ch
    return ch

def fix_hex(h):
    """h: 'XXXX...' hex string (UTF-16BE). returns fixed hex string."""
    try:
        b = bytes.fromhex(h if len(h) % 2 == 0 else '0' + h)
        s = b.decode('utf-16-be')
    except Exception:
        return h
    f = ''.join(fix_char(c) for c in s)
    if f == s:
        return h
    return f.encode('utf-16-be').hex().upper()

HEX = r'<([0-9A-Fa-f]+)>'

def fix_cmap(text):
    n = [0]
    def fix_bfchar(block):
        def r(m):
            src, dst = m.group(1), m.group(2)
            nd = fix_hex(dst)
            if nd != dst: n[0] += 1
            return '<%s> <%s>' % (src, nd)
        return re.sub(HEX + r'\s+' + HEX, r, block)
    def fix_bfrange(block):
        def r_arr(m):
            lo, hi, arr = m.group(1), m.group(2), m.group(3)
            def r2(mm):
                nd = fix_hex(mm.group(1))
                if nd != mm.group(1): n[0] += 1
                return '<%s>' % nd
            return '<%s> <%s> [%s]' % (lo, hi, re.sub(HEX, r2, arr))
        block = re.sub(HEX + r'\s+' + HEX + r'\s*\[([^\]]*)\]', r_arr, block)
        def r3(m):
            lo, hi, dst = m.group(1), m.group(2), m.group(3)
            nd = fix_hex(dst)
            if nd != dst: n[0] += 1
            return '<%s> <%s> <%s>' % (lo, hi, nd)
        return re.sub(HEX + r'\s+' + HEX + r'\s+' + HEX, r3, block)

    out = re.sub(r'beginbfchar(.*?)endbfchar',
                 lambda m: 'beginbfchar' + fix_bfchar(m.group(1)) + 'endbfchar', text, flags=re.S)
    out = re.sub(r'beginbfrange(.*?)endbfrange',
                 lambda m: 'beginbfrange' + fix_bfrange(m.group(1)) + 'endbfrange', out, flags=re.S)
    return out, n[0]

def main(src, dst):
    pdf = pikepdf.open(src)
    seen, total, streams = set(), 0, 0
    for obj in pdf.objects:
        try:
            if not isinstance(obj, pikepdf.Dictionary): continue
            if '/ToUnicode' not in obj: continue
        except Exception:
            continue
        tu = obj['/ToUnicode']
        key = tu.objgen if hasattr(tu, 'objgen') else id(tu)
        if key in seen: continue
        seen.add(key)
        try:
            data = tu.read_bytes().decode('latin-1')
        except Exception:
            continue
        new, cnt = fix_cmap(data)
        if cnt:
            tu.write(new.encode('latin-1'))
            total += cnt
            streams += 1
    pdf.save(dst)
    print('ToUnicode streams patched: %d / %d, mappings fixed: %d' % (streams, len(seen), total))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
