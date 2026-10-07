# 86V1 自定义固件开发

目标设备为 `xiaomi.controller.86v1`，目前只支持本机精确的 1.50.10 映像。
这是和原厂系统一起运行的持久化补丁程序；复用原来的 Wi-Fi、米家、GUI 调度及显示驱动。
源码与历史 `analysis/` 实验分开维护，历史三击逻辑和冻结材料不删除、不重新生成。
图片上传和下拉画面是当前自定义固件的功能。

当前安装 `maintained-http-four-page-20261007-g`，主/辅助/网络为 2946/236/2976B。
d 精确恢复、g 四页读回、native 闭包、GLOBAL 和暖启动通过；真实 303 指向正式网页并
自动填写设备地址，用户报告上传正常，随后只读状态确认新 generation 已由 GUI 消费。
本轮没有自动发送 HTTPS 网页 POST；
[发布结果](releases/maintained-http-20261007-g.json)单列这些观察及其余待验收项。

## 交互

- 原界面顶边下拉打开自定义画面，自定义画面上滑返回原界面。
- 自定义画面连续两次短按，在最新上传图片和 IP:18086 地址页之间切换。
- 自定义固件没有第三物理键三击切换；原系统的物理按键动作继续由原系统处理。
- 观察到原系统息屏时，通过既有安全交接切回自定义画面，不调用背光接口。
  唤醒接触不参与双击，仍允许上滑返回原界面。

图片只在 RAM 中保存，重启恢复地址画面，程序本身持久化。双击切换不丢弃图片，
地址页也可接收新图。息屏检测依赖 GUI timer 能观察到原厂状态；两次采样之间发生的
完整 off/on 无法识别，首个唤醒画面和原系统的息屏调度需要单独实机验证。

## 构建与检查

Windows 使用 WSL Ubuntu 中的 LLVM18，Node24 运行 TypeScript 工具。构建入口：

```sh
sh firmware/build.sh
sh firmware/tests/test-http.sh
clang-18 -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
  -I firmware/include firmware/tests/tap-gesture.c -o build/tap-test
./build/tap-test
```

实际 ARM 模型在 Windows 使用本地 Unicorn/pyelftools 及历史模型 helper：

```powershell
python -X utf8 firmware/tests/test_ui_arm.py
$env:PANEL_TEST_FRONTEND_URL = "https://wan.sh/xiaomi-86v1/"
$env:PANEL_TEST_FRONTEND_ORIGIN = "*"
$env:PANEL_TEST_OUTPUT = "build/reviews/http-arm-$(Get-Date -Format yyyyMMdd-HHmmss).json"
python -X utf8 firmware/tests/test_http_arm.py
Remove-Item Env:PANEL_TEST_FRONTEND_URL, Env:PANEL_TEST_FRONTEND_ORIGIN, Env:PANEL_TEST_OUTPUT
node --test firmware/tools/release.test.ts
```

ARM 模型执行真实 ELF 指令，原生接口仍由 mock 提供；不证明真实 RPC 延迟、LCD、
并发或断电恢复。它们不调用历史结果写入器；HTTP 模型用 `PANEL_TEST_OUTPUT` 将新结果
写到独立路径，避免覆盖已冻结发布所绑定的结果。

构建默认前端 URL 为 `https://wan.sh/xiaomi-86v1/`，origin 为 `*`；当前 g 的冻结配置
与此相同。`GET /` 返回 303，将 endpoint 编码为普通 `device` query，前端自动读取。
默认版本不依赖电脑开发服务器。开发时仍可单独启动本地页面，手动输入设备地址：

```powershell
npm --prefix web run dev -- --host 0.0.0.0 --port 5173 --strictPort
```

需要另一个前端时，在 WSL 构建时覆盖配置；实际安装前仍需新 release 的审查与冻结：

```sh
PANEL_FRONTEND_URL=https://YOUR_FRONTEND_DOMAIN/panel \
PANEL_FRONTEND_ORIGIN=https://YOUR_FRONTEND_DOMAIN sh firmware/build.sh
```

URL 不能含凭据、fragment 或预置 `device` 参数；根页面跳转追加百分号编码的
`?device=`，若已有其他 query 则用 `&device=`。显式 `PANEL_FRONTEND_URL=''` 的构建
仍返回 200 本机说明页。ARM HTTP 模型的 `PANEL_TEST_FRONTEND_URL` 和
`PANEL_TEST_FRONTEND_ORIGIN` 必须与待测 ELF 的构建配置一致；上例对应默认构建。
设备不内置 PNG/JPEG 解码，前端或上传器提供 RGB565。
协议见 [HTTP 图片 API](../docs/http-image-api.md)。

当前 g 允许省略或任意声明 Content-Type，仍校验固定长度、VIMG 头和 FNV。
网页不添加该 header，cURL 不指定 `-H`。d 曾实测完整上传 202 和错误内容拒绝；
g 的正式 HTTPS 页面跳转和自动地址已实测，HTTPS 上传正常由用户报告，随后只读
generation/displayed_generation=1、pending/error=0。未自动采集其 POST 状态或 LCD
画面。44 组实际 ARM、261 项 host HTTP、93 项 writer mock、
12 项 release 工具及 9 项前端单元测试属于本轮离线证据。

## 安装与维护

构建输出、compiler headers、完整 NOR 页和 release 快照都保持 ignored，不提交 Git。
全新 clone 缺少精确原厂备份、历史 freeze 和工具链，不能直接用于刷写。

先完成 [离线发布流程](tools/README.md)、独立 storage/program/writer 审查、ARM 模型和
当前 writer mock，才创建不可覆盖的 freeze。执行器会串行核对 live 四页，并拒绝混合
状态；失败留下 `NEEDS_INSPECTION`，不自动重复 native call、写入或复位。

```powershell
node firmware/tools/hardware.ts check RELEASE
node firmware/tools/hardware.ts install RELEASE
node firmware/tools/hardware.ts restore RELEASE
```

上述操作须使用该 release 冻结的执行器和验证器。canonical 工具后续改动时，从仓库根目录
运行 `build/releases/RELEASE/snapshot/firmware/tools/hardware.ts`，使用其相邻冻结验证器。
install/restore 都会中断服务并暖重启；精确范围及诊断命令损失见
[1.50.10 端口](ports/1.50.10/README.md)。恢复目标为精确的旧图片实验版（`native-image-drawer`）
三页加原厂网络页，再使用该历史版本自己的回退器。不能直接对自定义固件使用旧三页 writer。

安装基线中的“三页”是三个已安装旧图片实验程序的 4KiB Flash 区域，第四个网络区域仍
为原厂字节，四页都必须逐字节匹配；它不是屏幕界面页，也不是任意原厂设备的首刷起点。
install 只接受这个精确基线，不能叠加在旧自定义固件上。
本轮先用 d 自己的冻结执行器完整恢复精确基线，再安装 g，四页及 native/cache/context
闭包、GLOBAL 与暖启动读回均通过；g 自己的硬件 restore 尚未执行。main/aux 与 d/c
字节相同，也不继承它们的实屏、双击、息屏或米家用户观察。完整断电仍按用户要求跳过。
