# 开发与维护流程

当前项目为 **86V1 自定义固件**，本轮六页图片持久保存版本为
`maintained-persistent-images-six-page-20261008-a`，仅适用于本机精确的 1.50.10 映像。
566 组实际 ARM、7 项 ABI、139 项当前候选 writer、12 项 release、299 项 host HTTP 和
30 项网页检查通过，522-input candidate 与 528-input freeze 已完成。六页实机安装、
完整页/native/cache/context、outer GLOBAL 和暖读回通过，fresh check 为 patched=true。
PNG/JPEG持久保存、两次独立暖复位自动重载及完整RGB565读回通过，见
[六页发布结果](../firmware/releases/maintained-persistent-images-20261008-a.json)。

历史五页迁移前，四页 `maintained-idle-return-four-page-20261007-a` 的新鲜只读检查为
`patched=true`。现已由它自身冻结执行器完成恢复，四页/native/context、outer GLOBAL
和暖读回闭合；随后新五页检查为 `original=true`，再由新版本自身工具安装，五页暖读回
和 fresh patched 检查通过。五页能力 GET200 返回三种格式，设置 GET60；直接 Node 的
PNG/JPEG 请求、完整 RGB565 读回和错误图不替换现图通过，见
[五页发布结果](../firmware/releases/maintained-images-20261008-a.json)。
旧版 382 项 freeze、g 自身恢复、四页安装、真实设置读写和 AON GLOBAL
暖复位结果保留在 [四页自动返回版结果](../firmware/releases/maintained-idle-return-20261007-a.json)，
不用于证明新版本已安装。硬件工作前先读
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
| `build/releases/<唯一名称>/` | 新版本源码、构建输入、工具、完整页镜像及审查证据的不可覆盖快照；本轮为六页，历史 release 保持自身布局 |
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
node firmware/tools/release.ts verify maintained-persistent-images-six-page-20261008-a
```

这些是离线命令，不连接、halt、reset 或写设备。`release.ts` 没有硬件执行接口；它检查
历史基线 freeze 的完整依赖、六页 release 的快照和派生页，不把重新计算 hash 当作完成审查。
canonical 工具只接受 schema4 六页布局；旧五页及四页版本必须使用其自身冻结的
`snapshot/firmware/tools/release.ts` 和相邻工具，不能用当前工具代替旧验证器。
候选未 prepare/freeze 或材料缺失时，`verify` 应报告未就绪，不能绕过检查。
维护源码、构建及 ARM 模型入口见 [firmware](../firmware/README.md)，发布流程和审查 JSON
格式见 [离线工具](../firmware/tools/README.md)。

已冻结的 C/S/链接脚本、BIN/ELF、prepare 输出及结果保持原字节。后续可以修改 canonical
`firmware/` 源码并构建另一个唯一 release，不能覆盖旧快照或运行会改写历史 result 的生成器。
缺材料先报告，不连接硬件凑结果。当前 [HTTP 图片 API](http-image-api.md) 与
[历史 TCP 协议](image-upload-protocol.md) 分开记录。六页源码会保存图片到项目专用 MMC
文件；旧五页及更早版本只修改图片 RAM。

本轮源码按内容签名接收 PNG/JPEG/VIMG，Content-Type 可省略，Content-Length 为
1..1048576B；非 identity Content-Encoding 拒绝。VIMG 的固定长度与 FNV 保留，
旧四页自动返回版只支持 VIMG。网页仅在用户发送时查询格式能力，明确 404 才选择
旧 VIMG；失败 POST 不自动换格式重试。协议见 [HTTP 图片 API](http-image-api.md)。
默认配置沿用 `https://wan.sh/xiaomi-86v1/`，普通 `device` query 和 origin `*`。
它不依赖电脑开发服务器；后续改目标 URL 要重新完成独立构建、审查、冻结和安装，
源码变化不会自动改变已安装 release。此前 d 的临时 LAN 地址仅保存在它自己的私有材料。

## 开发新的自定义固件版本

已有研究证明显示、触摸、设备端网络与持久化程序可以组合，但没有通用的完整固件 SDK。
新功能使用可维护的 `firmware/` 源码和独立 release freeze，不覆盖任一旧集合。维护需求见
[阶段计划](maintenance-plan.md)。

1. 确认当前源码、freeze、manifest 和保存的安装结果相互匹配；硬件前按该版本核对所有
   live 页，本轮为六页，旧图片版为五页、旧自动返回版为四页，
   不将文档检查点当作实时探测结果。
2. 在 WSL LLVM18 中使用 Cortex-A7 Thumb、freestanding、`-Oz` 构建。build record 绑定
   源码、输出和实际使用的八个 compiler resource headers；header 原字节复制到本地快照。
   原生函数地址和 ABI 仍按精确映像审查。
