# 86V1 自定义固件刷写与配置

本指南记录当前设备的已验证接线、构建、材料检查和安装命令。开发命令从仓库根目录
执行；冻结刷写命令使用后文各版本自己的完整短路径执行副本。阅读步骤不代表可以跳过
设备备份、精确状态匹配或版本审查。
硬件工作前还需阅读 [工程约束](engineering-notes.md)、[开发流程](development.md)及
[项目工作约束](../AGENTS.md)。日常图片功能使用见 [项目 README](../README.md)。

本轮已安装版为 `maintained-images-five-page-20261008-a`，新增 PNG/JPEG 解码和第五个
Flash 页，已冻结并安装。完整五页/native/cache/context、outer GLOBAL 和暖读回通过，
随后 fresh check 为 `patched=true`。迁移前四页
`maintained-idle-return-four-page-20261007-a` 检查为 `patched=true`；其自身恢复现已通过，
新五页检查为 `original=true`。两者名称中的 `a` 不能混用执行器或验证结果。

## 安装材料

当前只支持已备份并审核的本机官方 1.50.10 精确映像。另一台设备需要自己的完整备份、
端口审查和独立安装材料；同型号、同版本号不能代替字节与安装状态校验。

安装器只接受精确的**旧图片实验版（技术标识 `native-image-drawer`）三个 Flash 区域，
加原厂网络与解码区域**作为五页安装器的起点。这是已装历史实验程序的特定存储内容，
并非原厂状态。旧四页版本只核对其中三页加网络页，五页版本还必须核对解码页。
这里的“三页/四页/五页”是相应数量的 4KiB Flash 区域，**不是屏幕上的界面页**。

已经安装 86V1 自定义固件时，必须先用当前版本自身保存的执行工具恢复这个精确起点，
再装新版本；不能直接覆盖旧自定义固件，也不能把原厂状态当作旧图片实验版。
仓库尚无从原厂状态直接安装当前固件的公开首装流程；全新 clone 不能直接刷写。

| 必需材料 | 说明 |
| --- | --- |
| 本机 16MiB 原厂 NOR 备份 | 本机已审核 SHA-256 为 `777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b` |
| 旧图片实验版及其冻结材料 | 93 项旧实验版输入及递归历史依赖，不能通过改 hash 绕过 |
| `build/releases/<release>/` | 该版本的 candidate、freeze、源码/工具快照、完整页镜像和独立证据；本轮为五页，旧版本保持自身布局 |
| 冻结的 Windows OpenOCD 包 | exe、DLL、两份字节相同的 CMSIS-DAP 接口配置，随 release 绑定 |

这些私有材料包含原厂字节或设备数据，不在 Git 中分发。缺失时先补齐和审查，不能仅靠
编译几个 BIN 刷写。NOR 备份不含 MMC 上的 `/data`、字库和全部设备配置，也不等于
已获得任意故障状态的救砖能力。

## 调试器、接线与供电

