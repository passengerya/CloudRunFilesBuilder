# CloudRunFilesBuilder

> 基于 [wukongdaily/RunFilesBuilder](https://github.com/wukongdaily/RunFilesBuilder) 分叉维护。

**本仓库是 OpenWrt 固件流水线的第一层**：每天同步上游各位大佬项目里最新编译的 ipk 文件，
用 makeself 打包成适用于 iStoreOS/OpenWrt 的 **run 自解压包**，发布到当日 Release。

下游项目 [AutoBuildTWrt](https://github.com/passengerya/AutoBuildTWrt)
的内嵌 store 每天从本仓库最新 Release 自动同步，因此**本仓库是整条流水线的软件来源**。

## 工作原理

- 每个软件一个 GitHub Actions 工作流，每天 UTC 22:00（北京时间早 6 点）起**错开分钟数**自动运行；
- 工作流流程：拉取上游最新 Release → 解析下载 ipk/apk → 分平台目录整理 →
  **apk 文件名规范化**（[normalize_apk_names.py](shell/normalize_apk_names.py)，见下文）→
  生成 install.sh → makeself 打包 → 上传当日 Release →
  **通知下游 Sync Store**（领导选举：由「最新启动且仍在运行」的构建发 repository_dispatch，见下文）；
- 所有工作流上传到**同一个当日 tag**（`YYYY-MM-DD`，北京时间），Release 名 `Daily Build - <日期>`；
- run 自解压包不加密，内含若干 ipk/apk 和一个 install.sh：
  - 安装：`sh xxx.run`（24.10 用 `opkg install *.ipk`，25.12 用 `apk add --allow-untrusted *.apk`）
  - 只解压不安装：`sh xxx.run --target <目录> --noexec`

### 25.12 通道 apk 文件名规范化（重要）

ImageBuilder 构建时会对本地 `packages/` 目录执行 `apk mkndx`，其索引不含 filename 字段，
安装时按默认规范 `${name}-${version}.apk` 推导文件名——上游 Release 的 apk 文件名带
`_x86_64`/`-aarch64_cortex-a53` 等后缀会全部失配（报 `package mentioned in index not found`）。
因此所有 25.12 工作流在打包前都会运行 `python3 shell/normalize_apk_names.py`，
从 apk 包记录（apk v3 `ADBd` 格式或 v2 gzip tar）读取真实 name/version 并重命名为规范名。
**新增 25.12 工作流时勿忘加这一步。**

### 构建完成即时通知下游

每个上传工作流末尾有「Notify Sync Store」步骤：等待 15s 让同期启动的构建全部入队后，
由**「最新启动且仍在运行/排队」的那个运行**（领导选举，确定性单通知，避免并发完成时
无人通知或多重通知）向 AutoBuildTWrt 发 `repository_dispatch`（event_type: `builder-done`）
即时触发 store 同步（需要 secrets.SYNC_DISPATCH_TOKEN；未配置时自动跳过，
依赖下游 23:00 UTC 定时同步兜底）。

## 产物命名规范（下游同步脚本依赖此规则，请勿随意改动）

```
[通道前缀]<应用名>_<版本>_<架构>.run
```

| 通道 | 前缀 | 包管理 | 下游对应 |
| --- | --- | --- | --- |
| 24.10 ipk 通道 | 无前缀 或 `24_`/`24-` | opkg | AutoBuildTWrt 的 `shell/custom-packages.sh` |
| 25.12 apk 通道 | `25_` 或 `25-` | apk | AutoBuildTWrt 的 `shell/apk-custom-packages.sh` |

架构标记枚举：`x86_64`、`aarch64_generic`、`aarch64_cortex-a53`、`aarch64_a53`、`_all`（架构无关，两个架构目录都放）。

示例：`mosdns_v5.3.4-r14_x86_64.run`、`24_quickfile_1.0.16_aarch64_generic.run`、`25-argon-2.4.7_aarch64_generic.run`、`luci-app-store-0.2.1-r1_all.run`。

## 应用清单（54 个工作流）

**24.10 ipk 通道**（30 个）：

| 应用 | 工作流 | 上游来源 |
| --- | --- | --- |
| AdGuardHome | `adguardhome.yml` | AdguardTeam/AdGuardHome |
| argon 主题 | `argon.yml` | ImmortalWrt 软件源 |
| aurora 极光主题 | `aurora-theme.yml` | eamonxg/luci-theme-aurora |
| aurora-config 极光配置中心 | `aurora-config.yml` | eamonxg/luci-app-aurora-config |
| shadcn 主题 | `shadcn.yml` | eamonxg/luci-theme-shadcn |
| oaf 应用过滤 | `oaf.yml` | destan19/OpenAppFilter |
| advancedplus 进阶设置 | `advancedplus.yml` | sirpdboy/luci-app-advancedplus |
| amlogic 晶晨宝盒（仅 ARM64） | `amlogic.yml` | ophub/luci-app-amlogic |
| bandix 流量监控 | `bandix.yml` | timsaya 官方 Release（openwrt-bandix + luci-app-bandix + zh-cn 语言包） |
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
| iStore 商店 | `store.yml` | linkease/istore |
| 高级卸载 | `advance_uninstall.yml` | 上游 run 直采 |

**25.12 apk 通道**（21 个）：`argon25.yml`、`build-pw.yml`（PassWall）、`mosdns25.yml`、`oc25.yml`（OpenClash）、`pw2-25.yml`（Passwall2）、`ssrp25.yml`、`store25.yml`（iStore）、`25-quickfile.yml`、`25-singbox.yml`、`25-openwrt-daede.yml`、`25-clashoo.yml`、`25-rtp2httpd.yml`、`25-advancedplus.yml`、`25-aurora-theme.yml`、`25-aurora-config.yml`、`25-oaf.yml`、`25-amlogic.yml`、`25-tailscale-community.yml`、`25-easytier.yml`、`25-shadcn.yml`、`25-bandix.yml`（bandix 流量监控）

> aurora 全系（主题+配置中心+语言包）2026-09-18 按用户要求恢复；oaf 应用过滤（destan19/OpenAppFilter）同日新增（24.10 上游 v7.x 起只发 apk，工作流自动选择含 ipk 的最新 release）。**2026-09-24 补齐 25.12 通道**：bandix 新增 `25-bandix.yml`（timsaya 官方 Release apk）；adguardhome/dufs/homeproxy 已确认在 ImmortalWrt 25.12.1 官方源，由 TWrt 侧 imm 固定段提供（无需 builder 工作流）；lucky/momo/nikki/nekobox/openlist2/高级卸载上游仍无 25.12 apk 资产，继续缺席。

**维护类**（3 个）：`clean.yml`（清理旧运行记录）、`clean-release.yml`（清理旧 Release）、`remove.yml`（删除全部 tag）

> 注：xray-core 已从本仓库移除——imm 官方仓库自带 xray-core，下游已在开关文件的
> imm 固定段中提供（24.10/25.12 两通道），不再需要 run 包。

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
- 25.12 工作流在打包前必须运行 `normalize_apk_names.py` 规范化 apk 文件名（见上文）；
- 上传 Release 的工作流末尾带「Notify Sync Store」领导选举步骤（模板复制时保留）；
- 同一 ipk 集的 luci 主包若已内置 i18n（kiddin9 的 luci-app-bandix 曾内置 zh-cn lmo），**不要**额外打包独立 luci-i18n 包，否则 opkg 文件冲突导致下游构建失败——正确做法是切到上游官方发布「主包不含 lmo + 独立语言包」的配套组合（bandix 已于 2026-09-23 切换 timsaya 官方 Release）；
- 提交到 dev 分支验证后**合并到 daily**（定时构建只读默认分支）。

## 分支

- **daily**：生产分支（默认），定时构建只使用该分支的 workflow 文件
- **dev**：开发分支，验证通过后合并 daily

## 维护

- Release 每日新增一个 tag，累积过多时手动触发 `Cleanup Old Releases`（保留最近 N 天）；
- 上游资产改名导致解析失败时，工作流会红，参考 pw2-25 的做法改为动态解析。
