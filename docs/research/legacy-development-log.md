# 原始开发记录归档

归档于 2026-10-07，保留整理前的记录正文。下列构建、生成和刷写命令属于各自历史版本；冻结后不得照抄重建或用于当前设备。当前维护入口见 [开发流程](../development.md)，精确回退链见 [研究索引](../research-index.md)。

---

# 构建、验证与本地材料

## 仓库与本地材料的边界

仓库保存第一方代码及明确准入的 review JSON；所有其他文件默认被忽略。
完整 NOR、RAM、扇区镜像、设备身份、Wi-Fi/云日志及下载工具链仍在工作目录，
不会随 Git 提交同步。这些本地材料也是复现实验和精确回退的必要输入。

不要删除 `backups/` 或在其他设备上复用其中的身份数据。NOR 备份不覆盖 MMC `/data`。
历史 pink 审核材料位于 `analysis/persistence/native-counter-pink-reviewed/`，只在本地保存。

当前冻结安装器依赖以下未入库材料：

- 对应设备 1.50.10 的精确 16 MiB NOR 备份。
- `native-counter.elf`、`native-counter.bin` 和两个原始/补丁 4 KiB 扇区。
- 生成的 `diagnostics/boot-nor-native-app-stage-inputs.cfg` 和
  `analysis/persistence/boot-nor-read-runner-data.cfg`。
- `tools/xpack-openocd-0.12.0-7/`，及 WSL Ubuntu 的 LLVM18 与本地 `ld.lld`。
- 分析脚本需要的 capstone、公开头文件及反汇编输入；下载参考材料默认不入库。

缺少材料时应报告缺失，不用不完整的数据绕过 SHA 检查。

## 构建旧计数原型（不连接设备）

在本机现有 WSL Ubuntu + LLVM18 环境：

```powershell
wsl.exe -d Ubuntu -- bash /mnt/c/Users/vilicvane/Projects/vilicvane/mi-panel/analysis/display-takeover/build-native-counter.sh
python -X utf8 analysis/display-takeover/prepare_native_counter_sectors.py
```

编译目标为 Cortex-A7 Thumb，freestanding、`-Oz`；链接器在
`tools/a7-llvm/extracted/usr/lib/llvm-18/bin/ld.lld`。构建脚本不启动 OpenOCD。
第二条命令从本地基线生成补丁扇区，因此需要完整备份。
这些路径对应当前机器；其他工作目录应按实际位置调整 WSL 路径。

旧白色计数程序：966 字节，BIN SHA-256
`80a92ac659f795546258b24b31780fae353f0dd5e543a97c0d47b8b139ecae9d`。

当前补丁 manifest SHA-256：
`55fbb71be4fe4abd40a245f72f303073cc5afce0288a5aa238bf35ea475af4ed`。
旧文档里的 `7a0c246...` 指首次 pink 审核版本，不是当前 manifest。

`.gitattributes` 禁用自动换行转换，因为安装器用 SHA-256 核对源码、配置和二进制
的完整字节。即使只是格式化源码，冻结检查也会拒绝。新功能需要新的编译、独立
审查、离线校验和冻结输入集合；不要将重新生成 SHA 当作完成了审查。

## 离线验证

在现有材料齐全时，下面命令仅核对冻结输入，不连接、复位或写设备：

```powershell
python -X utf8 analysis/persistence/run_native_counter_firmware.py install
```

`analysis/persistence/test_native_app_runner_offline.py` 是固定写入器的独立 Jim mock。
最新白色输入的 run-4 覆盖 28 条路径，包括整扇区不一致、擦除/编程超时、状态位
变化、半写入口表和不允许的地址/数据。mock 不执行 ARM 指令，不证明屏幕、触摸
或冷启动成功。运行 mock 需要本地 OpenOCD 和完整生成输入。

Python 源码可通过 AST 编译检查语法；不要为了提交而连接设备或重复刷写。

## 常驻切换程序与设备入口

当前 broker 用独立源码、输入集合和写入入口；旧 counter 的冻结材料仍保留原字节。
不要在已装 broker 的设备上调用旧 counter 安装/回退命令。

```powershell
wsl.exe -d Ubuntu -- bash /mnt/c/Users/vilicvane/Projects/vilicvane/mi-panel/analysis/display-takeover/build-native-ui-broker.sh
python -X utf8 analysis/display-takeover/test_ui_broker_arm.py
python -X utf8 analysis/persistence/prepare_native_ui_broker_inputs.py
python -X utf8 analysis/persistence/test_native_ui_broker_runner_offline.py
python -X utf8 analysis/persistence/run_native_ui_broker_firmware.py install
```

