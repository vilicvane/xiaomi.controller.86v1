# 研究及历史版本索引

本页把保存的研究证据按问题和版本连接起来。当前已安装维护版为
**maintained-images-five-page-20261008-a**，五页完整读回、native 闭包、GLOBAL、暖启动
和新鲜 patched 检查通过。实机 Node PNG/JPEG 上传返回 202，RGB565 与参考一致；
坏 CRC 返回 422 且不替换原图。Node 阶段最后恢复的默认 PNG 已被 GUI 消费，generation 3。
网页改版已部署为 `2ee45a5f-6b04-42ce-80bb-2e92e4dc4cc5`，五项文件与构建精确一致，
Chrome 启动无错误、无自动 LAN 请求；官方 HTTPS 页面的单次 PNG 上传返回 202。
本轮 LCD、手势和米家用户观察仍待验收，自身恢复未实机测试，完整断电由用户跳过。
每个历史 result 的 `installed` 表示当轮曾安装，不表示现在仍运行那个版本。
当前验证见 [架构](architecture.md)，操作入口见 [开发流程](development.md)。
维护版安装与协议结果见 [当前发布结果](../firmware/releases/maintained-images-20261008-a.json)。

## 早期问题与已得到的结论

| 研究问题 | 结论与证据 |
| --- | --- |
| 配网失败是否为 Wi-Fi 残留 | 历史 1.48.5 已完成关联/IP，失败在云登录；RAM 身份缓存异常，限定身份验证后恢复，见 [恢复记录](../analysis/recovery-summary.md) |
| BES 引脚连到哪些设备 | [针脚映射](../analysis/pinout/panel-pinmap-1.50.10.json)与 [触摸输入路由](../analysis/pinout/a7-touch-input-route-1.50.10.json)，物理连线待确认项单列 |
| 能否只写显示寄存器接管 | LCDC/DSI 测试未见变化；实际像素源提交成功，后续 [native counter](../analysis/display-takeover/native-counter.md)证明设备端显示和触摸 |
| 原界面能否退出后反复重启 | 生命周期有悬挂与重复初始化边界，见 [生命周期审查](../analysis/display-takeover/vapp-lifecycle-switch-review-1.50.10.json)；采用只启动一次的 owner broker |
| 原显示与触摸如何交接 | [所有权审查](../analysis/display-takeover/ui-switch-ownership-review-1.50.10.json)与 [broker](../analysis/display-takeover/native-ui-broker.md)，两显示提交及两输入路径须共同处理 |
| Flash 的空白是否可直接使用 | [容量统计](../analysis/flash-capacity-summary-1.50.10.json)只是内容模式；加载长度、BSS、OTA 与保留范围约束另见 [工程约束](engineering-notes.md) |
| 原厂字体可否复用 | [字体可行性](../analysis/image-push/font-resource-feasibility-1.50.10.json)仅静态分析，未做实机字体/glyph API 调用 |
| 图片压缩传输如何接入 | [图片压缩研究](research/image-compression.md)比较无损 DEFLATE 与 RLE；[直接 PNG/JPEG 上传](research/direct-image-upload.md)已接入当前 images 版本，实机 Node PNG/JPEG 与 RGB565 读回通过，官方 HTTPS 单次 PNG 上传也返回 202；LCD 用户观察仍待验收 |

### 配网诊断的保留结论

其他 SSID 可以只是扫描记录，不能据此认定残留配置。1.48.5 的 `device.info` 创建失败
路径未继续读取出厂身份，却返回成功，RAM 保留编译预置值；底层文件失败原因未确认。
只修改 DID/key 各 32B RAM，每轮保存原值并读回，未清空 NOR。首次授权失败可能与 BLE
身份不同有关，仍是未证实假设。后续原程序自行加载真实身份，完全断电后云连接/控制
正常；这个历史验证不能替代后续每版 UI 的米家或冷启动结果。

## 原生 UI 演进

每一行对应独立源码、manifest、freeze、模型及硬件结果，集合保留原路径与字节。
“完整断电”只记录该版自己的证据，不继承前版结果。代码 byte 数来自保存的 manifest/result。

