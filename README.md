# Xiaomi Smart Panel Image Drawer

为小米智能家庭面板 `xiaomi.controller.86v1` 开发可远程更新内容的自定义下拉屏幕。
设备端接收局域网上传的图片，与原界面在运行中交接显示和触摸；原米家应用继续运行。

目前交付是针对**本机官方 1.50.10 映像**的持久化原生程序补丁，复用 NuttX、板级驱动、
网络和 MCU 服务。它还不是能适用于任意同型号设备的完整替代固件。仓库不分发原厂映像、
设备身份或包含它们的刷机包。

## 当前可用功能

- 默认画面显示设备查询的 `IP:18086`；上传后显示 480×320 图片。
- 原界面顶边下拉展开自定义画面，上滑返回原界面；当前安装版也支持第三键三击。
- 图片接收、合成和触摸运行在设备上，电脑只参与上传。
- 程序写入 Flash 常驻；图片仅保存在 RAM，重启后恢复地址画面。

```powershell
python -X utf8 analysis/image-push/push_panel_image.py PANEL_IP --image picture.png
```

将 `PANEL_IP` 换成面板显示的非零地址。PNG/JPEG 在电脑通过 Pillow 转成 RGB565；
`--pattern` 和 `--raw` 不需要 Pillow。当前端口使用 TCP `VIMG/VACK`，**没有 HTTP 页面**。
上传参数和协议见 [图片上传协议](docs/image-upload-protocol.md)。

当前安装版是 `native-image-drawer`：3416B 主程序、424B 辅助程序，93 项输入独立冻结。
三页完整读回、普通重启、两张完整图片、上下滑、三击往返及米家在线控制均有独立记录。
完整断电测试按用户要求跳过；异常连接不保证收到完整拒绝确认，原生网络调用没有严格
墙钟上限。验证范围见 [当前架构](docs/architecture.md)，详细证据见
[硬件结果](analysis/persistence/native-image-drawer-hardware-result.json)。

## 开发与研究入口

| 文档 | 内容 |
| --- | --- |
| [当前架构](docs/architecture.md) | 启动、GUI/网络职责、RAM 布局、已验证状态 |
| [图片上传协议](docs/image-upload-protocol.md) | 数据格式、客户端使用、确认及超时限制 |
| [工程约束](docs/engineering-notes.md) | 供电、调试、版本专用 ABI、Flash 和失败处理 |
| [开发与维护流程](docs/development.md) | 本地材料、冻结校验、新版本开发和精确回退 |
| [研究与历史版本索引](docs/research-index.md) | 配网恢复、显示接管、版本演进和原始归档 |
| [维护需求](docs/maintenance-plan.md) | 研究整理后的四项交互及 Web 入口需求 |

研究代码仍在 `analysis/`，PowerShell 入口在 `scripts/`，OpenOCD 配置在 `diagnostics/`。
已经冻结的历史集合保留原路径和字节，不能为了整理目录而移动或重新生成。

## 仓库与安装材料

仓库保存第一方源码、文档和经过审查的结构化证据。完整 NOR/RAM 备份、扇区镜像、
凭据、网络日志、工具链、第三方参考源码及生成的 BIN/ELF/Tcl 数组只在本地保存。
全新 clone 不能直接安装或回退设备；必须准备与该设备、版本及安装基线匹配的材料。

下一阶段先移除三击入口、增加双击地址画面及浏览器入口，并研究锁屏后自动打开；
这些是 [已记录的维护需求](docs/maintenance-plan.md)，不属于本次研究整理的实现结果。