3. 离线检查 ELF allocated 段、4B Thumb B.W 入口、加载地址和分段 raw BIN 一致性。
   五段代码分别输出 `panel.bin`、`panel-aux.bin`、`panel-net.bin`、`panel-codec.bin`、`panel-store.bin`，不生成填满中间地址洞的
   平铺 BIN；核对各容器末端、相邻 helper
   和页面其余字节。
4. 用实际 ARM ELF 模型验证绘图、输入和交接，writer Jim mock 验证固定页流程；另做独立
   程序/容量及 writer 审查。mock/stub 不证明 IRQ、真实驱动、网络或 LCD 时序。
5. `prepare NAME OWNERSHIP.json` 创建独立私有快照，分别绑定网络页、解码页和存储页的 ownership 审查。
   完成 storage ownership、程序、writer、实际 ARM 模型及当前 139 项 writer mock 五份
   独立证据后，`freeze NAME EVIDENCE.json` 才能绑定全部输入。提交前核对准入
   文件，不能 force-add dump、原厂字节数组、session 或 BIN/ELF。
6. 一个负责人使用该 release 冻结的 `hardware.ts` 和相邻验证器串行检查、安装，明确
   写入范围、入口生效顺序及精确回退目标；每页完整读回及
   `app_complete/safe_to_resume` 闭合才进入后续阶段。遇不确定 native 结果保留停点和证据。
7. 用独立硬件 result 记录安装、暖启动、网络、用户观察和未验证项，不覆盖旧记录。
   当前用户已跳过完整断电测试，不再次要求或挪用旧版结果。

纯文档整理只检查链接、引用的版本及 `git diff --check`，不为提交而重复刷写。

## 本轮六页图片持久保存

五段 BIN main/aux/net/codec/store 为 **3368/396/3940/3012/1676B**，完整 ELF SHA 为
`f7e4d2bbeff500ac997e694846523ddc025f94d88d1bccf7306419233ae6fcd3`；
522-input candidate SHA 为 `e061db87d2e4e4aa1e2836a89fa1dd1f47215826914b5b492b59b9bce7388591`，
528-input freeze SHA 为 `9a3f4d7e39a1451d7bef16672415d4183f516234a3741d986d3c721b6d39a801`。
存储容器为 `0x38052000..0x38052bf0`，NOR 页 `0x932000`，
仅借用可选 `monkey` 压力诊断单函数尾部。原页 SHA 为
`6874cd0d613150d2c71c70bbf5513f83f72214304e2891f092d50e6e87d84c71`；页前 4B、
后 1036B 及 BIN 外字节保留，入口页 `+0xe6c` 从 `0x38051fd1` 改为禁用 stub。
该诊断可通过持久调试开关启动，本版放弃它。正常启动/恢复需要的 `mkgpt` 已排除，不能借用。

六页基线为旧图片实验版精确三页及原厂网络、解码、存储页；不能直接叠加在五页维护版上。
迁移前须使用五页版自身冻结执行器恢复，核对其五页及 native/cache/context 闭合后，再
用六页自身工具检查全部六页。安装 **store→codec→net→aux→code→entry**，恢复
**entry→code→aux→net→codec→store**；完整页和 native 状态闭合前不允许 GLOBAL 或自动重试。
本轮已使用完整短根副本 `C:\p86-img-a` 完成旧五页自身恢复，完整五页/native/cache/context、
outer GLOBAL 和暖读回通过；随后 `C:\p86-persist-a` 六页检查为original，再安装六页，
完整页/native/cache/context、outer GLOBAL、暖读回与fresh patched检查通过。
六页自身硬件restore尚未测试；旧五页原始result保持不变，后续恢复记在新六页结果中。

图片文件为 MMC `/data/86v1-image.0` 与 `.1`，20B little-endian `VPI1` header
包含 magic/sequence/length/body FNV/header FNV，后接完整原编码 PNG/JPEG/VIMG，1..1MiB。
16B sequence/length/hash/valid 状态归网络线程私有，broker 保持 224B。启动检查两槽，
实际解码新版失败可回退旧图，全部失败保持默认图；保存完整预检两槽并保护已知可解码槽，
另一槽即使 hash 有效但图像坏也不能导致可恢复旧图被覆盖。短读写、fsync、close 与
独立完整逐字节读回确认后，才更新已知状态及 GUI pending。

`GET /api/image` 返回 `persistent: true`；202 表示图片保存已确认并排队供 GUI 消费。
发布锁、owner 或响应失败可能发生在保存之后，非 202/无响应不保证文件未改变；不自动重试。
foreign 文件409、I/O/资源/确认失败503；不足4B的现有文件无法证明归属，保持foreign保护。
中断模型证明的是应用双槽选择与旧图保护，不证明真实 FAT/MMC/RPMsgFS 掉电耐久性。
NOR 备份及安装/恢复不包含、不删除图片或设置文件，回到旧固件也保留这些项目文件。