| 版本 | 代码规模 | 该轮进展及边界 | 完整断电 |
| --- | --- | --- | --- |
| [native counter](../analysis/display-takeover/native-counter.md) | 白色 966B | 常驻 A7 计数，替换旧 UI 入口；暖启动白色与粉色冷启动分开 | 粉色通过；白色独立观察未补做 |
| [broker v1](../analysis/display-takeover/native-ui-broker.md) | 2652B | 原 UI 只进入一次，第三键三击交接显示/触摸；往返及米家控制通过 | 通过 |
| [first drawer](../analysis/display-takeover/native-drawer.md) | 3224B | 顶边下拉、上滑、短拉回弹；用户功能通过但希望更自然 | 当轮 pending |
| [ease](../analysis/display-takeover/native-drawer-ease.md) | 3264B | 松手剩余行程 cubic ease-out；用户/米家通过，上滑仍偏突然 | 通过 |
| [smooth](../analysis/display-takeover/native-drawer-smooth.md) | 3368B | 新提交位置作锚、每帧进度限制；用户手感通过 | 用户跳过 |
| [GitHub card](../analysis/display-takeover/native-github-card.md) | 3432B | GitHub logo、用户名、项目名及 Star 提示；排版/手势通过 | 用户跳过 |
| [GitHub tap v1](../analysis/display-takeover/native-github-tap.md) | 主 3392B + aux 291B | 松手累加及自动恢复；用户报告间歇慢/漏点，原因未证实 | 用户跳过 |
| [GitHub tap-fast](../analysis/display-takeover/native-github-tap-fast.md) | 主 3336B + aux 431B | PAN 后计时与局部软件绘图；用户决定 Demo 不再改，不能说实际卡顿已解决 | 用户跳过 |
| [image drawer](../analysis/image-push/native-image-drawer.md) | 主 3416B + aux 424B | 旧三页 TCP 原型，接图/IP显示；两图、手势及米家控制通过，图片 RAM-only | 用户跳过 |
| [maintained HTTP c](../firmware/releases/maintained-http-20261007.json) | 主 2946B + aux 236B + net 3004B | 独立四页 HTTP；双击/息屏用户通过，本轮迁移的 c 精确恢复另记在 d 结果 | 用户跳过 |
| [maintained HTTP d](../firmware/releases/maintained-http-20261007-d.json) | 主 2946B + aux 236B + net 2948B | 配置 LAN 前端 303、忽略 Content-Type；真实网页/cURL 上传、默认图/手机跳转通过，其余交互和米家待验收 | 用户跳过 |
| [maintained HTTP g](../firmware/releases/maintained-http-20261007-g.json) | 主 2946B + aux 236B + net 2976B | 主/aux 与 d 相同；303 指向正式 HTTPS 网页，以普通 query 传递地址；用户报告上传正常，fresh runtime 消费 generation=1，未自动采集 POST 或确认 LCD/米家 | 用户跳过 |
| [maintained idle return a](../firmware/releases/maintained-idle-return-20261007-a.json) | 主 3344B + aux 396B + net 4072B | 触摸空闲返回、MMC 双槽持久化设置；g 恢复及 a 安装闭包通过，设置读写及暖复位重载通过，网页及交互用户观察待验收 | 用户跳过 |
| [maintained images a](../firmware/releases/maintained-images-20261008-a.json) | 主 3368B + aux 396B + net 4012B + codec 2916B | 五页安装/暖启动、Node PNG/JPEG 及像素读回通过；官方 HTTPS PNG POST/202，LCD/米家待验收 | 用户跳过 |

tap-fast 减少软件画布写量 93.45%，原 PAN 仍整帧处理，触摸 ring 仍为 8 个样本。
离线故意丢 UP 可复现合并点击/移动等行为，但实际间歇问题没有证据归因为 ring 溢出；
两轮非原子采样没记录到 count 变化，也不构成实机延迟证明。

ease 旧动画首帧跳跃的只读采样中，第一次计算的 shown 从 233/220 跳至 114/91，起点
已过 25/30ms；不能写成已证明整段 120ms 在首帧前耗尽。smooth 修正了时间锚和逻辑
推进，不改写已经冻结的 ease 证据。所有历史三击逻辑均保留；只有 `firmware/` 维护版
移除自有三击入口，原系统按键动作继续由原系统处理。