前四条只构建/模拟/准备；最后一条只核对冻结输入，**没有 `--execute` 不访问设备**。
ARM 模型需要本地 `tools/python-ui-broker/` 的 Unicorn、pyelftools；原生 API/IRQ/调度
使用 stub。不得把模拟结果当作真实驱动/显示/触摸证明。

BIN 为2652字节（ELF allocated 2629，另外23字节为地址空隙），无新增.data/.bss。
新 freeze 36项还绑定key3-gesture.h、实际ELF模型结果及33路径Jim测试摘要。
freeze工具需要明确的manifest hash、至少两个独立review artifact hash及当前测试摘要；
它只冻结已经审查的输入。已经冻结的列表不可覆盖，新版本应使用新的审核集合。

已审核的新设备入口：

```powershell
.\scripts\Set-PanelNativeUiBroker.ps1 -Mode install
.\scripts\Set-PanelNativeUiBroker.ps1 -Mode restore
```

同样会暂停到BOOT恢复上下文、写两扇区并重启；恢复原界面后才能再安装旧counter。
broker公共流程只接受完整original/original或broker/broker，不处理半写表/未知基线。
实机状态见native-ui-broker-hardware-result.json，流程/副作用见native-ui-broker.md。

## 旧计数原型的设备入口

以下仅用于原始/旧counter基线：

```powershell
.\scripts\Set-PanelNativeCounter.ps1 -Mode install
.\scripts\Set-PanelNativeCounter.ps1 -Mode restore
```

它们会暂停恢复上下文、写入两个固定扇区并重启，必须按照工程经验中的当前
基线、供电和失败恢复要求运行。全新 clone 或新固件版本不能直接运行这些命令。
早期 `Test-PanelDisplay.ps1`、`Test-PanelPixels.ps1` 和 `Test-PanelTouchCounter.ps1`
是电脑参与的历史实验；常驻、重启自动进入的程序由 `Set-PanelNativeCounter.ps1`
安装，不要混淆两类测试。

## 证据入口与状态更新

- `native-counter-hardware-result.json`：当前白色安装与此前粉色冷启动，分别记录。
- `native-counter-frozen-inputs.json`：所有设备操作输入的完整 hash。
- `native-counter-patch-inputs-1.50.10.json`：扇区范围、布局和原始/补丁 hash。
- `ui-switch-assessment-1.50.10.json`：待实现的双向热切换状态机。
- `original-ui-return-entry-options-1.50.10.json`：入口候选及已定位、尚未验证的边界。

新的实际实验要保存独立 capture 目录，记录源码/二进制 hash、读回、恢复状态
和用户观察。更新总结时区分旧结果、新结果和静态假设，不覆盖旧证据。

## 下拉覆盖层独立版本

源码与行为说明见 `analysis/display-takeover/native-drawer.md`。构建只操作本地文件：

```powershell
wsl.exe -d Ubuntu -- bash /mnt/c/Users/vilicvane/Projects/vilicvane/mi-panel/analysis/display-takeover/build-native-drawer.sh
wsl.exe -d Ubuntu -- bash /mnt/c/Users/vilicvane/Projects/vilicvane/mi-panel/analysis/display-takeover/test-drawer-gesture.sh
python -X utf8 analysis/display-takeover/test_native_drawer_arm.py
python -X utf8 analysis/persistence/run_native_drawer_firmware.py install
```

最后一条没有 `--execute` 时只核对46项冻结输入。3224B程序通过12项host手势测试、
16组实际ARM模型、38项Jim写入器路径；模型不证明SMP/IRQ、真实动画帧率及冷启动。

这套安装器只接受精确 broker v1 两页，`Set-PanelNativeDrawer.ps1 -Mode restore`
也恢复 broker v1。若要再回原 stock，先用 drawer 回 broker，再用 broker 回 stock。
旧 counter/broker/drawer 的三个冻结集合不可互相覆盖，新功能仍须新建审查集合。

之前的独立 `native-drawer-ease` 版本为3264B、45项冻结。构建脚本为
build-native-drawer-ease.sh，模型为test_native_drawer_ease_arm.py，安装入口为
Set-PanelNativeDrawerEase.ps1。无 --execute 的run_native_drawer_ease_firmware.py
只核对材料。其restore先回首版drawer，再依次回broker和stock；每套冻结保留原字节。

当前松手后首帧跳跃的优化使用独立 `native-drawer-smooth` 版本（3368B，47项冻结）。
原ease的源码/ELF/安装输入仍冻结。新实际ARM模型22组与写入器41项Jim路径通过；
各自验证动画进度/触摸交接和固定写入流程，不能代替LCD手感及完整断电观察。

