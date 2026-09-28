#!/usr/bin/env python3
"""apk v3 包解析与 depends 内核钉扎改写工具(25-oaf 工作流使用)。

apk v3 包格式(已逆向, 见 AutoBuildTWrt 开发说明防错 #45):
  [4B "ADBd"] [raw-deflate 流, 从 offset 4 起]
  解压后 = [8B "ADB."+schema "pckg"] [ADB 块] [若干 DATA 块] [4B 0x00000000 结尾]
  - 块头 = u32 type_size: type=高2位(0=ADB元数据, 2=DATA文件, 3=EXT), size=低30位(含头4B)
  - ADB 块 payload = [u8 compat_ver][u8 ver][u16 reserved][u32 root 值标签] + 值缓冲
  - 值标签 = (类型<<28)|缓冲内偏移; INT 内联, INT32/INT64/BLOB 为偏移引用
  - OBJECT/ARRAY 序列化 = [u32 count][u32 字段槽×count](槽 0 = count)
  - pckg schema: 字段1=info(pkginfo); pkginfo 字段15=depends(依赖对象数组);
    依赖对象 = {1:name blob, 2:version blob, 3:match int}
  - match 标志: EQUAL=1 LESS=2 GREATER=4 FUZZY=8; '~' 操作符 = EQUAL|FUZZY(前缀匹配,
    version.c 的 apk_version_op_string 可证)

用途: destan19 的 kmod-oaf 以 OpenWrt 25.12.5 的 kernel 配置哈希钉扎 depends
(`kernel=6.12.94~<32hex>-r1`), 与 imm 各目标的 kernel 包版本(哈希按目标不同)不匹配。
本工具把该依赖改写为 `kernel~6.12.94`(fuzzy 前缀匹配), 使 kmod 在任何 imm 25.12.1
(内核 6.12.94)目标上可安装; 其余字段、文件内容、DATA 块均保持不变。

用法: python3 patch_apk3.py --kernel-fuzzy <in.apk> <out.apk> [--dump]
"""

import re
import sys
import zlib

# adb.h 值类型(高 4 位)
T_INT = 0x10000000
T_INT32 = 0x20000000
T_INT64 = 0x30000000
T_BLOB8 = 0x80000000
T_BLOB16 = 0x90000000
T_BLOB32 = 0xA0000000
T_ARRAY = 0xD0000000
T_OBJECT = 0xE0000000
T_MASK = 0xF0000000
V_MASK = 0x0FFFFFFF

# apk_version.h 匹配标志
MATCH_EQUAL = 1
MATCH_FUZZY = 8

# pckg schema 字段索引(apk_adb.c schema_package / schema_pkginfo)
PKG_INFO = 1
PI_DEPENDS = 15
DEP_NAME = 1
DEP_VERSION = 2
DEP_MATCH = 3

KERNEL_PIN_RE = re.compile(rb"^\d+\.\d+\.\d+~[0-9a-f]{32}-r\d+$")


class AdbParseError(Exception):
    pass


class Node:
    """解码后的 ADB 值树节点。kind: 'int'|'bytes'|'obj'|'arr'。"""

    def __init__(self, kind, val=None, slots=None, raw_count=0):
        self.kind = kind
        self.val = val              # int: 数值; bytes: 内容
        self.slots = slots or {}    # obj: {字段索引: Node|None}; arr: {1..n: Node|None}
        self.raw_count = raw_count  # 原 count(保留空槽)


def _tag_type(tag):
    return tag & T_MASK


def _tag_off(tag):
    return tag & V_MASK


def decompress_package(data):
    """apk v3: 'ADBd' 魔数后紧跟 raw-deflate, 返回解压流。"""
    if data[:4] != b"ADBd":
        raise AdbParseError("不是 apk v3 包(缺 ADBd 魔数)")
    d = zlib.decompressobj(-15)
    out = d.decompress(data[4:])
    if d.unconsumed_tail:
        raise AdbParseError("解压不完整")
    return out


