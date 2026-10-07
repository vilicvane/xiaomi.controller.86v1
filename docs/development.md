# 开发与维护流程

当前检查点是本机 1.50.10 的 `native-image-drawer`。硬件工作前先读
[工程约束](engineering-notes.md)、[当前架构](architecture.md)及根目录 `AGENTS.md`。
历史命令原文保留在 [开发记录归档](research/legacy-development-log.md)，不作为当前操作指南。

## 材料边界

Git 保存第一方源码、脚本、文档及明确准入的 review/result JSON。完整 NOR、RAM、扇区
镜像、凭据、Wi-Fi/云日志、第三方源码、工具链、BIN/ELF 和生成的固件 Tcl 数组只在本地。
这些是精确安装/回退的必要输入，全新 clone 不能直接刷写；缺失材料时报缺失，不绕过 SHA。

| 本地材料 | 用途 |
| --- | --- |
| `backups/mi-panel-flash-16m-1.50.10-20261004.bin` | 精确 16MiB 原厂 NOR 基线 |
| 各版本原始/补丁 4KiB 页、BIN/ELF | 重构、完整页比对和逐级回退 |
| 93 项 image drawer freeze 绑定的 stage/session cfg、runner 数据 | 精确设备流程 |
| `tools/xpack-openocd-0.12.0-7/` | 本地已绑定 hash 的 OpenOCD |
| WSL Ubuntu LLVM18、本地 `ld.lld`、公开 ABI 参考材料 | 新版本离线编译及分析 |
| Unicorn、pyelftools、OpenOCD Jim mock 环境 | ARM 程序模型及固定 writer 模拟 |

完整 freeze 逐项列在
[native-image-drawer-frozen-inputs.json](../analysis/persistence/native-image-drawer-frozen-inputs.json)。
原厂备份 SHA 见 [工程约束](engineering-notes.md)；NOR 不覆盖 MMC `/data`，勿删除本地
`backups/` 或复用其中的身份给其他设备。

`.gitattributes` 禁用自动换行转换，输入以完整字节 hash 绑定。`analysis/` 的路径仍是
冻结输入的一部分，整理文档不移动这些文件。不要把重算 hash 当作完成审查。

## 只检查现有冻结集合

```powershell
python -X utf8 analysis/persistence/run_native_image_drawer_firmware.py install
```

**没有 `--execute` 时只核对本地冻结材料，不连接、halt、reset 或写设备。**它也校验所依赖
的历史 UI 集合。这是现有版本的校验入口，不是“重新构建后自动刷入”的命令。
已经冻结的 C/S/链接脚本、BIN/ELF、prepare 输出及测试摘要保持原字节；不要重新构建
或运行会覆盖旧 result 的生成器。缺材料先报告，不连接硬件凑结果。

上传图片的命令和格式见 [协议](image-upload-protocol.md)。上传修改 RAM 内容，不写 NOR；
它仍是设备状态变更，须符合当前用户授权的测试范围。

## 开发新的维护版本

已有研究证明显示、触摸、设备端网络与持久化程序可以组合，但没有通用的完整固件 SDK。
新功能使用独立版本文件及 freeze，不覆盖已安装版本及任一旧集合。维护需求见
[阶段计划](maintenance-plan.md)。

1. 确认当前源码、freeze、manifest 和保存的安装结果相互匹配；硬件前另行核对 live 三页，
   不将文档检查点当作实时探测结果。
2. 为新版本建立独立源码/构建/模型/安装输入。现有 Cortex-A7 Thumb、freestanding、`-Oz`
   路线在 WSL LLVM18 中构建；原生函数地址和 ABI 仍按精确映像审查。
3. 离线检查 ELF allocated 段、4B Thumb B.W 入口、加载地址和分段 raw BIN 一致性。
   两段代码相距较远，不生成填满中间地址洞的平铺 BIN；核对各容器末端、相邻 helper
   和页面其余字节。
4. 用实际 ARM ELF 模型验证绘图、输入和交接，writer Jim mock 验证固定页流程；另做独立
   程序/容量及 writer 审查。mock/stub 不证明 IRQ、真实驱动、网络或 LCD 时序。
5. 完成独立 review、模型及 mock 后，冻结新的材料并保存所有输入 hash。提交前核对准入
   文件，不能 force-add dump、原厂字节数组、session 或 BIN/ELF。
6. 一个负责人串行安装，明确写入范围、入口生效顺序及精确回退目标；每页完整读回及
   `app_complete/safe_to_resume` 闭合才进入后续阶段。遇不确定 native 结果保留停点和证据。
7. 用独立硬件 result 记录安装、暖启动、网络、用户观察和未验证项，不覆盖旧记录。
   当前用户已跳过完整断电测试，不再次要求或挪用旧版结果。

纯文档整理只检查链接、引用的版本及 `git diff --check`，不为提交而重复刷写。

## 当前安装与精确回退

当前 writer 只接受精确 image drawer 或作为安装基线的 tap-fast **三页集合**。
未知、混合、半写页面不能直接交给历史 writer。当前直接回退命令：

```powershell
.\scripts\Set-PanelNativeImageDrawer.ps1 -Mode restore
```

它执行硬件恢复及一次普通重启，返回 **exact tap-fast**，不直接返回原厂。若继续回原厂，
每一步先确认上一版本的完整集合，再用下面与该版本匹配的入口；各步骤都会中断服务
并重启，不能把整个表当作无人监督的批处理。

| 已安装版本 | `-Mode restore` 的脚本 | 精确目标 |
| --- | --- | --- |
| image drawer | `Set-PanelNativeImageDrawer.ps1` | tap-fast 三页 |
| tap-fast | `Set-PanelNativeGitHubTapFast.ps1` | tap v1 三页 |
| tap v1 | `Set-PanelNativeGitHubTap.ps1` | card 两页及 stock aux |
| card | `Set-PanelNativeGitHubCard.ps1` | smooth |
| smooth | `Set-PanelNativeDrawerSmooth.ps1` | ease |
| ease | `Set-PanelNativeDrawerEase.ps1` | first drawer |
| first drawer | `Set-PanelNativeDrawer.ps1` | broker v1 |
| broker v1 | `Set-PanelNativeUiBroker.ps1` | stock |

tap v1 回退并恢复 stock aux 后，才可使用旧两页 writer。counter 是更早的独立 stock 分支，
不能用 counter writer 操作 image/broker/drawer/card 基线。安装 aux→code→entry、回退
entry→code→aux 的依赖顺序由当前受审 writer 处理，即使 entry 字节本次未变也完整核对。

BOOT 路线、168B native caller、看门狗及状态闭包的细节见
[固定写入器研究](../analysis/persistence/boot-nor-native-app-runner.md)。健康 MAIN 下的成功
恢复不等于已经测试故意损坏 MAIN 后的任意冷恢复。

## 证据与提交

当前程序的来源依次是 patch manifest（布局）、freeze（精确字节绑定）、review/model/mock
（离线结果）、hardware result（实际安装、运行和用户观察）。各类证据分别保留，不能只
从 `installed: true` 推断某项 UI 或米家控制已验收。

每轮硬件 capture、生成镜像和日志留在本地 ignored 目录；入库 result 只包含必要的
语义信息和 hash，不含设备身份、SSID、密码、局域网实址或原始 RAM/固件字节。
提交前检查 staged diff 和目录准入；整理阶段与功能实现阶段独立提交。