```powershell
wsl.exe -d Ubuntu -- bash /mnt/c/Users/vilicvane/Projects/vilicvane/mi-panel/analysis/display-takeover/build-native-drawer-smooth.sh
python -X utf8 analysis/display-takeover/test_native_drawer_smooth_arm.py
python -X utf8 analysis/persistence/run_native_drawer_smooth_firmware.py install
```

最后一条没有 `--execute` 不访问设备；除了新冻结输入，它还核对broker、drawer、
ease三个旧集合的全部材料。已经冻结后不要随意重建或更新测试摘要。
`Set-PanelNativeDrawerSmooth.ps1 -Mode restore` 返回精确ease版本，再逐级回退。

## GitHub 信息卡独立版本

`native-github-card` 将自定义界面的计数文字换成 GitHub 标志、用户名、项目名称
和 `Star on GitHub` 提示。说明及资源来源见
`analysis/display-takeover/native-github-card.md`。它沿用 smooth 的手势和所有权交接，
使用新的源码、像素参考、ARM 模型和安装材料，不改写任何历史冻结集合。

```powershell
wsl.exe -d Ubuntu -- bash /mnt/c/Users/vilicvane/Projects/vilicvane/mi-panel/analysis/display-takeover/build-native-github-card.sh
python -X utf8 analysis/display-takeover/test_native_github_card_arm.py
python -X utf8 analysis/persistence/run_native_github_card_firmware.py install
```

最后一条没有 `--execute` 只核对新冻结及 broker、drawer、ease、smooth 四套旧材料。
新安装只接受完整、精确的 smooth 两页；`Set-PanelNativeGitHubCard.ps1 -Mode restore`
返回 exact smooth，然后才能使用 smooth 的回退入口。不能在 card 上直接运行旧 writer。
参考图和真实 ARM framebuffer 的逐像素核对只验证绘图，不代替实机显示及手势观察。
本次用户明确跳过完整断电测试，证据中须记录跳过，不能写成通过。

card 的两个生成 session cfg 含从旧模板复制的原厂 BOOT 校验页数据，因此仅在本地
保留并精确忽略，冻结列表保存其哈希。不要将它们或 stage inputs 的固件 word 数组
加入 Git。第一方准备器、runner 和独立审查记录仍提交；完整本地材料不可由 clone 代替。

## GitHub 卡片的临时点击反馈

`native-github-tap` 是另一套独立材料，行为说明见
`analysis/display-takeover/native-github-tap.md`。主 BIN3392B、辅助 BIN291B，
实际 ELF 使用两个不连续地址范围，不能生成含中间地址洞的单一平铺 BIN。
184B context 的新字段为 feedback_ms/+176、feedback_pending/+180。

```powershell
python -X utf8 analysis/persistence/run_native_github_tap_firmware.py install
```

没有 `--execute` 时只检查材料。40组当前 ARM ELF 模型和65项三页写入器 Jim mock
通过；程序/辅助槽与写入器分别经过独立审查，作者自检另行标注。模型和 mock
不能代替实屏观察。已经冻结后不要重建、重新 prepare 或更新测试摘要。

该版本只接受精确 GitHub card 的代码/入口页和已只读核对的原始辅助页。
安装依次写 NOR95a000、92b000、ccd000；辅助页完整核对后才更新引用它的主代码。
回退顺序为入口、主代码、辅助页，返回精确 card。辅助代码只能占
`3807a764..3807a920` 内的原工厂 socket worker；相邻背光回调、JSON helper 和
主代码共享 helper/be70 保留。辅助 worker 的旧工厂入口已被替换，不能据此
借用整个工厂线程区域。第三页原始内容、完整扇区备份和调用 capture 留在本地。

```powershell
.\scripts\Set-PanelNativeGitHubTap.ps1 -Mode restore
```

这会中断服务并重启一次；之后才可用 card 的 restore 回 smooth，再逐级回退。
两个 tap session cfg 同样含原厂 BOOT 校验字节，必须保持精确文件、仅本地存放。
不要 force-add stage inputs、session、BIN/ELF、扇区或运行内存。
暖启动及用户观察记录在新的 native-github-tap-hardware-result.json；完整断电按
用户要求跳过，不能借用旧版断电或米家控制结果。

## 点击反馈计时与局部绘图的独立版本

