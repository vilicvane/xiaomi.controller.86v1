# 86V1 自定义固件开发

目标设备为 `xiaomi.controller.86v1`，目前只支持本机精确的 1.50.10 映像。
这是和原厂系统一起运行的持久化补丁程序；复用原来的 Wi-Fi、米家、GUI 调度及显示驱动。
源码与历史 `analysis/` 实验分开维护，历史三击逻辑和冻结材料不删除、不重新生成。
图片上传和下拉画面是当前自定义固件的功能。

当前已安装版为 `maintained-images-five-page-20261008-a`，主/辅助/网络/解码为
3368/396/4012/2916B，完整 ELF SHA-256 为
`3f67d12758931a05fc22e20ddd89c51688ea9ec12de185ededce821b0ead79d3`。
本轮已接入设备端 PNG/JPEG 解码，新增 NOR `0x927000` 页；模型、116 项 writer 与 freeze
完成，五页安装、完整页/native/cache/context、outer GLOBAL 和暖读回通过，fresh check
为 `patched=true`。471-input candidate SHA 为
`992b58c7aa72a162aca23756088ce8951467fa1d624ba8c7889a155ab430021b`，
477-input freeze SHA 为
`627a224c619b59a6813b47685e272cd19a4f8b25bb04af1bdbf690b31cf2a330`。

迁移前四页 `maintained-idle-return-four-page-20261007-a` 的新鲜检查匹配 patched 四页；
随后它自身恢复通过四页/native/context、outer GLOBAL 和暖读回，新五页检查为 original
后才安装。新能力 GET200 返回 png/jpeg/vimg，设置 GET60，通过直接 Node 的 PNG/JPEG
上传和完整 RGB565 读回，见 [本轮发布结果](releases/maintained-images-20261008-a.json)。
其 main/aux/net 3344/396/4072B、382 项 freeze、g 自身恢复、四页读回、
真实设置读写和一次 AON GLOBAL 暖复位加载保留在
[历史发布结果](releases/maintained-idle-return-20261007-a.json)，不用于证明五页版已安装。
此前 g 的安装和正式 HTTPS 页面用户上传结果保持在自己的历史记录中，不继承给 a。

## 交互

- 原界面顶边下拉打开自定义画面，自定义画面上滑返回原界面。
- 自定义画面连续两次短按，在最新上传图片和 IP:18086 地址页之间切换。
- 自定义固件没有第三物理键三击切换；原系统的物理按键动作继续由原系统处理。
- 观察到原系统息屏时，通过既有安全交接切回自定义画面，不调用背光接口。
  唤醒接触不参与双击，仍允许上滑返回原界面。
- 原界面未触摸 60 秒后自动返回；网页可配置 0–3600 整数秒，0 关闭。物理键不计入触摸。
  设置使用 MMC 双槽并按重启保留实现，息屏返回独立生效；详见 [自动返回](../docs/auto-return.md)。

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
$panelTestStamp = Get-Date -Format yyyyMMdd-HHmmss
python -X utf8 firmware/tests/test_ui_arm.py > "build/reviews/ui-arm-$panelTestStamp.json"
$env:PANEL_TEST_FRONTEND_URL = "https://wan.sh/xiaomi-86v1/"
$env:PANEL_TEST_FRONTEND_ORIGIN = "*"
$env:PANEL_TEST_OUTPUT = "build/reviews/http-arm-$panelTestStamp.json"
python -X utf8 firmware/tests/test_http_arm.py
$env:PANEL_SETTINGS_TEST_OUTPUT = "build/reviews/settings-arm-$panelTestStamp.json"
python -X utf8 firmware/tests/test_settings_arm.py
$env:PANEL_CODEC_RESULT_PATH = "build/reviews/codec-arm-$panelTestStamp.json"
python -X utf8 firmware/tests/test_image_codec_arm.py
Remove-Item Env:PANEL_TEST_FRONTEND_URL, Env:PANEL_TEST_FRONTEND_ORIGIN, Env:PANEL_TEST_OUTPUT, Env:PANEL_SETTINGS_TEST_OUTPUT, Env:PANEL_CODEC_RESULT_PATH
node --test firmware/tools/release.test.ts
```

这些模型需要本机精确 stock NOR 和本地公开/合成图片 fixture，不从其他设备或身份凑材料。
HTTP/codec 模型执行真实 ELF 和已核对 SHA 的原厂 PNG/JPEG 指令；OS、分配器、部分 libc、
锁与 GUI 边界仍由 mock 提供，不证明实际堆容量、RPC 延迟、LCD、并发或断电恢复。
仅加载 allocated PROGBITS sections，不用 PT_LOAD 地址空洞覆盖原厂解码器。
各轮输出写到独立 ignored 路径，避免覆盖冻结发布已绑定的结果。

构建默认前端 URL 为 `https://wan.sh/xiaomi-86v1/`，origin 为 `*`，沿用四页维护版的配置；
`GET /` 返回 303，将 endpoint 编码为普通 `device` query，前端自动读取。
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
本轮源码按内容签名直接接收 480×320 PNG/JPEG，使用独立解码状态和 inactive RGB565 槽；
不重初始化共享 GUI 图片缓存。图片格式自身的压缩已接入候选，HTTP Content-Encoding
只能省略或为 identity。PNG 8-bit/noninterlaced 和 JPEG baseline 的采样、尾部及元数据
范围见 API 文档。原厂解码器复用研究见 [图片压缩传输](../docs/research/image-compression.md)及
[直接 PNG/JPEG 上传](../docs/research/direct-image-upload.md)。
协议见 [HTTP 图片 API](../docs/http-image-api.md)。

