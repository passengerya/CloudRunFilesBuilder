#!/usr/bin/env python3
"""patch_apk3.py 离线单元测试(stdlib unittest, 不联网)。

- 构造合成 apk v3 包(最小 pckg schema 树 + DATA 块)验证全流程
- 若本地存在真实 kmod-oaf apk(CI 工作流下载后), 一并做真实夹具验证
运行: python3 shell/test_patch_apk3.py [真实apk路径...]
"""

import os
import sys
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch_apk3 as P


def build_synthetic_package(kernel_ver=b"6.12.94~a7bc15f451f9652701ba04af9cfb0b95-r1"):
    """构造一个最小合法 apk v3 包: pckg schema(info.depends) + 1 个 DATA 块。

    块布局与 apk-tools 一致: rawsize = 4 + 载荷长, 块间零填充到 8 对齐
    (ADB_BLOCK_ALIGNMENT=8, 遍历器按 ROUND_UP(rawsize, 8) 步进)。"""
    # depends 数组: [ {name=kernel, version=<kernel_ver>}, {name=kmod-ipt-conntrack} ]
    dep_kernel = P.Node("obj", raw_count=3, slots={
        1: P.Node("bytes", val=b"kernel"),
        2: P.Node("bytes", val=kernel_ver),
    })
    dep_other = P.Node("obj", raw_count=3, slots={
        1: P.Node("bytes", val=b"kmod-ipt-conntrack"),
    })
    deps = P.Node("arr", raw_count=3, slots={1: dep_kernel, 2: dep_other})
    info = P.Node("obj", raw_count=17, slots={
        1: P.Node("bytes", val=b"kmod-oaf"),
        2: P.Node("bytes", val=b"6.12.94-r1"),
        5: P.Node("bytes", val=b"x86_64"),
        P.PI_DEPENDS: deps,
    })
    root = P.Node("obj", raw_count=4, slots={1: info})
    adb_payload = P.reencode(root)

    def block(typ, payload):
        rawsize = len(payload) + 4
        return ((typ << 30) | rawsize).to_bytes(4, "little") + payload + b"\x00" * ((-rawsize) % 8)

    data_payload = b"\x06\x00\x00\x00\x01\x00\x00\x00oaf.ko" + b"\x7fELF" * 4
    stream = b"ADB.pckg" + block(0, adb_payload) + block(2, data_payload)
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    return b"ADBd" + co.compress(stream) + co.flush()


def apk_walk_ok(stream):
    """模拟 apk-tools 块遍历器: ROUND_UP(rawsize, 8) 步进, 填充区必须全零。
    (2026-09-29 教训: 补丁后 ADB 块长度变化未对齐 → mkndx 报 "ADB block error")"""
    pos = 8
    n = len(stream)
    blocks = 0
    while pos < n:
        ts = int.from_bytes(stream[pos:pos + 4], "little")
        if ts == 0 and pos == n - 4:
            break  # 末尾 4 字节零 = 最后一块的填充
        typ = ts >> 30
        size = ts & 0x3FFFFFFF
        if typ == 3:
            raw = int.from_bytes(stream[pos + 8:pos + 16], "little")
            hdr = 16
        else:
            raw = size
            hdr = 4
        if raw < hdr or pos + raw > n:
            return False
        nxt = pos + raw
        aligned = (nxt + 7) & ~7
        if aligned > n or any(stream[nxt:aligned]):
            return False
        pos = aligned
        blocks += 1
    return pos == n


class TestSynthetic(unittest.TestCase):
    def test_roundtrip_no_kernel(self):
        """无 kernel 依赖时 process 原样返回(不碰字节)。"""
        pkg = build_synthetic_package(kernel_ver=b"1.0")
        self.assertEqual(P.process(pkg), pkg)

    def test_patch_kernel_fuzzy(self):
        pkg = build_synthetic_package()
        out = P.process(pkg)
        self.assertNotEqual(out, pkg)
        root = P.decode_adb(P.split_blocks(P.decompress_package(out))[0][1])
        deps = P.read_depends(root)
        self.assertEqual(deps[0], ("kernel", "6.12.94", 9))
        self.assertEqual(deps[1], ("kmod-ipt-conntrack", "", 0))
        # 其余信息字段保留
        info = root.slots[1]
        self.assertEqual(info.slots[1].val, b"kmod-oaf")
        self.assertEqual(info.slots[2].val, b"6.12.94-r1")
        self.assertEqual(info.slots[5].val, b"x86_64")

    def test_idempotent(self):
        pkg = build_synthetic_package()
        out = P.process(pkg)
        self.assertEqual(P.process(out), out)

    def test_preserves_data_block(self):
        pkg = build_synthetic_package()
        out = P.process(pkg)
        orig_blocks = P.split_blocks(P.decompress_package(pkg))
        new_blocks = P.split_blocks(P.decompress_package(out))
        self.assertEqual([t for t, _ in new_blocks], [t for t, _ in orig_blocks])
        for (t1, b1), (t2, b2) in zip(orig_blocks, new_blocks):
            if t1 == 2:
                self.assertEqual(b1, b2)

    def test_apk_walker_alignment(self):
        """补丁后的包必须能被 apk-tools 的块遍历器完整走通(8 对齐步进)。"""
        pkg = build_synthetic_package()
        out = P.process(pkg)
        self.assertTrue(apk_walk_ok(P.decompress_package(out)))


class TestRealFixture(unittest.TestCase):
    """真实 apk 夹具(CI 下载后传入路径): 验证完整链路。"""

    def test_real_apks(self):
        paths = sys.argv[1:]
        real = [p for p in paths if os.path.isfile(p) and p.endswith(".apk")]
        if not real:
            self.skipTest("未提供真实 apk 夹具")
        for p in real:
            with self.subTest(pkg=p):
                data = open(p, "rb").read()
                out = P.process(data)
                root = P.decode_adb(P.split_blocks(P.decompress_package(out))[0][1])
                deps = P.read_depends(root)
                self.assertTrue(any(n == "kernel" and v == "6.12.94" and m == 9
                                    for n, v, m in deps),
                                "kernel~6.12.94 依赖缺失: %s" % deps)
                self.assertEqual(P.process(out), out, "幂等失败")
                # apk-tools 块遍历器语义(8 对齐步进 + 零填充)必须走通
                self.assertTrue(apk_walk_ok(P.decompress_package(out)),
                                "apk 块遍历失败(ADB block error 风险)")
                # DATA 块与终止块保持不变
                ob = P.split_blocks(P.decompress_package(data))
                nb = P.split_blocks(P.decompress_package(out))
                for (t1, b1), (t2, b2) in zip(ob, nb):
                    if t1 == 2:
                        self.assertEqual(b1, b2)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