def split_blocks(stream):
    """把解压流按块头切分为 [(type, payload)]; type=None 表示 0 结尾块。

    块头 = u32 type_size: type=高2位(0=ADB元数据, 1=SIG签名, 2=DATA文件, 3=EXT扩展),
    size=低30位(含头4B); type=3 时随后还有 u32 reserved + u64 x_size(总块长),
    真实类型 = size 低30位。
    注意: apk 的块遍历按 ROUND_UP(rawsize, 8) 前进(ADB_BLOCK_ALIGNMENT=8),
    块间可能夹 0~7 字节零填充, 必须按对齐步进, 否则后续块头全部错位。
    """
    if stream[:8] != b"ADB.pckg":
        raise AdbParseError("流首不是 ADB.pckg")
    blocks = []
    pos = 8
    n = len(stream)
    while pos < n:
        ts = int.from_bytes(stream[pos:pos + 4], "little")
        if ts == 0 and pos == n - 4:
            # 4 字节零 = 末尾块的对齐填充(非真实块)
            break
        if ts == 0:
            break
        typ = ts >> 30
        size = ts & V_MASK
        if typ == 3:  # EXT 块: [u32 type_size][u32 reserved][u64 x_size][payload]
            if pos + 16 > n:
                raise AdbParseError("EXT 块头越界 @%d" % pos)
            real_type = size & V_MASK
            x_size = int.from_bytes(stream[pos + 8:pos + 16], "little")
            if x_size < 16 or pos + x_size > n:
                raise AdbParseError("EXT 块越界 @%d x_size=%d" % (pos, x_size))
            blocks.append((real_type, stream[pos + 16:pos + x_size]))
            pos += x_size
        else:
            if size < 4 or pos + size > n:
                raise AdbParseError("块头越界 @%d type=%d size=%d" % (pos, typ, size))
            blocks.append((typ, stream[pos + 4:pos + size]))
            pos += size
        # 对齐步进(块间零填充)
        pos = (pos + 7) & ~7
    return blocks


def decode_adb(payload):
    """解码 ADB 元数据块 payload, 返回根节点。"""
    if len(payload) < 8:
        raise AdbParseError("ADB 块 payload 过短")
    buf = payload
    root_tag = int.from_bytes(buf[4:8], "little")
    if _tag_type(root_tag) not in (T_OBJECT, T_ARRAY):
        raise AdbParseError("root 标签类型异常 0x%08x" % root_tag)
    memo = {}

    def decode_tag(tag):
        typ = _tag_type(tag)
        off = _tag_off(tag)
        if typ == T_INT:
            return Node("int", val=off)
        if typ in (T_INT32, T_INT64, T_BLOB8, T_BLOB16, T_BLOB32):
            if off + 8 > len(buf):
                raise AdbParseError("内联值越界 tag=0x%08x" % tag)
            if typ == T_INT32:
                return Node("int", val=int.from_bytes(buf[off:off + 4], "little"))
            if typ == T_INT64:
                return Node("int", val=int.from_bytes(buf[off:off + 8], "little"))
            plen = {T_BLOB8: 1, T_BLOB16: 2, T_BLOB32: 4}[typ]
            ln = int.from_bytes(buf[off:off + plen], "little")
            return Node("bytes", val=bytes(buf[off + plen:off + plen + ln]))
        if typ in (T_OBJECT, T_ARRAY):
            return node_at(off, typ)
        raise AdbParseError("未知值类型 tag=0x%08x" % tag)

    def node_at(off, typ):
        if off in memo:
            return memo[off]
        if off + 4 > len(buf):
            raise AdbParseError("容器偏移越界 @%d" % off)
        count = int.from_bytes(buf[off:off + 4], "little")
        if count > V_MASK or off + 4 * count > len(buf):
            raise AdbParseError("容器 count 异常 @%d count=%d" % (off, count))
        memo[off] = Node("obj", raw_count=count)  # 防环占位
        slots = {}
        for i in range(1, count):
            st = int.from_bytes(buf[off + 4 * i:off + 4 + 4 * i], "little")
            if st == 0 or _tag_type(st) == 0:
                slots[i] = None
            elif _tag_type(st) in (T_OBJECT, T_ARRAY):
                slots[i] = node_at(_tag_off(st), _tag_type(st))
            else:
                slots[i] = decode_tag(st)
        node = Node("obj" if typ == T_OBJECT else "arr", slots=slots, raw_count=count)
        memo[off] = node
        return node

    return node_at(_tag_off(root_tag), _tag_type(root_tag))


