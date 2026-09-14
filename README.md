# CloudRunFilesBuilder

> 基于 [wukongdaily/RunFilesBuilder](https://github.com/wukongdaily/RunFilesBuilder) 分叉维护。

**本仓库是 OpenWrt 固件流水线的第一层**：每天同步上游各位大佬项目里最新编译的 ipk 文件，
用 makeself 打包成适用于 iStoreOS/OpenWrt 的 **run 自解压包**，发布到当日 Release。

下游项目 [AutoBuildImmortalTWrt](https://github.com/passengerya/AutoBuildImmortalTWrt)
的内嵌 store 每天从本仓库最新 Release 自动同步，因此**本仓库是整条流水线的软件来源**。

## 工作原理

- 每个软件一个 GitHub Actions 工作流，每天 UTC 22:00（北京时间早 6 点）起**错开分钟数**自动运行；
- 工作流流程：拉取上游最新 Release → 解析下载 ipk → 分平台目录整理 → 生成 install.sh → makeself 打包 → 上传当日 Release；
- 所有工作流上传到**同一个当日 tag**（`YYYY-MM-DD`，北京时间），Release 名 `Daily Build - <日期>`；
- run 自解压包不加密，内含若干 ipk 和一个 install.sh：
  - 安装：`sh xxx.run`（24.10 用 `opkg install *.ipk`，25.12 用 `apk add --allow-untrusted *.apk`）
  - 只解压不安装：`sh xxx.run --target <目录> --noexec`

## 产物命名规范（下游同步脚本依赖此规则，请勿随意改动）

```
[通道前缀]<应用名>_<版本>_<架构>.run
```

| 通道 | 前缀 | 包管理 | 下游对应 |
| --- | --- | --- | --- |
| 24.10 ipk 通道 | 无前缀 或 `24_`/`24-` | opkg | AutoBuildImmortalTWrt 的 `shell/custom-packages.sh` |
| 25.12 apk 通道 | `25_` 或 `25-` | apk | AutoBuildImmortalTWrt 的 `shell/apk-custom-packages.sh` |

架构标记枚举：`x86_64`、`aarch64_generic`、`aarch64_cortex-a53`、`aarch64_a53`、`_all`（架构无关，两个架构目录都放）。

示例：`mosdns_v5.3.4-r14_x86_64.run`、`24_quickfile_1.0.16_aarch64_generic.run`、`25-argon-2.4.7_aarch64_generic.run`、`luci-app-store-0.2.1-r1_all.run`。

## 应用清单（48 个工作流）

**24.10 ipk 通道**（28 个）：

| 应用 | 工作流 | 上游来源 |
| --- | --- | --- |
| AdGuardHome | `adguardhome.yml` | AdguardTeam/AdGuardHome |
| argon 主题 | `argon.yml` | ImmortalWrt 软件源 |
| aurora 极光主题 | `aurora-theme.yml` | eamonxg/luci-theme-aurora |
| advancedplus 进阶设置 | `advancedplus.yml` | sirpdboy/luci-app-advancedplus |
| amlogic 晶晨宝盒（仅 ARM64） | `amlogic.yml` | ophub/luci-app-amlogic |
| bandix 流量监控 | `bandix.yml` | dl.openwrt.ai/kiddin9 + timsaya |
| clashoo | `clashoo.yml` | kenzok8/openwrt-clashoo |
| dufs 文件服务器 | `dufs.yml` | sigoden/dufs |
| easytier 组网 | `easytier.yml` | EasyTier/luci-app-easytier |
| homeproxy | `homeproxy.yml` | ImmortalWrt 软件源 |
| lucky 大吉 | `lucky.yml` | dl.openwrt.ai/kiddin9 |
| momo | `momo.yml` | nikkinikki-org/OpenWrt-momo |
| mosdns | `mosdns.yml` | sbwml/luci-app-mosdns |
| nekobox | `nekobox.yml` | Thaolga/openwrt-nekobox |
| nikki | `nikki.yml` | nikkinikki-org/nikki |
| openclash | `oc.yml` | vernesong/OpenClash |
| openlist2 | `openlist2.yml` | sbwml/luci-app-openlist2 |
| openwrt-daede | `openwrt-daede.yml` | kenzok8/openwrt-daede |
| passwall | `main.yml` | Openwrt-Passwall/openwrt-passwall |
| passwall2 | `pw2.yml` | Openwrt-Passwall/openwrt-passwall2 |
| quickfile 文件管理 | `24-quickfile.yml` | wkccd/quickfile |
| rtp2httpd IPTV 转发 | `rtp2httpd.yml` | stackia/rtp2httpd |
| sing-box 内核 | `singbox.yml` | SagerNet/sing-box |
| ssr-plus（mihomo） | `ssrp.yml` | fw876/helloworld |
| tailscale-community | `tailscale-community.yml` | Tokisaki-Galaxy |
| xray-core | `xray-core.yml` | XTLS/Xray-core |
| iStore 商店 | `store.yml` | linkease/istore |
| 高级卸载 | `advance_uninstall.yml` | 上游 run 直采 |

**25.12 apk 通道**（17 个）：`argon25.yml`、`build-pw.yml`（PassWall）、`mosdns25.yml`、`oc25.yml`（OpenClash）、`pw2-25.yml`（Passwall2）、`ssrp25.yml`、`store25.yml`（iStore）、`25-quickfile.yml`、`25-singbox.yml`、`25-openwrt-daede.yml`、`25-clashoo.yml`、`25-rtp2httpd.yml`、`25-advancedplus.yml`、`25-aurora-theme.yml`、`25-amlogic.yml`、`25-tailscale-community.yml`、`25-easytier.yml`

**维护类**（3 个）：`clean.yml`（清理旧运行记录）、`clean-release.yml`（清理旧 Release）、`remove.yml`（删除全部 tag）

## 如何新增一个软件

按上游资产类型选一个模板（参考 [shell/](shell/) 与 [.github/workflows/](.github/workflows/)）：

1. **GitHub Release 直接发 ipk**（最常用）：复制 [rtp2httpd.yml](.github/workflows/rtp2httpd.yml)——fetch release.json → jq 按架构正则解析 ipk URL → 分平台下载 → makeself 打包；
2. **GitHub Release 发 zip 压缩包**：复制 [easytier.yml](.github/workflows/easytier.yml)——下载 zip → unzip 出 ipk → makeself；
3. **目录列表型源**（如 dl.openwrt.ai）：复制 [lucky.yml](.github/workflows/lucky.yml) + [shell/lucky.sh](shell/lucky.sh)——curl 目录页 grep ipk 链接。

注意事项：
- workflow 文件名：24.10 用 `<app>.yml`，25.12 用 `25-<app>.yml`；
- 所有 GitHub API 请求必须带 `Authorization: token ${{ secrets.GITHUB_TOKEN }}`（未认证会撞共享 IP 限流）；
- cron 分钟数与现有工作流错开；
- 产物命名遵守上面的命名规范，**版本号提取要覆盖 `_all.ipk` 后缀**；
- 提交到 dev 分支验证后**合并到 daily**（定时构建只读默认分支）。

## 分支

- **daily**：生产分支（默认），定时构建只使用该分支的 workflow 文件
- **dev**：开发分支，验证通过后合并 daily

## 维护

- Release 每日新增一个 tag，累积过多时手动触发 `Cleanup Old Releases`（保留最近 N 天）；
- 上游资产改名导致解析失败时，工作流会红，参考 pw2-25 的做法改为动态解析。
