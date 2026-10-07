# 开发与维护流程

当前项目为 **86V1 自定义固件**，发布标识为 `maintained-http-four-page-20261007-g`，
只适用于本机精确的 1.50.10 映像。
离线审查、freeze、d 精确恢复、g 四页安装读回、状态闭包和暖启动通过；真实 303 已指向
正式 HTTPS 网页并自动填写设备地址，用户报告上传正常，随后只读状态确认新 generation
已由 GUI 消费。其 HTTP 状态、默认图实屏、其他界面和米家验收未单独确认，见
[当前发布结果](../firmware/releases/maintained-http-20261007-g.json)。硬件工作前先读
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
| 旧图片实验版（`native-image-drawer`）93 项 freeze 及其依赖闭包 | 自定义固件的精确三页安装基线与旧回退材料 |
| `build/releases/<唯一名称>/` | 新版本源码、构建输入、工具、四页镜像及审查证据的不可覆盖快照 |
| `tools/xpack-openocd-0.12.0-7/` | 本地已绑定 hash 的 OpenOCD |
| WSL Ubuntu LLVM18、本地 `ld.lld`、公开 ABI 参考材料 | 新版本离线编译及分析 |
| Unicorn、pyelftools、OpenOCD Jim mock 环境 | ARM 程序模型及固定 writer 模拟 |

完整 freeze 逐项列在
[native-image-drawer-frozen-inputs.json](../analysis/persistence/native-image-drawer-frozen-inputs.json)。
原厂备份 SHA 见 [工程约束](engineering-notes.md)；NOR 不覆盖 MMC `/data`，勿删除本地
`backups/` 或复用其中的身份给其他设备。

`.gitattributes` 禁用自动换行转换，输入以完整字节 hash 绑定。`analysis/` 的路径仍是
冻结输入的一部分，整理文档不移动这些文件。不要把重算 hash 当作完成审查。

## 离线构建与材料检查

```powershell
node firmware/tools/release.ts baseline
node --test firmware/tools/release.test.ts
node firmware/tools/release.ts verify maintained-http-four-page-20261007-g
```

这些是离线命令，不连接、halt、reset 或写设备。`release.ts` 没有硬件执行接口；它检查
历史 freeze 的完整依赖、当前 release 的快照和派生页，不把重新计算 hash 当作完成审查。
维护源码、构建及 ARM 模型入口见 [firmware](../firmware/README.md)，发布流程和审查 JSON
格式见 [离线工具](../firmware/tools/README.md)。

已冻结的 C/S/链接脚本、BIN/ELF、prepare 输出及结果保持原字节。后续可以修改 canonical
`firmware/` 源码并构建另一个唯一 release，不能覆盖旧快照或运行会改写历史 result 的生成器。
缺材料先报告，不连接硬件凑结果。当前 [HTTP 图片 API](http-image-api.md) 与
[历史 TCP 协议](image-upload-protocol.md) 分开记录；图片上传只修改 RAM。

当前 g 的接收器忽略 Content-Type，仍验证固定长度、VIMG 和 FNV。其冻结配置指向
`https://wan.sh/xiaomi-86v1/`，用普通 `device` query 传递设备 endpoint，origin 为 `*`。
它不依赖电脑开发服务器；后续改目标 URL 要重新完成独立构建、审查、冻结和安装，
源码变化不会自动改变已安装 release。此前 d 的临时 LAN 地址仅保存在它自己的私有材料。

## 开发新的自定义固件版本

已有研究证明显示、触摸、设备端网络与持久化程序可以组合，但没有通用的完整固件 SDK。
新功能使用可维护的 `firmware/` 源码和独立 release freeze，不覆盖任一旧集合。维护需求见
[阶段计划](maintenance-plan.md)。

1. 确认当前源码、freeze、manifest 和保存的安装结果相互匹配；硬件前另行核对 live 四页，
   不将文档检查点当作实时探测结果。
2. 在 WSL LLVM18 中使用 Cortex-A7 Thumb、freestanding、`-Oz` 构建。build record 绑定
   源码、输出和实际使用的八个 compiler resource headers；header 原字节复制到本地快照。
   原生函数地址和 ABI 仍按精确映像审查。
3. 离线检查 ELF allocated 段、4B Thumb B.W 入口、加载地址和分段 raw BIN 一致性。
   三段代码分别输出 `panel.bin`、`panel-aux.bin`、`panel-net.bin`，不生成填满中间地址洞的
   平铺 BIN；核对各容器末端、相邻 helper
   和页面其余字节。
4. 用实际 ARM ELF 模型验证绘图、输入和交接，writer Jim mock 验证固定页流程；另做独立
   程序/容量及 writer 审查。mock/stub 不证明 IRQ、真实驱动、网络或 LCD 时序。
5. `prepare NAME OWNERSHIP.json` 创建独立私有快照，绑定额外网络页的 ownership 审查。
   完成 storage ownership、程序、writer、实际 ARM 模型及当前 93 项 writer mock 五份
   独立证据后，`freeze NAME EVIDENCE.json` 才能绑定全部输入。提交前核对准入
   文件，不能 force-add dump、原厂字节数组、session 或 BIN/ELF。