`native-github-tap-fast` 使用独立C/Thumb入口/链接器/构建脚本、实际ARM模型和三页
安装材料，说明见 `analysis/display-takeover/native-github-tap-fast.md`。主BIN3336B
止于3804be10，辅助BIN431B止于3807a913；仍分别生成两段BIN，禁止平铺地址空洞。
复用已冻结tap的logo和像素参考，旧源码/模型/资产及61项输入保持原字节。

53组实际ARM模型和68项Jim写入器mock通过，68项材料已独立冻结，SHA-256为
`96588070da46764460c72d0ba1e71c635c1de39d226842ff3e71c2226e4a5b6c`。
184B/46-word运行采样保留+176 feedback_ms和+180 feedback_pending；pending0表示
已接受并锚定，1表示新计数待成功PAN，2表示已成功PAN待有效CLOCK。
冻结后不要重新编译、prepare、运行旧结果生成器或改写测试摘要来更新材料。

```powershell
python -X utf8 analysis/persistence/run_native_github_tap_fast_firmware.py install
```

没有 `--execute` 时只核对冻结输入及六套旧UI集合，不访问设备。本版安装闭包、
普通重启后的三页完整SHA读回、MCU状态和暖启动owner/ready/phase150已通过。
新版本用户触摸与切换观察仍待确认；ARM/mock通过不能证明LCD吞吐或米家控制。
安装仍为aux→code→entry，回退仍为entry→code→aux，每页完整核对才继续。
入口只接受精确tap v1三页作为安装基线，restore返回精确tap v1三页；未知或混合
主/辅页不能套用历史writer。只有fast恢复tap v1后才执行下一步：

```powershell
.\scripts\Set-PanelNativeGitHubTapFast.ps1 -Mode restore
.\scripts\Set-PanelNativeGitHubTap.ps1 -Mode restore
```

第二步返回card及原始辅助页，之后card→smooth→ease→drawer→broker→stock各用自己的
restore。每一步会中断服务并重启，不要将这个顺序改成跨版本直接回退。

fast两个session cfg沿用原厂BOOT校验字节，仅本地存放并由冻结表绑定哈希；stage
Tcl数组、BIN/ELF、扇区、运行dump和原始帧继续被忽略。临时数字绘制只更新RAM，
软件画布写入减少不等于原PAN已局部传输；8条原生输入ring没有增加或改成无损队列。
本版实机及用户观察应单独记在native-github-tap-fast-hardware-result.json。完整断电
按用户要求跳过，不再询问，不借用旧版在线/控制或断电结果。


## 设备端图片推送程序

本轮新代码在analysis/image-push，说明见native-image-drawer.md；历史display-takeover
输入不移动、不重新生成。主3416B+辅助424B，212B context；33组当前实际ARM模型、
12组独立重点检查、70项三页Jim mock和独立程序/容量/writer审查通过，93项输入冻结。
已经冻结后禁止重建、prepare或写旧测试摘要。新独立peer复核源码是
analysis/persistence/review_native_image_drawer_writer_peer.py。

```powershell
python -X utf8 analysis/persistence/run_native_image_drawer_firmware.py install
python -X utf8 analysis/image-push/push_panel_image.py PANEL_IP --pattern
python -X utf8 analysis/image-push/push_panel_image.py PANEL_IP --image picture.png --fit contain
.\scripts\Set-PanelNativeImageDrawer.ps1 -Mode restore
```

第一条无--execute只核对全部新/旧冻结输入，不访问设备。PANEL_IP来自面板默认地址
画面；port18086、TCP VIMG，不是HTTP。PNG/JPEG在电脑通过Pillow转换到480x320
RGB565 LE，--pattern/--raw不依赖Pillow。图片校验后在GUI安全边界发布，ACK0表示
已排队，不等于LCD扫描。第二次上传会替换前一张图；图片仅RAM，重启恢复地址。

restore只返回精确tap-fast，之后才可用tap-fast→tap-v1→card→smooth→ease→drawer→
broker→stock各自入口；不能直接套旧两页/三页writer。BOOT caller168B和完整stage/
outer按命名替换保持控制流程；每页全读回及safe-to-resume/complete都通过才GLOBAL。
新stage/session/扇区/BIN/ELF与raw capture保持local ignored，仓库只存源码及审查元数据。

普通重启安装、两张完整上传及设备IP显示已验证；用户确认两张图、上下滑、三击
和米家在线控制正常，后续只读核对generation/displayed_generation2、server1/error0。
首次拒绝/客户端提前结束可能没有完整ACK，空连接退出实测10.038秒；native RPC不
保证严格墙钟界限。完整断电按用户要求继续跳过。字体资源可行性与ACK条件路径
分别记录在image-push的安全JSON中；它们没有实施字体文件读取或原生字形调用。