已验证调试器为 MuseLab nanoDAP，使用 **SWD**，不需要完整 JTAG 五线。
购买入口来自 [nanoDAP 官方项目](https://github.com/wuxx/nanoDAP)的 About：
[实验室官方淘宝商品](https://item.taobao.com/item.htm?id=586425846353)。型号接口和使用说明
见 [官方用户手册](https://github.com/wuxx/nanoDAP/blob/master/user_manual.md)。

建议一起准备：

- nanoDAP、USB 数据线，以及短杜邦线或对应转接线。
- **烧录探针夹**：用于主板测试点的 pogo pin/弹簧探针夹具，能稳定接触 GND、JTMS、JTCK
  三个 SWD 测试点；按自己主板的焊盘间距和排列选型，供电另外接线。这里需要的是
  测试点探针夹具，SOIC8 Flash 芯片夹不能替代它。没有合适夹具时可焊接短导线。
- 万用表，用于确认共地、供电入口极性和电压。
- 稳定的隔离 5V 低压供电。本机已验证 nanoDAP 的 5V 输出；若 USB 供电不足，准备
  独立低压电源并共地。

在断电时接线，使用短导线或焊线，按主板丝印对应：

| nanoDAP | 面板主板 | 用途 |
| --- | --- | --- |
| GND | GND | 共地 |
| SWDIO / IO | JTMS | SWD 数据 |
| SWCLK / CK | JTCK | SWD 时钟 |
| 5V 供电或独立稳定 5V 电源 | 已核实的主板原低压供电入口 | 为主板供电，电源 GND 与上述共地 |

JTDI/JTDO 不参与已验证 SWD 路径，nRST 未接。主板供电入口在本机输入 3.3V 不启动，
5V 正常启动；**5V 只接已确认的供电入口，不能接 JTMS/JTCK 或芯片引脚**。调试信号
实测约 3.1V，供电电压与调试逻辑电压不同。不要同时叠加两路供电；若 USB 供电不足，
用稳定的隔离低压电源并共地。裸板调试时断开原市电供电板，不在裸露 220V 下连接电脑。
主板电源焊点不能凭本表推断位置，必须先核对自己的连接器与极性。

## Windows 和 WSL 环境

| 工作 | 环境 |
| --- | --- |
| 网页开发、离线 release 工具、上传器 | Node.js 24、Git；网页依赖通过 `npm --prefix web ci` 安装 |
| 硬件检查/安装/恢复 | Windows PowerShell + Windows Node.js 24，使用 release 内冻结的 OpenOCD |
| 编译新的设备端代码 | WSL Ubuntu，`clang-18`、`llvm-objcopy-18`、`llvm-size-18`、`llvm-nm-18`，以及本地 `ld.lld` |
| ARM 模型和 writer mock | Windows Python、Unicorn、pyelftools、历史模型 helper 和冻结的 OpenOCD/Jim 环境 |

准备代码和检查环境：

```powershell
git clone https://github.com/vilicvane/xiaomi.controller.86v1.git
cd xiaomi.controller.86v1
node --version
wsl.exe --list --verbose
npm --prefix web ci
node firmware/tools/release.ts baseline
```

`baseline` 是离线材料检查，不连接设备；全新 clone 因缺少私有材料而失败是预期行为。
Windows Node 用于硬件入口，不能在 WSL 直接执行 Windows-only `hardware.ts`。
没有 Ubuntu 时可先使用 `wsl.exe --install -d Ubuntu` 安装 WSL 环境。
构建脚本目前将链接器固定在
`tools/a7-llvm/extracted/usr/lib/llvm-18/bin/ld.lld`，不能只安装 Clang 就视为工具链完整。
公开的 [xPack OpenOCD 0.12.0-7](https://github.com/xpack-dev-tools/openocd-xpack/releases/tag/v0.12.0-7)
可用作来源参考，但实际写入必须使用已绑定 hash 的 release 包，不能随意换为系统中的 OpenOCD。

## 备份与只读检查

首次修改前保留这台设备的原厂备份。下例仅适用于已经确认本项目 1.50.10 NOR 映射、
供电和 SWD 的本机；从仓库根目录用独立文件名读取 16MiB，不覆盖原有备份：

```powershell
$panelOpenOcd = '.\tools\xpack-openocd-0.12.0-7\bin\openocd.exe'
New-Item -ItemType Directory -Path backups -Force | Out-Null
$panelBackup = (Join-Path (Get-Location) ('backups/nor-' + (Get-Date -Format yyyyMMdd-HHmmss) + '.bin')) -replace '\\', '/'
& $panelOpenOcd -s diagnostics -f diagnostics/swd-memory.cfg -c 'adapter speed 1000' -c init -c "dump_image {$panelBackup} 0x28000000 0x1000000" -c shutdown
if ($LASTEXITCODE -ne 0) { throw '读取失败；保留日志，不继续写入。' }
Get-Item -LiteralPath $panelBackup | Select-Object Length
Get-FileHash -LiteralPath $panelBackup -Algorithm SHA256
```

文件应为 16777216B。可另读一个新文件并比较 hash；已经打补丁的备份是当前状态，
不能冒充原厂备份或替换 release 的固定 stock 输入。不要提交备份、SSID、密钥或原始日志。
使用通用 MEM-AP 配置，不加载自动 CPU/Flash 烧写算法。

## 配置网址、构建与冻结

正式页面配置在编译时写入；修改源码或网页部署不会自动改变设备中的跳转目标。
在已配置好的 WSL Ubuntu 中，切到仓库对应的 Linux 路径后运行：

```sh
PANEL_FRONTEND_URL=https://wan.sh/xiaomi-86v1/ \
PANEL_FRONTEND_ORIGIN='*' sh firmware/build.sh
sh firmware/tests/test-http.sh
```

URL 保留 `/xiaomi-86v1/` 子路径，origin 可为 `*` 或不带路径的协议与域名。
设备 `GET /` 返回 303，自动把当前面板地址放入 `?device=` 查询参数，例如
`https://wan.sh/xiaomi-86v1/?device=http%3A%2F%2FPANEL_IPV4%3A18086`。
本轮沿用 CORS `*`，允许正式页面及本地开发 origin 读取响应。也可在新 release 中把 origin
设为 `https://wan.sh`，限定正式来源；origin 不能带路径。命令行 cURL 不受浏览器 CORS 限制。

新版本还必须完成程序/容器审查、实际 ARM 模型、116 个 writer mock、独立 storage 和
writer 审查，再通过 [离线发布流程](../firmware/tools/README.md)创建唯一 release 和 freeze。
构建成功不等于已审核或可刷写，不能覆盖既有 release 快照。本轮 471 项 candidate 输入、
477 项 freeze 和 116 项 writer 已完成；下方旧四页 hash 仅属于旧 release，不能替代新版本材料。

## 安装、升级与恢复

下面命令须在匹配本机材料及完整 freeze 的前提下执行。先恢复升级前安装的四页自动
返回版，再选择新五页图片版；它们各用自身保存的 executor 和 verifier，不能直接叠加。

Windows/Jim 在深目录可能报路径过长。旧四页 a 的完整执行材料已逐项 hash 核对并放在短根目录
`C:\p86-idle-a`，在那里 93 项 writer mock 全部通过。下面命令从这个**已准备且完整**的
执行副本根目录运行；它必须包含同一套备份、历史依赖、release 和工具，不能只复制
`hardware.ts`，也不能改 hash 绕过检查。新 clone 不会自动得到这个目录或这些材料。

```powershell
Set-Location 'C:\p86-idle-a'
$panelOldRelease = 'maintained-idle-return-four-page-20261007-a'
$panelOldExecutor = "build/releases/$panelOldRelease/snapshot/firmware/tools/hardware.ts"
node --input-type=module -e 'const name = "maintained-idle-return-four-page-20261007-a"; const { verifyRelease } = await import("./build/releases/" + name + "/snapshot/firmware/tools/release.ts"); console.log(JSON.stringify(verifyRelease(process.cwd(), name)));'
node $panelOldExecutor check $panelOldRelease
```

上述 import 调用 `verifyRelease(process.cwd(), name)` 只检查文件。旧冻结验证器的 CLI
按脚本位置推算根目录，不能把 `node $panelVerifier verify ...` 当作等价命令，也不能修改
旧冻结源码来修复路径。`check` 连接 SWD 并读取旧四页和当前状态，不写 Flash。
核对输出的 `original`/`patched` 与实际版本；`check` 命令成功只代表读完，不等于匹配。
旧四页完整匹配 `patched=true` 后，使用其自身恢复器：

```powershell
node $panelOldExecutor restore $panelOldRelease
```

完整恢复旧图片实验版三页及原厂网络页，GLOBAL 和暖读回闭合后，再核对原厂解码页并
安装新版本。新完整短根副本 `C:\p86-img-a` 已完成全部绑定字节 hash 核对、116 项
writer mock 和 freeze，冻结 CLI verify 通过；下列命令只用于这一套完整包。

```powershell
Set-Location 'C:\p86-img-a'
$panelNewRelease = 'maintained-images-five-page-20261008-a'
$panelNewExecutor = "build/releases/$panelNewRelease/snapshot/firmware/tools/hardware.ts"
$panelNewVerifier = "build/releases/$panelNewRelease/snapshot/firmware/tools/release.ts"
node $panelNewVerifier verify $panelNewRelease
node $panelNewExecutor check $panelNewRelease
```

新五页检查须为 `original=true`、`patched=false`，才执行
`node $panelNewExecutor install $panelNewRelease`。安装后应为 `patched=true`、`original=false`，
此时不重复 install。将来恢复使用同一新版本的
`node $panelNewExecutor restore $panelNewRelease`，返回旧图片实验版三页及两个原厂依赖页。
各次 install/restore 会中断服务、暖重启并清除 RAM 图片，不是无人监督的批处理。

新安装仅操作 NOR 五个完整 4KiB 页 `0x927000`、`0x92d000`、`0x95a000`、`0x92b000`、
`0xccd000`，保留页内其余字节。安装 codec→net→aux→code→entry，
恢复 entry→code→aux→net→codec；
执行器负责保持其他核复位、原保护状态、cache/native 上下文闭包和整页验证。
只有整次 `app_complete=1`、`safe_to_resume=1`、GLOBAL 及暖读回闭合才算完成。

若出现 `NEEDS_INSPECTION`、未知/混合页、native 超时或读回不一致，保留停止状态、
供电和 capture，不删除标记，不反复安装/restore/reset。正常健康 MAIN 下的恢复结果
不能证明故意损坏 MAIN 后仍可救砖。完整断电验证按本次用户要求跳过，未借用历史结论。
自定义固件的 restore 只回到旧图片实验版，继续回原厂要走各历史版本自己的精确恢复链，见
[开发与维护流程](development.md)。不要在当前自定义固件上直接运行旧 `Set-Panel*.ps1`。
此前 g→四页自动返回版先用 g 自身冻结工具恢复精确基线，再由四页 a 自身工具安装，
完整页读回和暖启动通过。旧四页 a 自身恢复现已在本轮迁移中通过完整四页/native/context、
outer GLOBAL 和暖读回；新五页基线检查为 `original=true` 后完成五页安装、完整
native/cache/context、outer GLOBAL 和暖读回，fresh check 为 `patched=true`。
新五页自身硬件恢复尚未测试；能力 GET 返回三种格式，设置 GET60。
直接 Node PNG/JPEG 上传和完整RGB565读回通过，用户浏览器、LCD及米家验收仍单列。
此前 d→g 的 d restore
和 g install 结果保留在旧 g 记录中；g restore 另记在四页自动返回版 a 的结果中。
NOR restore 不会删除新增的 MMC 自动返回设置，配置保存与重启加载须另行验证。
原厂 OTA 不属于当前补丁维护流程，升级原厂映像后必须重新核对端口和完整基线。

## 本轮五页发布与验证范围

| 项目 | 值 |
| --- | --- |
| release | `maintained-images-five-page-20261008-a`，已安装 |
| 完整 ELF SHA-256 | `3f67d12758931a05fc22e20ddd89c51688ea9ec12de185ededce821b0ead79d3` |
| 主/辅助/网络/解码 BIN | 3368/396/4012/2916B |
| 471-input candidate SHA-256 | `992b58c7aa72a162aca23756088ce8951467fa1d624ba8c7889a155ab430021b` |
| 477-input freeze SHA-256 | `627a224c619b59a6813b47685e272cd19a4f8b25bb04af1bdbf690b31cf2a330` |
| writer mock | 116 项通过；旧四页的 93 项不能替代 |

420 项解码器实际 ARM、36 组 UI、34 组 HTTP、17 组设置、299 项 host HTTP 和 29 项网页
测试通过，12 项 release 工具测试通过。
这些离线检查不证明真实可用堆、RPC/GUI 时序、实屏显示、米家或断电恢复。
本轮五页安装与 fresh patched 检查通过；自身硬件 restore 尚未测试，完整断电按用户要求跳过。
直接 Node 上传2204B PNG、55134B JPEG均为202，完整RGB565匹配独立参考，计数依次1、2；
坏PNG CRC为422且当前JPEG和计数2不变；最后恢复默认PNG为202、计数3，完整像素匹配。
新鲜运行 alive/ready=1、pending=0、server=1/error=0、GUI cycles推进。
这些结果不等于LCD扫描、用户浏览器上传或米家验证，也不是请求耗时性能基准。
详情见 [本轮发布结果](../firmware/releases/maintained-images-20261008-a.json)。

正式网页版本 `2ee45a5f-6b04-42ce-80bb-2e92e4dc4cc5` 已部署，五项资源一致，
零浏览器错误和初始零自动 LAN 请求。agent Chrome 中实际点击 HTTPS 网页 Send，能力
GET200 及单次 6050B PNG POST202 通过，未添加 Content-Type。最初权限 prompt 时 GET
等待、没有 POST；测试通过 origin-scoped CDP 临时授予本地网络权限，结束后恢复为
prompt，不是用户点击许可，也不验证用户浏览器设置。上传后只读核验完整 RGB565 与
默认图参考一致，槽位和计数稳定，generation/displayed_generation=4、pending=0、
alive/ready=1、server=1/error=0，GUI cycles 推进。LCD、手势和米家仍待用户确认。

## 历史四页自动返回版检查点

旧 `maintained-idle-return-four-page-20261007-a` 为 main/aux/net 3344/396/4072B，
候选 SHA `6022cbd3e41cfc913a260ff17855582c47656318227dfb6defc55230be503f55`，
382-input freeze SHA `660534d525762b83b8029b3adebd82a20d84723d5706e53afc6f6790a5c64cb4`。

旧四页 a 的 76 组实际 ARM、93 项短路径 writer mock、12 项 release、290 项 host HTTP 和
19 项网页测试通过；四页安装及暖读回、设置接口读写、独立暖复位加载通过。正式网页
设置卡片已发布，用户读取/保存、定时返回、触摸延期及其他界面验收仍单列待确认。
旧 a 原始结果未测试自身恢复；本轮五页迁移中的成功恢复单列在新证据中，不改旧结果。
完整断电仍按用户要求跳过。
详细范围见 [a 发布结果](../firmware/releases/maintained-idle-return-20261007-a.json)。