### 实机结果与冻结入口

结果都在 `analysis/persistence/`，每版 `<variant>-hardware-result.json` 单列离线、安装、
暖启动和用户观察，`<variant>-frozen-inputs.json` 绑定精确输入。常用入口如下：

- [counter 结果](../analysis/persistence/native-counter-hardware-result.json)
- [broker 结果](../analysis/persistence/native-ui-broker-hardware-result.json)
- [first drawer 结果](../analysis/persistence/native-drawer-hardware-result.json)
- [ease 结果](../analysis/persistence/native-drawer-ease-hardware-result.json)
- [smooth 结果](../analysis/persistence/native-drawer-smooth-hardware-result.json)
- [card 结果](../analysis/persistence/native-github-card-hardware-result.json)
- [tap v1 结果](../analysis/persistence/native-github-tap-hardware-result.json)
- [tap-fast 结果](../analysis/persistence/native-github-tap-fast-hardware-result.json)
- [image drawer 结果](../analysis/persistence/native-image-drawer-hardware-result.json)与
  [93 项 freeze](../analysis/persistence/native-image-drawer-frozen-inputs.json)

历史三击样本、源码和结论不能因下一版取消入口而删掉；它们也是精确回退的一部分。

### 当前维护版证据

`maintained-images-five-page-20261008-a` 使用完整 PNG/JPEG 文件头识别，最大 1MiB，
尺寸固定 480×320。PNG 接受 8-bit 非交错静态图；JPEG 接受灰度及 RGB/YCbCr 三分量的
baseline 单扫描 4:4:4、4:2:2、4:2:0。额外 PNG 元数据与文件完整性限制见
[HTTP 图片 API](http-image-api.md)。接收图像仍为 RAM-only，不把图片压缩当作固件压缩或持久化。

完整 ELF 已离线执行 420 个实际 ARM 解码案例：20 张参考图逐像素一致，36 组格式和
完整性检查，182 次单次分配故障及 182 次持续内存不足。所有案例完成清理和边界检查；
JPEG 能恢复的单次内存池分配失败也验证了输出。PNG 不再使用早期 height=0 实验绕过；
JPEG 固定内部初始化 ABI 的范围及约束单列于 [直接 PNG/JPEG 研究](research/direct-image-upload.md)。

同版本通过 36 组 UI、34 组 HTTP、17 组设置模型，网页通过 29 项测试。Chrome 实际 sRGB
Canvas PNG 已在离线 native HTTP/GUI 像素路径中验证一致；该检查没有请求真实设备。

[images 发布结果](../firmware/releases/maintained-images-20261008-a.json)绑定 candidate SHA
`992b58c7aa72a162aca23756088ce8951467fa1d624ba8c7889a155ab430021b` 和 477 项 freeze SHA
`627a224c619b59a6813b47685e272cd19a4f8b25bb04af1bdbf690b31cf2a330`。
先用 idle-return a 自身冻结执行器恢复精确原始四页，再安装 images 五页；两阶段完整读回、
native/cache/context 闭包、GLOBAL 和暖启动通过，images 新鲜只读检查为 patched。
2204B 默认 PNG、55134B JPEG 的 Node POST 均返回 202；RGB565 读回与参考一致，分别消费
generation 1/2。坏 CRC PNG 返回 422 并保留 generation 2 和原图；最后默认 PNG 返回 202，
generation/displayed_generation 3、pending 0、GUI 持续运行。没有 LCD 或性能测量。
已有 MMC 设置在本轮加载为 60 秒，仅 GET 确认，未保存设置；不继承旧版保存/重启验收。

网页已部署为 `2ee45a5f-6b04-42ce-80bb-2e92e4dc4cc5`。五项线上文件返回 200 且与构建一致，
Chrome 启动页面/控制台错误为 0、初始 LAN 请求为 0。独立点击官方 HTTPS 页面的发送按钮后，
能力 GET 返回 200，单次 6050B PNG POST 返回 202，无 Content-Type，按钮显示“画面已接收”。
初始本地网络权限提示时 GET 等待而未发送 POST；测试通过 CDP 临时授予该 origin 权限，
不是用户点击许可，不代表所有浏览器支持。该请求结果不代替 LCD 或独立 GUI 像素读回。
随后完整 307200B RGB565 只读核验与默认画面一致，slot/generation 稳定，generation/displayed_generation
均为 4、pending 0、alive/ready/server 1、error 0，GUI 持续运行；没有 LCD scanout 验证。
临时 Chrome origin 权限已恢复为 prompt 并查询确认。
images 自身恢复未实机测试，完整断电由用户跳过；LCD、手势、双击、定时返回、
网页设置和米家用户观察仍待验收，不继承以下 a/g 的历史结果。

