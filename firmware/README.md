# 可维护的图片抽屉程序

目标设备为 `xiaomi.controller.86v1`，目前只支持本机精确的 1.50.10 映像。
这是和原厂系统一起运行的持久化补丁程序；复用原来的 Wi-Fi、米家、GUI 调度及显示驱动。
源码与历史 `analysis/` 实验分开维护，历史三击逻辑和冻结材料不删除、不重新生成。

当前安装 `maintained-http-four-page-20261007-d`，主/辅助/网络为 2946/236/2948B，
四页读回、native 闭包、暖启动、真实 303 和网页/cURL 上传通过。
[发布结果](releases/maintained-http-20261007-d.json)分列默认图/手机跳转用户确认与其余待验收项。

## 交互

- 原界面顶边下拉打开自定义画面，自定义画面上滑返回原界面。
- 自定义画面连续两次短按，在最新上传图片和 IP:18086 地址页之间切换。
- 维护版没有第三物理键三击切换；原系统的物理按键动作继续由原系统处理。
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
$env:PANEL_TEST_OUTPUT = "build/reviews/http-arm-$(Get-Date -Format yyyyMMdd-HHmmss).json"
python -X utf8 firmware/tests/test_http_arm.py
Remove-Item Env:PANEL_TEST_OUTPUT
node --test firmware/tools/release.test.ts
```

ARM 模型执行真实 ELF 指令，原生接口仍由 mock 提供；不证明真实 RPC 延迟、LCD、
并发或断电恢复。它们不调用历史结果写入器；HTTP 模型用 `PANEL_TEST_OUTPUT` 将新结果
写到独立路径，避免覆盖已冻结发布所绑定的结果。

没有配置前端 URL 的构建在 `GET /` 返回本机说明页。当前 d 已配置临时电脑 LAN
页面 `http://PC_LAN_IPV4:5173/`，真实 303 和 Chrome 跟随已验证；地址只在私有构建
材料中保存。启动该页面：

```powershell
npm --prefix web run dev -- --host 0.0.0.0 --port 5173 --strictPort
```

电脑须保持该局域网地址并运行开发服务器。未来前端有实际网址后，在 WSL 构建时配置：

```sh
PANEL_FRONTEND_URL=https://YOUR_FRONTEND_DOMAIN/panel \
PANEL_FRONTEND_ORIGIN=https://YOUR_FRONTEND_DOMAIN sh firmware/build.sh
```

URL 不能含凭据或 fragment；根页面跳转时把设备 endpoint 放在 fragment 中，供前端读取。
未配置的 origin 默认为 `*`。设备不内置 PNG/JPEG 解码，前端或上传器提供 RGB565。
协议见 [HTTP 图片 API](../docs/http-image-api.md)。

当前已安装 d 允许省略或任意声明 Content-Type，仍校验固定长度、VIMG 头和 FNV。
网页不添加该 header，cURL 不指定 `-H` 的完整 VIMG 上传已实测 202；云 HTTPS 尚未验证。

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
[1.50.10 端口](ports/1.50.10/README.md)。恢复目标为 exact image drawer 加 stock network 页，
再使用历史 image drawer 回退器。不能直接对维护版使用旧三页 writer。

本轮先用 c 的冻结执行器完整恢复精确基线，再安装 d；c 恢复已实测闭合，d 的硬件
恢复尚未执行。d 的 UI BIN 与 c 相同，但不继承 c 的双击、息屏或米家用户观察。
