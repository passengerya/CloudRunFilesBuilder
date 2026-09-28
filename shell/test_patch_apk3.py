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
    """构造一个最小合法 apk v3 包: pckg schema(info.depends) + 1 个 DATA 块。"""
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
    data_payload = b"\x06\x00\x00\x00\x01\x00\x00\x00oaf.ko" + b"\x7fELF" * 4
    stream = (b"ADB.pckg"
              + (len(adb_payload) + 4).to_bytes(4, "little") + adb_payload
              + ((2 << 30) | (len(data_payload) + 4)).to_bytes(4, "little") + data_payload
              + (0).to_bytes(4, "little"))
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    return b"ADBd" + co.compress(stream) + co.flush()


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
                # DATA 块与终止块保持不变
                ob = P.split_blocks(P.decompress_package(data))
                nb = P.split_blocks(P.decompress_package(out))
                for (t1, b1), (t2, b2) in zip(ob, nb):
                    if t1 == 2:
                        self.assertEqual(b1, b2)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
