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