真实307216B VIMG、2204B PNG和55134B JPEG依次POST202，完整RGB565匹配参考，计数1/2/3；
坏PNG为422且保留JPEG和计数3。第一次独立AON GLOBAL暖复位不执行OS shutdown hooks，
重新加载JPEG，计数1/pending0/server1/error0及完整像素匹配。随后保存默认PNG，再从正式
网页发送6050B PNG，GET200/POST202、按钮“画面已保存”和完整RGB565读回通过。第二次
独立暖复位自动加载浏览器保存的默认PNG，计数1/pending0/server1/error0和完整像素匹配。

正式网页版本 `6d2572cb-61e0-40b1-b28f-837e32d53157`，HTML/favicon/JS/CSS四项精确200，
Chrome零错误、初始零自动LAN请求。浏览器测试临时使用origin-scoped CDP本地网络许可，
结束后恢复prompt，不记为用户点击许可。用户对默认GitHub图片、上下滑、双击和米家状态
的合并问题回复“确认正常”，只记录合并观察，不扩展为分别测量。MEM-AP不证明LCD扫描，
暖重载不证明真实MMC掉电耐久性；完整断电仍按用户要求跳过。

## 历史五页发布检查点

该历史五页的四段 BIN 为 main/aux/net/codec **3368/396/4012/2916B**，完整 ELF SHA-256 为
`3f67d12758931a05fc22e20ddd89c51688ea9ec12de185ededce821b0ead79d3`。
471 项 candidate 输入对应候选 SHA
`992b58c7aa72a162aca23756088ce8951467fa1d624ba8c7889a155ab430021b`；
477-input freeze SHA 为
`627a224c619b59a6813b47685e272cd19a4f8b25bb04af1bdbf690b31cf2a330`。
新增解码页 NOR `0x927000`，代码容器为 `0x38047098..0x38047dac`；其余页面与入口位置不变。
端口依据和禁用的诊断命令见 [1.50.10 端口](../firmware/ports/1.50.10/README.md)。

五页 install 只接受旧图片实验版的精确三页、原厂网络页和原厂解码页。迁移须先用已安装
四页自动返回版自己的冻结工具 restore，暖读回确认后，再用新版本自己的工具核对五页。
安装顺序 **codec→net→aux→code→entry**，恢复顺序 **entry→code→aux→net→codec**。
全部页面、保护状态、cache/native/context 和 caller cleanup 闭合后才允许 GLOBAL 重启。
新恢复目标为同一旧图片实验版三页及两个原厂依赖页，不能直接调用历史三页 writer。

完整短根执行副本 `C:\p86-img-a` 已构建，全部绑定字节 hash 核对、116 项 writer mock 和
冻结 CLI verify 通过。旧四页版自身恢复、新五页 original 检查、五页安装、完整
native/cache/context 闭合、outer GLOBAL、暖读回和 fresh patched 检查已通过。
直接 Node 上传 2204B PNG 和 55134B JPEG 均返回202，完整 RGB565 分别匹配独立参考；
generation/displayed_generation 依次为1和2。坏 PNG CRC 返回422且保留JPEG和计数2；
最后恢复默认PNG为202，完整像素匹配且计数为3。新鲜运行状态 alive/ready=1、pending=0、
server=1/error=0、GUI cycles推进。这些是HTTP和MEM-AP证据，不证明LCD扫描、用户浏览器
或米家验收；请求耗时不作为性能基准。该五页原始检查点尚未测试自身硬件恢复，完整断电仍按用户
要求跳过。新结果不覆盖旧自动返回版记录或借用其图片、米家和冷启动证据。
224B context、MMC 自动返回双槽、RAM-only 图片和 `NEEDS_INSPECTION` 约束沿用。

正式网页版本 `2ee45a5f-6b04-42ce-80bb-2e92e4dc4cc5` 已部署，五项资源与本地构建
逐字节一致，浏览器零错误、初始零自动 LAN 请求。agent Chrome 的真实 HTTPS 页面点击
Send 后，能力 GET200 及单次 6050B PNG POST202 通过，没有 Content-Type 或自动重发。
最初本地网络权限 prompt 时 GET 等待且无 POST；随后由 agent 通过 origin-scoped CDP
临时授予权限完成测试，不是用户点击许可，结束后权限已恢复为 prompt。
随后只读 MEM-AP 核验完整 307200B RGB565 与默认图参考一致，槽位和计数稳定，
generation/displayed_generation=4、pending=0、alive/ready=1、server=1/error=0，GUI cycles
推进。这证明测试环境中的浏览器请求及 GUI 消费，不代表用户浏览器权限、LCD 扫描或米家验收。

