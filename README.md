# Xiaomi Smart Panel

小米智能家庭面板（`xiaomi.controller.86v1`）的硬件分析、原生程序和自定义固件实验。
产品名称见[小米官网](https://www.mi.com/intelligent-panel)。

当前基线是这台设备的官方固件 **1.50.10**。已安装常驻 A7 下拉覆盖层测试版：
开机显示白色 `vilicvane +0`，点击在松手时加一；上滑收起，原界面顶边下拉
带出自定义界面，短拉松手回弹。第三个自定义物理键三击仍可往返。
当前smooth版本已刷入并通过整页读回、暖启动owner/动画终态检查。
它从最后提交的位置开始松手动画，并限制每帧推进量；手感和完整断电结果
独立记录在native-drawer-smooth-hardware-result.json。
之前ease版本已通过上下滑、三击、完整断电和米家控制，但上滑收起时有较大首帧跳跃。
之前的 broker 版本已经通过反复实机往返、完整断电和米家控制验证，可精确回退。

程序目前复用原固件的 NuttX、板级初始化、显示和触摸驱动及 MCU 服务，
包装原界面的启动入口，原应用只启动一次并在后台继续运行；还不是从源码
独立构建的完整替代固件。

## 从这里开始

- [工程经验与已验证状态](docs/engineering-notes.md)：硬件、电压、ABI、恢复闭包和实验陷阱。
- [构建、验证与本地材料](docs/development.md)：工具链、只在本地保存的备份及检查方法。
- [设备端计数程序](analysis/display-takeover/native-counter.md)：安装范围、回退和证据。
- [常驻界面切换程序](analysis/display-takeover/native-ui-broker.md)：三击、显示/触摸交接及新回退入口。
- [顶边下拉覆盖层](analysis/display-takeover/native-drawer.md)：跟手动画、整次手势拦截和回退到 broker。
- [覆盖层缓动](analysis/display-takeover/native-drawer-ease.md)：120ms三次缓出、独立版本和逐级回退。
- [松手动画节奏](analysis/display-takeover/native-drawer-smooth.md)：从已提交位置开始、缓入缓出及每帧进度上限。
- [启动时的 NOR 写入执行器](analysis/persistence/boot-nor-native-app-runner.md)：固定扇区写入流程。

源码主要在 `analysis/display-takeover/`、`analysis/persistence/` 和 `analysis/pinout/`；
`scripts/` 提供 PowerShell 入口，`diagnostics/` 保存 OpenOCD 配置。
较早的电脑驱动屏幕测试和恢复研究保留为历史代码，不代表推荐部署路径。

## 当前目标

在设备上通过**顶边下拉、上滑或第三个物理按键三击**，无需重启地切换原界面和自定义界面。
第三键已通过实际采样确认为 P3_1、低电平按下，目前没有米家动作绑定。
新程序交接显示和触摸所有权，保留原 UI/JS 状态。它不拦截原 MCU 按键通知，
以后给第三键绑定动作前需要另做过滤。

## 仓库包含什么

本仓库提交第一方源码、脚本、文档及选定的结构化分析证据。
原厂固件、完整 Flash/RAM 备份、设备凭据、网络日志、工具链、第三方参考源码和
生成文件保留在本地并被 Git 忽略。全新 clone 不能直接安装或回退设备；必须先准备
与这台设备、这个版本完全对应的本地材料，详见开发文档。