图片接口允许省略或任意声明 Content-Type，完整 body 为 1..1048576B；VIMG 兼容入口仍
校验固定 307216B、头部和 FNV。网页只在用户点击发送时查询 GET `/api/image` 格式能力，
明确 404 才选择旧 VIMG；失败 POST 不自动换格式重发。图片 cURL 无需专用 header。
GET/POST `/api/settings` 沿用四页自动返回版，网页 POST 声明 JSON，
设备检查单成员、整数范围和完整持久化确认；其错误与保存语义见 [设置 API](../docs/auto-return.md#设置-api)。
本轮离线证据为 420 项 codec 实际 ARM、36 组 UI、34 组 HTTP、17 组设置，299 项 host
HTTP、29 项网页、12 项 release 与 116 项 writer mock 测试通过。
模型不能替代文件系统、GUI 或重启的实机验证。

## 安装与维护

构建输出、compiler headers、完整 NOR 页和 release 快照都保持 ignored，不提交 Git。
全新 clone 缺少精确原厂备份、历史 freeze 和工具链，不能直接用于刷写。

先完成 [离线发布流程](tools/README.md)、独立 storage/program/writer 审查、ARM 模型和
当前 116 项 writer mock，才创建不可覆盖的 freeze。执行器串行核对本轮全部 live 五页并拒绝混合
状态；失败留下 `NEEDS_INSPECTION`，不自动重复 native call、写入或复位。

```powershell
$panelRelease = 'maintained-images-five-page-20261008-a'
$panelExecutor = "build/releases/$panelRelease/snapshot/firmware/tools/hardware.ts"
node $panelExecutor check $panelRelease
node $panelExecutor install $panelRelease
node $panelExecutor restore $panelRelease
```

上述操作须使用该 release 冻结的执行器和验证器。canonical 工具后续改动时，从仓库根目录
运行 `build/releases/RELEASE/snapshot/firmware/tools/hardware.ts`，使用其相邻冻结验证器。
install/restore 都会中断服务并暖重启；精确范围及诊断命令损失见
[1.50.10 端口](ports/1.50.10/README.md)。恢复目标为精确的旧图片实验版（`native-image-drawer`）
三页加原厂网络/解码页，再使用该历史版本自己的回退器。不能直接对自定义固件使用旧三页 writer。
安装 codec→net→aux→code→entry，恢复 entry→code→aux→net→codec。新完整短根副本
`C:\p86-img-a` 已完成全部绑定字节 hash 核对、116 项 mock、freeze 与冻结 CLI verify。

安装基线中的“三页”是三个已安装旧图片实验程序的 4KiB Flash 区域，网络和解码区域仍
为原厂字节，五页都必须逐字节匹配；它不是屏幕界面页，也不是任意原厂设备的首刷起点。
install 只接受这个精确基线，不能叠加在旧自定义固件上。
四页自动返回版自身冻结执行器已完成恢复，新五页基线 check 为 original；随后由五页
新版本自身执行器安装，完整闭合和暖读回通过，fresh check 为 patched。两者结果分别
记录，不借用旧版 UI 或米家观察。新五页自身硬件 restore 尚未测试。
224B context 和 MMC 双槽
设置保留，NOR 安装/恢复不删除它们；完整断电仍按用户要求跳过。

直接 Node 上传2204B PNG及55134B JPEG均为202，完整RGB565匹配独立参考，
generation/displayed_generation依次1和2。坏PNG CRC返回422且保留JPEG与计数2；最后
恢复默认PNG为202、计数3，完整像素匹配。新鲜alive/ready1、pending0、server1/error0、
GUI cycles推进。MEM-AP读回不测量LCD扫描，Node请求不是用户浏览器验收，
耗时也不是性能基准；新版本交互、息屏、自动返回和米家仍待用户分别确认。

正式网页版本 `2ee45a5f-6b04-42ce-80bb-2e92e4dc4cc5` 已部署，五项静态资源一致、
零浏览器错误、初始零自动LAN请求。实际HTTPS页面Send在agent Chrome中完成能力GET200
和单次6050B PNG POST202，不添加Content-Type。最初权限prompt时GET等待且无POST；
agent随后通过origin-scoped CDP临时granted本地网络权限，不是用户点击许可。
此请求链路结果不等于用户浏览器、LCD或米家验收；完整像素与计数单独只读核验。

## 历史四页自动返回版检查点

上一轮先用 g 自身冻结执行器恢复精确基线，再由四页 a 自身冻结执行器安装，两次均通过；
旧结果未测四页 a 自身 restore；本轮五页迁移中的完整恢复成功另记新证据，不改旧结果。
真实 GET 默认 60 秒，POST/GET
0 和 5 秒一致，3601 返回 422 且保留运行值 0；保存 5 秒后独立暖复位，context 和 GET
重新加载为 5 秒，随后保存回 60 秒。直接 Node 图片 POST/202 不代表 LCD 或网页上传验收。
完整断电仍按用户要求跳过。a 的 context 为 224B，冻结 executor 的只读 capture 同步扩展；
旧 g 的 212B executor 和所有旧快照保持原样。

Windows/Jim 长路径首次 mock 为 77/93；完整材料逐项 hash 核对后置于 `C:\p86-idle-a`，
93/93 通过。实机入口使用这个短根目录的完整执行副本，不是单独搬动脚本或改写 freeze。
详见 [维护流程](../docs/development.md)。
