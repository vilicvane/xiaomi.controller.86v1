# Xiaomi Smart Panel

小米智能家庭面板（`xiaomi.controller.86v1`）的硬件分析、原生程序和自定义固件实验。
产品名称见[小米官网](https://www.mi.com/intelligent-panel)。

当前基线是这台设备的官方固件 **1.50.10**。已安装一个随开机自动运行的
A7 原生计数程序：显示白色 `vilicvane +0`，每次触摸按下加一，长按和拖动
只计一次。它直接读取触摸设备、提交屏幕像素，不需要电脑绘图或输入循环。

程序目前复用原固件的 NuttX、板级初始化、显示和触摸驱动及 MCU 服务，
替换原界面的启动入口；还不是从源码独立构建的完整替代固件。

## 从这里开始

- [工程经验与已验证状态](docs/engineering-notes.md)：硬件、电压、ABI、恢复闭包和实验陷阱。
- [构建、验证与本地材料](docs/development.md)：工具链、只在本地保存的备份及检查方法。
- [设备端计数程序](analysis/display-takeover/native-counter.md)：安装范围、回退和证据。
- [启动时的 NOR 写入执行器](analysis/persistence/boot-nor-native-app-runner.md)：固定扇区写入流程。

源码主要在 `analysis/display-takeover/`、`analysis/persistence/` 和 `analysis/pinout/`；
`scripts/` 提供 PowerShell 入口，`diagnostics/` 保存 OpenOCD 配置。
较早的电脑驱动屏幕测试和恢复研究保留为历史代码，不代表推荐部署路径。

## 当前目标

在设备上通过**第三个自定义物理按键三击**，无需重启地切换原界面和自定义界面。
此检查点仅记录方案：实体按键与事件的对应、三击拦截、原界面完整退出和再次
初始化仍待验证，目前安装的计数程序没有切换功能。

## 仓库包含什么

本仓库提交第一方源码、脚本、文档及选定的结构化分析证据。
原厂固件、完整 Flash/RAM 备份、设备凭据、网络日志、工具链、第三方参考源码和
生成文件保留在本地并被 Git 忽略。全新 clone 不能直接安装或回退设备；必须先准备
与这台设备、这个版本完全对应的本地材料，详见开发文档。