本轮一次只读 capture 的 `-f/-l` Windows 反斜杠转义在 OpenOCD init 前失败，没有接触
硬件；路径改为正斜杠后另开进程只读采集，不重发已返回202的图片。这个已确定的本地
参数错误不适用于 uncertain native call：后者仍保留停点，不做路径重试或旧上下文回放。

## 历史四页自动返回版与精确回退

`maintained-idle-return-four-page-20261007-a` 的四页 writer 只接受精确的旧图片
实验版三页加原厂网络页；restore 接受
该 release 的精确补丁四页，或已经恢复的精确原四页。未知、混合、半写页面不能直接
推进，也不能在旧自定义固件上叠加新 install。离线 freeze 不证明已经安装；实际结果另行记录。

“安装基线”是写入前要求的完整 Flash 字节状态。这里的“三页”指三个已安装旧图片
实验程序的 4KiB Flash 区域，第四个网络区域仍是原厂字节；四个区域都必须逐字节匹配。
这些是 Flash 区域，不是三个屏幕页面；当前安装器不能对任意原厂设备直接首刷。
从仓库根目录使用该 release 的冻结执行器：

```powershell
node build/releases/maintained-idle-return-four-page-20261007-a/snapshot/firmware/tools/hardware.ts check maintained-idle-return-four-page-20261007-a
node build/releases/maintained-idle-return-four-page-20261007-a/snapshot/firmware/tools/hardware.ts restore maintained-idle-return-four-page-20261007-a
```

`check` 会连接硬件读取当前页面，`restore` 会写设备并暖重启，均由硬件负责人按已授权
范围执行。恢复返回 **精确的旧图片实验版三页与原厂网络页**。canonical 工具变化后
不可代替旧 release 的冻结执行器；`NEEDS_INSPECTION` 表示保留停点，先检查而非自动重试。
`check` 退出 0 仅说明读取完成，还需核对 `original`/`patched` 和完整页证据；两者均为 false
就不能继续。四页 a 的原始发布检查点未测自身恢复；本轮五页迁移中，其自身恢复已通过
完整四页/native/context、outer GLOBAL 和暖读回，后续结果记在新迁移记录中。

a 在深目录的首次 Jim mock 为 77/93，失败原因是 Windows/Jim 的路径长度；逐项核对
相同材料后放到短根目录 `C:\p86-idle-a`，93/93 通过。硬件入口也使用这个已验证的
完整执行副本，从该根目录运行上述冻结入口。短副本须包含 release、历史依赖、备份和
工具的全部绑定字节，不能只移动 executor、修改 freeze 或把 `NEEDS_INSPECTION` 当作
路径问题重试。原候选/冻结表与短副本逐项 hash 相同。

a 新增 [自动返回设置](auto-return.md)：只根据触摸屏活动计时，默认 60 秒，0 关闭、
最大 3600 秒；224B context 尾部保存运行计时状态。两个 `/data/86v1-return.*` MMC 文件
保存设置，NOR 安装/恢复不读写这些文件，NOR 备份不包含它们。配置已确认后才更新
运行值；失败不承诺旧持久值原样保留，不自动再次写入。

上一轮先由 g 自身冻结工具恢复精确基线，完整四页与 native 状态闭合、GLOBAL 和暖读回
通过，再由短根目录 a 自身冻结工具安装。a 四页读回及暖启动通过，两次新鲜 check 均为
`patched=true`。真实 GET 默认 60，POST/GET 0 和 5 一致，3601 返回 422 且不改运行值。
保存 5 后执行一次独立 AON GLOBAL 暖复位，224B context 和 GET 都重新读到 5；随后保存回
60。a 自身 restore、用户交互、米家和完整断电未由这些检查推定通过。

此前 d→g 迁移先使用 d 自己的冻结执行器，完整恢复精确的旧图片实验版三页和原厂网络页，
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
| 当前六页图片持久保存版（已安装） | 六页本版冻结执行器；自身硬件恢复未测试 | 旧图片实验版三页与原厂网络/解码/存储页 |
| 历史五页图片版 | 本版自己的冻结 `hardware.ts restore`，本轮六页迁移中已通过 | 旧图片实验版三页与原厂网络/解码页 |
| 历史四页自动返回版 | 上述四页 a 冻结 `hardware.ts restore`，本轮五页迁移中已通过 | 旧图片实验版三页与原厂网络页 |
| 历史自定义固件 g 四页 | g 自己冻结的 `hardware.ts restore`，a 迁移中已通过 | 旧图片实验版三页与原厂网络页 |
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
也完整核对。维护版自定义固件必须先完成自身所有页的恢复，才能使用 `Set-PanelNativeImageDrawer.ps1`。

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
