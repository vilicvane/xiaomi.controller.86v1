# 小米智能家庭面板 86V1

为 `xiaomi.controller.86v1` 开发的自定义固件。保留原系统的米家功能，增加设备端运行的
自定义功能。目前支持下拉显示自定义图片，通过网页裁切、缩放并发送画面。

## 刷机

目前基于原厂 **1.50.10** 开发，刷写工具只支持已经核对过的设备状态，需要本机备份和
对应安装材料。仓库暂不提供让未修改的原厂面板直接首刷的通用安装包。

### 准备什么

- **MuseLab nanoDAP 调试器**和 USB 数据线。见 [官方项目](https://github.com/wuxx/nanoDAP)、
  [购买入口](https://item.taobao.com/item.htm?id=586425846353)及
  [用户手册](https://github.com/wuxx/nanoDAP/blob/master/user_manual.md)。
- **烧录探针夹**：选择适合主板测试点间距的 pogo pin / 弹簧探针夹具，方便接触调试焊盘。
  这里需要测试点夹具，SOIC8 Flash 芯片夹不能替代；也可以焊接短导线。
- 短连接线、万用表，以及稳定的隔离 **5V** 低压供电。
- Windows 电脑和 Node.js 24。自行编译固件还需要 WSL Ubuntu；使用已准备的安装材料
  刷写时，在 Windows PowerShell 中操作。

### 怎样连接

断电后连接主板调试点，使用 SWD：

| nanoDAP | 面板主板 |
| --- | --- |
| GND | GND |
| SWDIO / IO | JTMS |
| SWCLK / CK | JTCK |

JTDI/JTDO 不需要连接。供电单独接到**已经确认的主板低压供电入口**，并与调试器共地。
本机输入 5V 可以正常启动；5V 不能接到调试点或芯片引脚。裸板调试时断开原市电供电板，
不要在裸露 220V 下连接电脑。

### 刷写流程

1. 核对面板型号、原厂版本、供电入口和接线。
2. 读取并保存这台设备的完整 NOR 备份。
3. 使用与本机状态匹配的安装材料，先执行只读检查，确认匹配后再安装。
4. 面板启动后，按下面的功能说明查看地址并发送图片。

具体命令、环境准备以及升级和恢复步骤见 **[完整刷写指南](docs/flashing.md)**。
程序保存在 Flash 中，重启后仍会运行；上传的图片目前只保存在 RAM 中，重启后需要重新发送。
当前图片格式支持版已安装，安装与验证范围见 [发布结果](firmware/releases/maintained-images-20261008-a.json)。

## 功能：自定义图片

图片编辑页面：[wan.sh/xiaomi-86v1](https://wan.sh/xiaomi-86v1/)。

1. 让面板连上 Wi-Fi，手机或电脑接入能访问它的局域网。
2. 从原界面最顶边向下拖，打开自定义画面；向上拖返回原界面，无需重启。
3. 双击自定义画面，查看 IP 地址和端口；再双击回到图片。
4. 在浏览器访问面板显示的地址，例如 `http://PANEL_IPV4:18086/`，会跳到图片编辑页面，
   并通过 `?device=` 自动填写面板地址。也可以直接打开网页后手动填写。
5. 选择或拖入图片，拖动调整位置，用滚轮或双指缩放。中央框内是面板最终显示的
   **480×320** 画面，预览按面板像素放大显示。
6. 点击“发送画面”。如果浏览器询问本地网络访问权限，请允许；收到成功提示后查看面板画面。

页面支持 PNG、JPEG、WebP 和 SVG，也可用方向键移动、`+` / `-` 缩放、`0` 重置。
可以下载 PNG 留存或直接用于 API 上传，也保留完整 `.vimg` 导出。

当前固件取消了第三物理键三击切换。原界面息屏后会切回自定义画面，下次唤醒时显示它，
继续使用原系统的背光和息屏设置。双击和上下滑不会清除已上传图片。

### 自动返回

新版本可设置原界面连续未触摸多少秒后返回自定义图片，默认 60 秒；`0` 关闭定时返回，
范围为 0–3600 秒。从网页导航进入“设置”，即可读取和保存等待时间，保存后按重启保留设计。
物理按键不计入触摸，原系统的息屏规则独立生效。

设置读写与暖重启保留已在此前版本验证；当前版重新读取为 60 秒，
自动返回和触摸延期的使用体验仍待独立确认。
使用方法和接口约定见 [自动返回说明](docs/auto-return.md)。

## 图片 API

面板提供 `POST http://PANEL_IPV4:18086/api/image`，支持直接发送 **480×320 PNG 或 JPEG**，
也接受完整 `.vimg`。设备按文件内容识别格式；网页负责裁切缩放，其他客户端可参考
[HTTP 图片 API](docs/http-image-api.md)。

下载 PNG 后，也可以在能访问面板的电脑上发送：

```sh
curl --data-binary "@picture-480x320.png" "http://PANEL_IPV4:18086/api/image"
```

替换 IP 和文件名时，保留文件名前的 `@`，它表示读取文件内容。收到 HTTP 202 表示面板
已接收并排队显示，图片不会写入 Flash。

PNG 限 8-bit 非隔行；JPEG 支持常见单扫描 baseline，不支持 progressive 或 CMYK。
透明图片铺黑底。文件最大 1MiB，设备不处理 EXIF 旋转；完整格式范围见协议文档。
网页发送时自动查询支持能力，旧固件仍使用 VIMG。

## 开发

设备端源码在 [firmware](firmware/README.md)，网页源码在 [web](web/README.md)。
网页采用 Vite + TypeScript，图片在浏览器内处理，直接发送到局域网面板。

使用 Node.js 24，在仓库根目录运行：

```sh
npm --prefix web ci
npm --prefix web run dev
```

网页测试和构建分别使用 `npm --prefix web run test`、`npm --prefix web run build`。
Cloudflare 发布使用 `npm --prefix web run deploy`，正式路径为 `/xiaomi-86v1/`。
设备端编译、发布与维护流程见 [固件开发说明](firmware/README.md)。

| 文档 | 内容 |
| --- | --- |
| [完整刷写指南](docs/flashing.md) | 调试器与探针夹、供电接线、备份、安装和恢复 |
| [架构](docs/architecture.md) | 自定义固件与原系统的关系、显示和触摸交接 |
| [开发与维护](docs/development.md) | 编译、冻结发布、安装基线和精确回退 |
| [工程约束](docs/engineering-notes.md) | 硬件操作、版本专用接口及失败处理 |
| [前端说明](docs/frontend.md) | 裁切预览、导出、浏览器权限和部署 |
| [HTTP 图片 API](docs/http-image-api.md) | 请求格式、响应及连接限制 |
| [研究记录](docs/research-index.md) | 配网恢复、硬件探索和历史版本 |
| [自动返回说明](docs/auto-return.md) | 定时返回、重启保留的设置及 API |
| [当前发布结果](firmware/releases/maintained-images-20261008-a.json) | 本次安装和验证范围 |

历史实验保留在 `analysis/`、`scripts/` 和研究文档中，包括此前的第三键三击逻辑。
备份、设备身份、原始日志及第三方工具链不在 Git 中分发。
