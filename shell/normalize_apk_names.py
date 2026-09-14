# -*- coding: utf-8 -*-
"""
把 .apk 文件重命名为 OpenWrt imagebuilder 要求的规范文件名 `<name>-<version>.apk`。

背景: imagebuilder 的 `apk mkndx` 生成的本地索引不写 filename 字段,
安装时 apk 按默认规范 `${name}-${version}.apk` 推导文件名;
上游 Release 的 apk 常带 `_x86_64`/`_openwrt_x86_64`/`-aarch64_cortex-a53`
等后缀, 导致推导名与实际文件不符 (ENOENT -> "package mentioned in index not found")。

本脚本从包记录 (apk v3 = ADBd+deflate, v2 = gzip tar) 读取真实 name/version,
按规范重命名; 解析失败则保留原名并告警。
"""
import gzip
import io
import os
import re
import sys
import tarfile
import zlib

MAX_HEAD = 256 * 1024  # 只解析头部, 大包也快

NAME_RE = re.compile(rb'^[A-Za-z0-9][A-Za-z0-9+_.-]{0,39}$')
# 版本: 数字开头, 含 . - ~ 分隔符(或 8 位以上纯数字日期), 长度 3~32
VER_RE = re.compile(rb'^[0-9](?=[0-9A-Za-z._~+-]{2,31}$)(?:[0-9]{8,}|[0-9A-Za-z._~+-]*[.\-~][0-9A-Za-z._~+-]*)$')


def v3_name_version(path):
    """apk v3: 'ADBd' + raw-deflate; 记录头部 ADB.pckg 块后, name/version 为相邻两个 u8 长度前缀短字符串。"""
    with open(path, 'rb') as f:
        data = f.read(MAX_HEAD + 4)
    try:
        d = zlib.decompressobj(-15)
        raw = d.decompress(data[4:], MAX_HEAD)
    except zlib.error:
        return None
    i = raw.find(b'ADB.pckg')
    if i < 0:
        return None
    # 在块头后 64 字节内扫描 u8 长度前缀的相邻 (name, version) 字符串对
    end = min(i + 72, len(raw) - 1)
    p = i + 8
    while p < end:
        ln = raw[p]
        if 2 <= ln <= 40 and p + 1 + ln < len(raw):
            s = raw[p + 1:p + 1 + ln]
            if NAME_RE.match(s):
                q = p + 1 + ln
                ln2 = raw[q] if q < len(raw) else 0
                if 2 <= ln2 <= 32 and q + 1 + ln2 <= len(raw):
                    v = raw[q + 1:q + 1 + ln2]
                    if VER_RE.match(v):
                        return s.decode(), v.decode()
        p += 1
    return None


def v2_streams(data):
    """apk v2: 拼接的 gzip 流 (签名/control/data)。"""
    out = []
    while data:
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            out.append(d.decompress(data))
        except zlib.error:
            break
        data = d.unused_data
    return out


def v2_name_version(path):
    """apk v2: control 流里的 .PKGINFO。"""
    with open(path, 'rb') as f:
        data = f.read(MAX_HEAD + 4)
    for member in v2_streams(data):
        try:
            tf = tarfile.open(fileobj=io.BytesIO(member), mode='r:')
        except tarfile.TarError:
            continue
        for m in tf.getmembers():
            if m.name != '.PKGINFO':
                continue
            content = tf.extractfile(m).read().decode(errors='replace')
            name = version = None
            for line in content.splitlines():
                if line.startswith('pkgname = '):
                    name = line.split(' = ', 1)[1]
                elif line.startswith('pkgver = '):
                    version = line.split(' = ', 1)[1]
            if name and version:
                return name, version
    return None


def normalize_dir(root):
    renamed = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in sorted(filenames):
            if not fn.endswith('.apk'):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, 'rb') as f:
                magic = f.read(4)
            if magic == b'ADBd':
                nv = v3_name_version(path)
            elif magic[:2] == b'\x1f\x8b':
                nv = v2_name_version(path)
            else:
                print(f'[WARN] 无法识别格式, 跳过 {path}', file=sys.stderr)
                continue
            if nv is None:
                print(f'[WARN] 解析失败, 保留原名 {path}', file=sys.stderr)
                continue
            name, version = nv
            target = f'{name}-{version}.apk'
            if fn == target:
                continue
            target_path = os.path.join(dirpath, target)
            if os.path.exists(target_path) and os.path.abspath(target_path) != os.path.abspath(path):
                print(f'[WARN] 目标已存在, 跳过 {path} -> {target}', file=sys.stderr)
                continue
            os.replace(path, target_path)
            renamed += 1
            print(f'[OK] {fn} -> {target}')
    return renamed


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    total = normalize_dir(root)
    print(f'normalized: {total} files')


if __name__ == '__main__':
    main()