class _ChunkWriter:
    """两阶段序列化: 先收集 chunk, 再按累计偏移回填槽位。"""

    def __init__(self):
        self.chunks = []
        self.objects = []

    def add(self, data):
        self.chunks.append(bytearray(data))
        return len(self.chunks) - 1

    def add_obj(self, count, spec):
        idx = self.add(b"\x00" * (4 * count))
        self.objects.append((idx, count, spec))
        return idx

    def materialize(self):
        offs = []
        acc = 0
        for c in self.chunks:
            offs.append(acc)
            acc += len(c)
        for idx, count, spec in self.objects:
            buf = self.chunks[idx]
            buf[0:4] = count.to_bytes(4, "little")
            for i in range(1, count):
                slot = spec.get(i)
                if slot is None:
                    continue
                typ, val = slot
                tag = (typ | val) if typ == T_INT else (typ | offs[val])
                buf[4 * i:4 + 4 * i] = tag.to_bytes(4, "little")
        return b"".join(bytes(c) for c in self.chunks), offs


def reencode(root):
    """把解码树重新序列化为 ADB 块 payload(含 8B 头)。返回 payload 字节。
    注意: 所有值偏移相对整个 payload 起点(含 8B 头, 与 adb_w_init_dynamic 一致)。"""
    w = _ChunkWriter()
    w.add(b"\x00" * 8)  # 预留 8B 头空间, 使后续 chunk 偏移含头

    def emit(node):
        if node.kind == "int":
            v = node.val
            if v < 0x10000000:
                return (T_INT, v)
            if v < 0x100000000:
                return (T_INT32, w.add(v.to_bytes(4, "little")))
            return (T_INT64, w.add(v.to_bytes(8, "little")))
        if node.kind == "bytes":
            b = node.val or b""
            ln = len(b)
            if ln <= 0xFF:
                return (T_BLOB8, w.add(bytes([ln]) + b))
            if ln <= 0xFFFF:
                return (T_BLOB16, w.add(ln.to_bytes(2, "little") + b))
            return (T_BLOB32, w.add(ln.to_bytes(4, "little") + b))
        count = node.raw_count
        if node.slots:
            count = max(count, max(node.slots) + 1)
        spec = {}
        for i in sorted(node.slots):
            spec[i] = emit(node.slots[i]) if node.slots[i] is not None else None
        idx = w.add_obj(count, spec)
        return (T_OBJECT if node.kind == "obj" else T_ARRAY, idx)

    rtype, ridx = emit(root)
    body, offs = w.materialize()
    root_tag = (rtype | offs[ridx]).to_bytes(4, "little")
    return body[:4] + root_tag + body[8:]


def read_depends(root):
    """返回 depends 列表 [(name, version, match)]。容器种类由 schema 决定,
    线上 ARRAY 与 OBJECT 用同一标签, 这里不做 kind 区分。"""
    out = []
    info = root.slots.get(PKG_INFO)
    if info is None or info.kind not in ("obj", "arr"):
        return out
    deps = info.slots.get(PI_DEPENDS)
    if deps is None or deps.kind not in ("obj", "arr"):
        return out
    for i in sorted(deps.slots):
        d = deps.slots[i]
        if d is None or d.kind not in ("obj", "arr"):
            continue
        name = d.slots.get(DEP_NAME)
        ver = d.slots.get(DEP_VERSION)
        match = d.slots.get(DEP_MATCH)
        out.append((
            (name.val if name and name.kind == "bytes" else b"").decode("utf-8", "replace"),
            (ver.val if ver and ver.kind == "bytes" else b"").decode("utf-8", "replace"),
            match.val if match and match.kind == "int" else 0,
        ))
    return out