6. 一个负责人使用该 release 冻结的 `hardware.ts` 和相邻验证器串行检查、安装，明确
   写入范围、入口生效顺序及精确回退目标；每页完整读回及
   `app_complete/safe_to_resume` 闭合才进入后续阶段。遇不确定 native 结果保留停点和证据。
7. 用独立硬件 result 记录安装、暖启动、网络、用户观察和未验证项，不覆盖旧记录。
   当前用户已跳过完整断电测试，不再次要求或挪用旧版结果。

纯文档整理只检查链接、引用的版本及 `git diff --check`，不为提交而重复刷写。

## 当前四页发布与精确回退

当前四页 writer 的 install 只接受精确的旧图片实验版三页加原厂网络页；restore 接受
该 release 的精确补丁四页，或已经恢复的精确原四页。未知、混合、半写页面不能直接
推进，也不能在旧自定义固件上叠加新 install。离线 freeze 不证明已经安装；实际结果另行记录。

“安装基线”是写入前要求的完整 Flash 字节状态。这里的“三页”指三个已安装旧图片
实验程序的 4KiB Flash 区域，第四个网络区域仍是原厂字节；四个区域都必须逐字节匹配。
这些是 Flash 区域，不是三个屏幕页面；当前安装器不能对任意原厂设备直接首刷。
从仓库根目录使用该 release 的冻结执行器：

```powershell
node build/releases/maintained-http-four-page-20261007-g/snapshot/firmware/tools/hardware.ts check maintained-http-four-page-20261007-g
node build/releases/maintained-http-four-page-20261007-g/snapshot/firmware/tools/hardware.ts restore maintained-http-four-page-20261007-g
```

`check` 会连接硬件读取当前页面，`restore` 会写设备并暖重启，均由硬件负责人按已授权
范围执行。恢复返回 **精确的旧图片实验版三页与原厂网络页**。canonical 工具变化后
不可代替旧 release 的冻结执行器；`NEEDS_INSPECTION` 表示保留停点，先检查而非自动重试。
`check` 退出 0 仅说明读取完成，还需核对 `original`/`patched` 和完整页证据；两者均为 false
就不能继续。当前 g 的恢复路径已完成离线审查与 mock，尚未在硬件执行。

本轮迁移先使用 d 自己的冻结执行器，完整恢复精确的旧图片实验版三页和原厂网络页，
四页、native/cache/context 闭包、GLOBAL 及暖启动读回通过后，才使用 g 自己的冻结
执行器安装。g 的完整四页和后续 fresh check 均匹配补丁集合。两次顺序暖重启清空 RAM
图片；没有把 g writer 直接运行在 d 上。d 恢复结果记录在
[g 迁移结果](../firmware/releases/maintained-http-20261007-g.json)中，不覆盖旧 d result。
此前 c→精确基线→d 的迁移仍保留在 [d 结果](../firmware/releases/maintained-http-20261007-d.json)。

安装顺序 net→aux→code→entry，恢复顺序 entry→code→aux→net。A7、WF、BT 在写入和
四页完整验证期间保持 reset；只有完整页面和 native/cache/context 状态闭合才继续。
新增网络容器的边界及诊断命令影响见 [1.50.10 端口](../firmware/ports/1.50.10/README.md)。

继续回原厂时，每一步先确认上一版本的完整集合，再用对应入口；各步骤都会中断服务
并重启，不能把下面的表当作无人监督的批处理。

| 已安装版本 | 恢复入口 | 精确目标 |
| --- | --- | --- |
| 86V1 自定义固件 g 四页 | 上述 g 冻结 `hardware.ts restore`，本版硬件恢复未测 | 旧图片实验版三页与原厂网络页 |
| 历史自定义固件 d 四页 | d 自己冻结的 `hardware.ts restore`，g 迁移中已通过 | 旧图片实验版三页与原厂网络页 |
| 历史自定义固件 c 四页 | c 自己冻结的 `hardware.ts restore`，d 迁移中已通过 | 旧图片实验版三页与原厂网络页 |
| 旧图片实验版 | `Set-PanelNativeImageDrawer.ps1` | tap-fast 三页 |
| tap-fast | `Set-PanelNativeGitHubTapFast.ps1` | tap v1 三页 |
| tap v1 | `Set-PanelNativeGitHubTap.ps1` | card 两页及 stock aux |
| card | `Set-PanelNativeGitHubCard.ps1` | smooth |
| smooth | `Set-PanelNativeDrawerSmooth.ps1` | ease |
| ease | `Set-PanelNativeDrawerEase.ps1` | first drawer |
| first drawer | `Set-PanelNativeDrawer.ps1` | broker v1 |
| broker v1 | `Set-PanelNativeUiBroker.ps1` | stock |

tap v1 回退并恢复 stock aux 后，才可使用旧两页 writer。counter 是更早的独立 stock 分支，
不能用 counter writer 操作 image/broker/drawer/card 基线。旧三页版本的安装
aux→code→entry、恢复 entry→code→aux 仅适用于它们自己的精确集合；即使 entry 字节未变
也完整核对。自定义固件必须先完成四页恢复，才能使用 `Set-PanelNativeImageDrawer.ps1`。

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
