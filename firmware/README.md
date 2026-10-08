# 86V1 自定义固件开发

目标设备为 `xiaomi.controller.86v1`，目前只支持本机精确的 1.50.10 映像。
这是和原厂系统一起运行的持久化补丁程序；复用原来的 Wi-Fi、米家、GUI 调度及显示驱动。
源码与历史 `analysis/` 实验分开维护，历史三击逻辑和冻结材料不删除、不重新生成。
图片上传和下拉画面是当前自定义固件的功能。

本轮图片持久保存版为 `maintained-persistent-images-six-page-20261008-a`，candidate 和 freeze 已完成。
主/辅助/网络/解码/存储 BIN 为 **3368/396/3940/3012/1676B**，新增 NOR `0x932000` 页。
566 组实际 ARM、7 项 ABI、139 项当前候选 writer、12 项 release、299 项 host HTTP 和
30 项网页检查通过。五页版自身恢复、六页原始基线检查及六页安装、完整页/native/cache/context、
outer GLOBAL、暖读回和fresh patched检查通过；当前已安装六页图片持久保存版。
完整 ELF SHA 为 `f7e4d2bbeff500ac997e694846523ddc025f94d88d1bccf7306419233ae6fcd3`；
522-input candidate SHA 为 `e061db87d2e4e4aa1e2836a89fa1dd1f47215826914b5b492b59b9bce7388591`，
528-input freeze SHA 为 `9a3f4d7e39a1451d7bef16672415d4183f516234a3741d986d3c721b6d39a801`。
本轮安装、保存与暖重载记录在[六页发布结果](releases/maintained-persistent-images-20261008-a.json)。
[五页发布结果](releases/maintained-images-20261008-a.json)和
[四页自动返回版结果](releases/maintained-idle-return-20261007-a.json)独立保留，不用于证明本轮功能。

## 交互

- 原界面顶边下拉打开自定义画面，自定义画面上滑返回原界面。
- 自定义画面连续两次短按，在最新上传图片和 IP:18086 地址页之间切换。
- 自定义固件没有第三物理键三击切换；原系统的物理按键动作继续由原系统处理。
- 观察到原系统息屏时，通过既有安全交接切回自定义画面，不调用背光接口。
  唤醒接触不参与双击，仍允许上滑返回原界面。
- 原界面未触摸 60 秒后自动返回；网页可配置 0–3600 整数秒，0 关闭。物理键不计入触摸。
  设置使用 MMC 双槽并按重启保留实现，息屏返回独立生效；详见 [自动返回](../docs/auto-return.md)。