def patch_kernel_fuzzy(root):
    """depends 中 kernel=<ver>~<32hex>-r<N> → kernel~<ver>(EQUAL|FUZZY)。返回改动记录。"""
    changed = []
    info = root.slots.get(PKG_INFO)
    if info is None or info.kind not in ("obj", "arr"):
        return changed
    deps = info.slots.get(PI_DEPENDS)
    if deps is None or deps.kind not in ("obj", "arr"):
        return changed
    for i in sorted(deps.slots):
        d = deps.slots[i]
        if d is None or d.kind not in ("obj", "arr"):
            continue
        name = d.slots.get(DEP_NAME)
        ver = d.slots.get(DEP_VERSION)
        if name is None or ver is None or name.kind != "bytes" or ver.kind != "bytes":
            continue
        if name.val == b"kernel" and KERNEL_PIN_RE.fullmatch(ver.val or b""):
            old = ver.val.decode()
            ver.val = old.split("~")[0].encode()
            d.slots[DEP_MATCH] = Node("int", val=MATCH_EQUAL | MATCH_FUZZY)
            changed.append((old, ver.val.decode()))
    return changed


def process(data, dump=False):
    """完整处理: 解压→切块→解码→改 depends→重编码→重压。返回新包字节。"""
    stream = decompress_package(data)
    blocks = split_blocks(stream)
    adb_idx = next(i for i, (t, _) in enumerate(blocks) if t == 0)
    root = decode_adb(blocks[adb_idx][1])
    if dump:
        print("depends(before):", read_depends(root))
    changed = patch_kernel_fuzzy(root)
    if not changed:
        print("[warn] 未发现需要改写的 kernel 钉扎依赖(保持不变)")
        return data
    new_adb = reencode(root)

    # 块对齐: apk 的块遍历按 ROUND_UP(rawsize, 8) 前进(adb.h ADB_BLOCK_ALIGNMENT=8),
    # rawsize = 4 + payload 长度必须是 8 的倍数, 否则下一个块头落在填充区 → "ADB block error"
    pad = (-(4 + len(new_adb))) % 8
    if pad:
        new_adb += b"\x00" * pad

    parts = [b"ADB.pckg"]
    for i, (t, payload) in enumerate(blocks):
        if i == adb_idx:
            # new_adb 已在载荷内补齐到 8 对齐(rawsize = 4 + len 为 8 的倍数)
            parts.append((len(new_adb) + 4).to_bytes(4, "little") + new_adb)
        else:
            # 保留块原样输出, 块间补齐 8 对齐的零填充(与 apk 遍历器步进一致)
            rawsize = len(payload) + 4
            pad = (-rawsize) % 8
            parts.append(((t << 30) | rawsize).to_bytes(4, "little") + payload + b"\x00" * pad)
    new_stream = b"".join(parts)

    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    out = b"ADBd" + co.compress(new_stream) + co.flush()

    if dump:
        stream2 = decompress_package(out)
        root2 = decode_adb(split_blocks(stream2)[0][1])
        print("depends(after):", read_depends(root2))
    for old, new in changed:
        print("[ok] kernel 钉扎改写: %s -> %s" % (old, new))
    return out


def main(argv):
    dump = "--dump" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__)
        return 2
    src, dst = args
    out = process(open(src, "rb").read(), dump=dump)
    open(dst, "wb").write(out)
    print("[ok] %s -> %s (%d -> %d bytes)" % (src, dst, len(open(src, "rb").read()), len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