### 历史 idle-return a 检查点

以下保留 idle-return a 发布当时的记录。它的自身恢复后来在 images 迁移中通过，
新增证据在 images result，不改写旧 result 或冻结输入。

当轮为 [maintained-idle-return-four-page-20261007-a](../firmware/releases/maintained-idle-return-20261007-a.json)：
candidate SHA `6022cbd3e41cfc913a260ff17855582c47656318227dfb6defc55230be503f55`，
382 项 freeze SHA `660534d525762b83b8029b3adebd82a20d84723d5706e53afc6f6790a5c64cb4`。
76 组实际 ARM、93 项 writer mock、290 项 host HTTP、12 项 release 及 19 项 web 测试通过。
先用 g 自身冻结执行器恢复精确基线，再使用完整 byte-matching 短路径 a bundle 安装，
四页/native 闭包及暖启动读回通过。a 自身实机恢复尚未测试。

设置 GET/POST 和一次无 OS shutdown hook 的 AON GLOBAL 暖复位重载已验证；
设置最终保存回 60 秒。图片直接 Node POST 返回 202，fresh runtime 消费 generation=1；
不冒充用户 LCD、浏览器上传或米家控制观察。完整断电仍为用户跳过，其他用户验收见当前 result。
该 idle-return a 的图片接口是 VIMG；当前 images 已独立安装并验证 PNG/JPEG Node 上传与像素读回。
通用 VIMG/DEFLATE 研究保留为独立路线，没有因 PNG 的内部 DEFLATE 解码而新增上传格式。

### 历史 g 检查点

以下保留 g 发布当时的记录。g 自身恢复后来在 a 迁移中通过，证据在 a result，
不改写 g 的历史 result 或冻结输入。

当轮 86V1 自定义固件 release 为 [maintained-http-four-page-20261007-g](../firmware/releases/maintained-http-20261007-g.json)：
candidate SHA `dbd66152502676875df1e2eddd97a02b00a0a14c547d7f6fee11e49f23994a8f`，
380 项 freeze SHA `4c523fdc97fee23173f05c2fa3883c48a1368f1865f01b4ef646c16b24583b38`。
主/aux 与 d 保持相同字节，网络段为 2976B。新一轮 21 组实际 ARM UI 与 23 组已配置
HTTP 模型（共 44 组）、93 项四页 writer mock、261 项 host parser、12 项 release 测试
和 9 项前端测试通过；这些离线结果不代替设备验证。

升级先用 d 自己的冻结执行器恢复其精确原始四页，再用 g 自己的执行器安装；两阶段
完整四页读回、native/cache/context 闭包、GLOBAL 和暖启动读回通过。新只读检查确认
g 的 patched 页匹配。g 自己的硬件恢复仍未测试，完整断电测试由用户明确跳过。

真实 `GET /` 返回 303 到 `https://wan.sh/xiaomi-86v1/`，设备 endpoint 通过普通
`device` query 传递；Chrome 跟随后填写地址且无页面错误，不再依赖电脑开发服务器。
自动浏览器验证停在本地网络授权提示，没有发送 POST。用户报告“可以，上传正常”后，
fresh runtime 的 generation/displayed_generation 均为 1、pending/error 为 0，
alive/ready/mode/server 为 1，GUI cycles 继续增长。这证明 GUI 消费了新 generation，
不冒充抓取的 HTTP 202、FNV 读回或 LCD 扫描结果。默认图、双击、手势、息屏唤醒、
三击入口取消及米家控制仍未分别确认，不借用 d/c 的历史观察。

