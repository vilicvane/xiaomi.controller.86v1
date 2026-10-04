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

## 构建原生程序（不连接设备）

在本机现有 WSL Ubuntu + LLVM18 环境：

```powershell
wsl.exe -d Ubuntu -- bash /mnt/c/Users/vilicvane/Projects/vilicvane/mi-panel/analysis/display-takeover/build-native-counter.sh
python -X utf8 analysis/display-takeover/prepare_native_counter_sectors.py
```

编译目标为 Cortex-A7 Thumb，freestanding、`-Oz`；链接器在
`tools/a7-llvm/extracted/usr/lib/llvm-18/bin/ld.lld`。构建脚本不启动 OpenOCD。
第二条命令从本地基线生成补丁扇区，因此需要完整备份。
这些路径对应当前机器；其他工作目录应按实际位置调整 WSL 路径。

当前白色计数程序：966 字节，BIN SHA-256
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

## 设备写入入口

已审核的现有原生计数安装/回退：

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