六页源码把完整原编码图片保存在 MMC 双槽，启动在 GUI ready 后验证、解码并恢复；
无可恢复记录时保持默认地址画面。双击切换不丢弃图片，地址页也可接收新图。
息屏检测依赖 GUI timer 能观察到原厂状态；两次采样之间发生的
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
$env:PANEL_IMAGE_STORE_RESULT_PATH = "build/reviews/image-store-arm-$panelTestStamp.json"
python -X utf8 firmware/tests/test_image_store_arm.py
Remove-Item Env:PANEL_TEST_FRONTEND_URL, Env:PANEL_TEST_FRONTEND_ORIGIN, Env:PANEL_TEST_OUTPUT, Env:PANEL_SETTINGS_TEST_OUTPUT, Env:PANEL_CODEC_RESULT_PATH, Env:PANEL_IMAGE_STORE_RESULT_PATH
node --test firmware/tools/release.test.ts
```

这些模型需要本机精确 stock NOR 和本地公开/合成图片 fixture，不从其他设备或身份凑材料。
HTTP/codec 模型执行真实 ELF 和已核对 SHA 的原厂 PNG/JPEG 指令；OS、分配器、部分 libc、
锁与 GUI 边界仍由 mock 提供；存储模型替换文件/FAT I/O 边界，不证明实际堆容量、RPC 延迟、LCD、并发或真实文件系统断电恢复。
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
不重初始化共享 GUI 图片缓存。图片格式自身的压缩已接入当前版本，HTTP Content-Encoding
只能省略或为 identity。PNG 8-bit/noninterlaced 和 JPEG baseline 的采样、尾部及元数据
范围见 API 文档。原厂解码器复用研究见 [图片压缩传输](../docs/research/image-compression.md)及
[直接 PNG/JPEG 上传](../docs/research/direct-image-upload.md)。
协议见 [HTTP 图片 API](../docs/http-image-api.md)。

图片接口允许省略或任意声明 Content-Type，完整 body 为 1..1048576B；VIMG 兼容入口仍
校验固定 307216B、头部和 FNV。网页只在用户点击发送时查询 GET `/api/image` 格式能力，
明确 404 才选择旧 VIMG；失败 POST 不自动换格式重发。六页能力另有 `persistent: true`。
图片 cURL 无需专用 header。
GET/POST `/api/settings` 沿用四页自动返回版，网页 POST 声明 JSON，
设备检查单成员、整数范围和完整持久化确认；其错误与保存语义见 [设置 API](../docs/auto-return.md#设置-api)。
本轮已完成 448 项 codec/VIMG、36 组 UI、42 组 HTTP、17 组设置、23 组图片存储，共
566 组实际 ARM；另有 7 项 ABI、139 项当前候选 writer、12 项 release、299 项 host HTTP
和 30 项网页检查通过，不继承旧五页计数。
模型不能替代文件系统、GUI 或重启的实机验证。

## 图片持久保存

仅使用 `/data/86v1-image.0` 和 `.1`，不改原厂或设置文件。每槽为 20B little-endian
`VPI1` header（magic/sequence/length/body FNV/header FNV），后接 1..1048576B 的完整
原 PNG/JPEG/VIMG 文件。16B sequence/length/hash/valid 状态属于网络 worker，broker 保持224B。
启动检查完整 header、body hash 和 EOF，实际解码失败的新槽可回退旧图；全部失败保持默认图。

保存完整预检两槽，已知可恢复记录必须仍匹配，然后只写另一槽；hash有效但无法解码的
较新记录不会挤掉实际恢复的旧图。完整短读写、fsync、close 和独立逐字节读回成功后，
才更新 worker 状态并排队给 GUI，HTTP202表示保存确认及排队，不表示 LCD 扫描完成。
确认后的发布锁、owner 或网络响应仍可能失败，非202或无响应不保证文件未改变，不自动重试。
foreign文件409，I/O/资源/确认失败503；不足4B的现有文件按foreign保护。
双槽中断测试只验证应用策略，不能宣称真实 FAT/MMC/RPMsgFS 掉电耐久性。
NOR备份及安装/恢复不包含、不删除图片和设置文件；回到旧固件也保留这些项目文件。

本轮真实VIMG/PNG/JPEG保存均POST202，完整RGB565匹配参考，坏PNG422保留JPEG。
JPEG及浏览器保存的默认PNG分别经过独立AON GLOBAL暖复位后自动重载，均未执行OS
shutdown hooks；新context计数1/pending0/server1/error0、完整RGB565匹配。
这是暖重载证据，不是断电恢复或LCD扫描测量。

正式网页版本`6d2572cb-61e0-40b1-b28f-837e32d53157`的HTML/favicon/JS/CSS四项字节精确、
200，Chrome零错误和初始零自动LAN请求。agent Chrome显式Send完成GET200及单次6050B
PNG POST202，无Content-Type，按钮“画面已保存”，完整RGB565读回匹配；本地网络许可
由origin-scoped CDP临时授予，结束后恢复prompt，不是用户点击许可。用户对默认GitHub
图片、上下滑、双击及米家状态的合并问题回复“确认正常”，记录为合并观察，不分别测量。

## 安装与维护

构建输出、compiler headers、完整 NOR 页和 release 快照都保持 ignored，不提交 Git。
全新 clone 缺少精确原厂备份、历史 freeze 和工具链，不能直接用于刷写。

先完成 [离线发布流程](tools/README.md)、独立 storage/program/writer 审查、ARM 模型和
当前 139 项 writer mock，才创建不可覆盖的 freeze。执行器串行核对本轮全部 live 六页并拒绝混合
状态；失败留下 `NEEDS_INSPECTION`，不自动重复 native call、写入或复位。

```powershell
$panelRelease = 'maintained-persistent-images-six-page-20261008-a'
$panelExecutor = "build/releases/$panelRelease/snapshot/firmware/tools/hardware.ts"
node $panelExecutor check $panelRelease
node $panelExecutor install $panelRelease
node $panelExecutor restore $panelRelease
```

本轮已安装；上例仍要求硬件前状态审查，不是连续执行的安装/恢复批处理。
上述操作须使用该 release 冻结的执行器和验证器。canonical 工具只接受 schema4 六页，旧
五页或四页版须使用自身冻结的 release/hardware 工具。从仓库根目录
运行 `build/releases/RELEASE/snapshot/firmware/tools/hardware.ts`，使用其相邻冻结验证器。
install/restore 都会中断服务并暖重启；精确范围及诊断命令损失见
[当前架构](../docs/architecture.md)。恢复目标为精确的旧图片实验版（`native-image-drawer`）
三页加原厂网络/解码/存储页，再使用该历史版本自己的回退器。不能直接对自定义固件使用旧三页 writer。
安装 store→codec→net→aux→code→entry，恢复 entry→code→aux→net→codec→store。
存储代码仅借用可选 `monkey` 诊断的 `0x38052000..0x38052bf0`，并禁用入口页 `+0xe6c`；
原页前4B/后1036B及容器外字节保留，正常启动与恢复使用的 `mkgpt` 不借用。

安装基线中的“三页”是三个已安装旧图片实验程序的 4KiB Flash 区域，网络和解码区域仍
为原厂字节，存储区域同样为原厂字节，六页都必须逐字节匹配；它不是屏幕界面页，也不是任意原厂设备的首刷起点。
install 只接受这个精确基线，不能叠加在旧自定义固件上。
六页安装前先用已安装五页版自身冻结执行器完整恢复，再由六页工具核对精确基线；
本轮迁移已由五页版自身工具恢复、六页original检查后安装，完整闭合及暖读回通过，
fresh check为patched=true。六页自身硬件恢复未测试。224B context、MMC图片和设置文件
分开管理；完整断电仍按用户要求跳过，真实FAT/MMC掉电耐久性未证明。

## 历史五页安装和上传检查点

五页版 main/aux/net/codec 为3368/396/4012/2916B，ELF SHA为
`3f67d12758931a05fc22e20ddd89c51688ea9ec12de185ededce821b0ead79d3`；
471-input candidate SHA为`992b58c7aa72a162aca23756088ce8951467fa1d624ba8c7889a155ab430021b`，
477-input freeze SHA为`627a224c619b59a6813b47685e272cd19a4f8b25bb04af1bdbf690b31cf2a330`。
当时420项codec、36组UI、34组HTTP、17组设置、299项host HTTP、29项网页、12项release
与116项writer mock通过。完整短根副本`C:\p86-img-a`的字节核对、mock及冻结verify通过，
仅供该五页release自身使用。
四页自动返回版自身冻结执行器已完成恢复，新五页基线 check 为 original；随后由五页
新版本自身执行器安装，完整闭合和暖读回通过，fresh check 为 patched。两者结果分别
记录，不借用旧版 UI 或米家观察。该原始检查点尚未测试五页自身硬件 restore。
224B context 和 MMC 双槽
设置保留，NOR 安装/恢复不删除它们；完整断电仍按用户要求跳过。

直接 Node 上传2204B PNG及55134B JPEG均为202，完整RGB565匹配独立参考，
generation/displayed_generation依次1和2。坏PNG CRC返回422且保留JPEG与计数2；最后
恢复默认PNG为202、计数3，完整像素匹配。新鲜alive/ready1、pending0、server1/error0、
GUI cycles推进。MEM-AP读回不测量LCD扫描，Node请求不是用户浏览器验收，
耗时也不是性能基准；新版本交互、息屏、自动返回和米家仍待用户分别确认。

正式网页版本 `2ee45a5f-6b04-42ce-80bb-2e92e4dc4cc5` 已部署，五项静态资源一致、
零浏览器错误、初始零自动 LAN 请求。实际 HTTPS 页面 Send 在 agent Chrome 中完成能力
GET200 和单次 6050B PNG POST202，不添加 Content-Type。最初权限 prompt 时 GET 等待
且无 POST；agent 随后通过 origin-scoped CDP 临时授予本地网络权限，不是用户点击许可，
结束后权限恢复为 prompt。上传后只读 MEM-AP 核验完整 307200B RGB565 与默认图参考
一致，槽位和计数稳定，generation/displayed_generation=4、pending0、alive/ready1、
server1/error0，GUI cycles 推进。这些结果不等于用户浏览器、LCD 或米家验收。

该五页版自身硬件restore后来在本轮六页迁移中通过完整五页/native/cache/context、
outer GLOBAL和暖读回，另记六页发布结果。以上保留五页原始检查点，不修改历史result。

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
