# 可维护的图片抽屉程序

目标设备为 `xiaomi.controller.86v1`，目前只支持本机精确的 1.50.10 映像。
这是和原厂系统一起运行的持久化补丁程序；复用原来的 Wi-Fi、米家、GUI 调度及显示驱动。
源码与历史 `analysis/` 实验分开维护，历史三击逻辑和冻结材料不删除、不重新生成。

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
python -X utf8 firmware/tests/test_http_arm.py
node --test firmware/tools/release.test.ts
```

ARM 模型执行真实 ELF 指令，原生接口仍由 mock 提供；不证明真实 RPC 延迟、LCD、
并发或断电恢复。它们不调用历史结果写入器，新的结果只写维护版的结果文件。

默认 `GET /` 返回本机说明页。未来前端有实际网址后，在 WSL 构建时配置：

```sh
PANEL_FRONTEND_URL=https://YOUR_FRONTEND_DOMAIN/panel \
PANEL_FRONTEND_ORIGIN=https://YOUR_FRONTEND_DOMAIN sh firmware/build.sh
```

URL 不能含凭据或 fragment；根页面跳转时把设备 endpoint 放在 fragment 中，供前端读取。
未配置的 origin 默认为 `*`。设备不内置 PNG/JPEG 解码，前端或上传器提供 RGB565。
协议见 [HTTP 图片 API](../docs/http-image-api.md)。

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