第一方源码入口见 [firmware](../firmware/README.md)，协议见 [HTTP 图片 API](http-image-api.md)，
安装与恢复步骤见 [开发流程](development.md)。[图片压缩研究](research/image-compression.md)
是后续研究入口；当轮 g 接收未压缩 VIMG，图片只保存在 RAM。

### 历史 d 检查点

以下保留 d 发布当时的完整记录，其中“当前”和“未执行”描述该轮检查点。
d 自己的恢复后来在 g 升级中通过，新增证据记录在 g 结果，不改写 d 的历史 result 或冻结输入。

第一方维护源码、模型和发布工具位于 [firmware](../firmware/README.md)，网络格式见
[HTTP 图片 API](http-image-api.md)，独立快照与五类证据绑定见
[离线发布流程](../firmware/tools/README.md)。current release 为
`maintained-http-four-page-20261007-d`：candidate SHA
`aba4a3e5021af175a3d6cd9dc90eac4559154d34711b647bbc8a48043ce5d9fe`，380 项 freeze SHA
`3af60edcb71636fbe227237f7c7f8b23d4135571b2e45651583665d4466a2632`。

12 项 release 测试、93 项独立四页 writer mock、261 项 host parser、24 组实际 ARM UI
和 23 组已配置 URL 的实际 ARM HTTP 模型通过。先用 c 自己的冻结执行器恢复 exact
image drawer 三页加 stock 网络页，再安装 d；两阶段四页/native 闭包和暖启动读回通过。
d 的 GET/303 Location、Chrome 自动填写地址、无 Content-Type 的网页 POST/202、
cURL 无 `-H` POST/202、无 type 坏 FNV/422、任意 type 坏 VIMG/400 已实测。
两次完整图片被 GUI 消费，generation/displayed_generation=2、pending=0、server=1；
用户另行确认默认卡片可见和手机 LAN 跳转打开网页。双击、手势、三击取消、息屏及米家
仍待用户验收；c 的双击/息屏确认不作为 d 的结论，d 硬件恢复也未执行。

完整原厂备份、四页字节、工具链、compiler headers、BIN/ELF、生成数组与整个 release
只在 ignored 私有目录保存，公共材料仅保存必要的语义结果和 hash。当前 URL 指向临时
`http://PC_LAN_IPV4:5173/`，电脑/开发服务器是依赖；真实地址不入库。没有 Cloudflare
部署、手机上传或 HTTPS 到 LAN 的验证结果。具体恢复命令见 [开发流程](development.md)。
旧 c 的 [结果](../firmware/releases/maintained-http-20261007.json)和全部冻结输入原样保留。

## NOR 执行器研究

| 文档 | 内容 |
| --- | --- |
| [NOR 编程审查](../analysis/persistence/nor-programming-review.md) | 控制器、保护状态及写入条件 |
| [BOOT 独立初始化闭包](../analysis/persistence/boot-independent-init-nor-closure.md) | 与应用上下文隔离的恢复范围 |
| [BOOT 读取 runner](../analysis/persistence/boot-nor-read-runner.md) | 只读调用与状态闭合 |
| [BOOT hook runner](../analysis/persistence/boot-nor-hook-runner.md) | 停点和受控调用路线 |
| [固定原生应用 writer](../analysis/persistence/boot-nor-native-app-runner.md) | 固定扇区写入及 safe-to-resume gate |
| [padding 测试计划](../analysis/persistence/boot-nor-padding-test-plan.md) | 当轮监督下的写入边界研究 |

这些研究不授权照抄其中旧命令到当前六页、历史五页/四页或其他版本的三页集合。`0x40140000` 访问曾锁总线，当前逻辑
controller 0 为 `0x40148000` 且要先验证 live pointer table。任何不确定 native 调用后
保留停止状态，不能回放旧 CPU/SRAM 或自动推进。逐级恢复表见 [开发流程](development.md)。

## 原始记录归档

- [整理前工程原文](research/engineering-log-through-image-drawer.md)：逐轮发现、失败和修正完整保留。
- [整理前开发原文](research/legacy-development-log.md)：工具、旧版本命令及冻结流程完整保留。

归档正文里的“当前”指对应实验轮次。维护时先看现阶段入口，再用这些原文追溯具体
结论；不从历史段落推断现在的安装版本或未经记录的新功能。
