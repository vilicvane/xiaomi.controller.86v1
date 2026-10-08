# 86V1 自定义固件架构

本页描述 **86V1 自定义固件**的当前五页版 `maintained-images-five-page-20261008-a`，
适用于本机精确的 1.50.10 映像。图片上传、下拉画面和可保存的自动返回设置是当前功能。
本轮新增 PNG/JPEG 原生解码，模型、116 项 writer 与 freeze 已完成；五页实机安装及
完整页/native/cache/context、outer GLOBAL 和暖读回通过，随后 fresh check 为 patched。
迁移前四页自动返回版检查匹配 patched；随后其自身恢复通过四页/native/context、
outer GLOBAL 和暖读回，新五页检查为 `original=true` 后才安装。原四页版安装、设置和暖复位
结果作为历史检查点保留，不继承给新版本。
源码入口见 [firmware](../firmware/README.md)，精确材料位于 ignored 的 release 快照。
[本轮发布结果](../firmware/releases/maintained-images-20261008-a.json)分别记录安装、直接HTTP、
完整RGB565读回及尚未验收的LCD、用户浏览器和米家项目。
[历史四页自动返回版结果](../firmware/releases/maintained-idle-return-20261007-a.json)单列离线、硬件及用户观察。
[此前 g 的结果](../firmware/releases/maintained-http-20261007-g.json)、
[此前 d 的结果](../firmware/releases/maintained-http-20261007-d.json)、
[此前 c 的结果](../firmware/releases/maintained-http-20261007.json)及冻结材料独立保留。
旧图片实验版（`native-image-drawer`）的三页 TCP 原型另有 [manifest](../analysis/persistence/native-image-drawer-patch-inputs-1.50.10.json)
和 [硬件结果](../analysis/persistence/native-image-drawer-hardware-result.json)。

## 程序与原系统的关系

补丁包装原 `vapp` 的启动入口，分配自己的画布和上下文，安装 GUI callback 代理，
再进入原应用一次。原 NuttX、板级初始化、显示/触摸驱动、App/JS 线程与 MCU 服务继续
运行；隐藏原界面不退出或重新初始化原 Framework。它是持久化设备端程序，尚不是
独立构建的完整固件，也没有找到通用的官方 UI 插件 API。

```mermaid
flowchart LR
    Client[上传器或图片编辑网页] -->|HTTP PNG / JPEG / VIMG body| Worker[A7 网络 worker]
    Worker -->|独立请求状态解码| Codec[原厂 PNG / JPEG 解码器]
    Codec -->|RGB565| Slots[两个 RGB565 RAM 槽]
    Worker -->|校验后发布| Slots
    Slots -->|GUI 安全边界交换| GUI[原 GUI 线程中的自定义显示代理]
    Original[原米家 UI 和 JS] --> GUI
    Touch[物理和虚拟触摸] --> GUI
    GUI -->|合成 RGB32 / PAN| Screen[显示驱动和屏幕]
    Worker <-->|usrsock / RPMsg| MCU[原 MCU 网络服务]
    Worker <-->|设置读写| Settings[MMC 两个自动返回设置槽]
```

bootstrap pthread 使原 GUI 所属 timer 完成代理安装，等待 ready 后继续运行网络 server。
本轮创建线程时显式传递 16B 默认调度属性和 16384B 栈，容纳原生解码调用；
模型中的栈观测及边界守护不等于实机调度或所有输入的栈上界证明。
稳态触摸、手势和绘图在原 GUI 线程执行；这个独立网络 worker 不在 GUI callback
内等 socket。早期纯界面实验的 bootstrap 安装后退出属于历史版本，不能套用于当前程序。
系统 `panel_apps` 仍负责背光和息屏。自定义固件观察系统状态来准备自定义 owner，
没有新建锁屏 App 或重初始化原系统的 GUI/字体服务。

## 当前交互与所有权

开机默认展开地址画面。上传后展示图片；连续两次短按可切换最新图片和 IP:18086，
切换不丢弃 RAM 图片。地址页接收新上传时仍保留地址页。上滑收起，原界面顶边起手
下拉展开，短拉后松手回弹。双击只接受物理短按的完整接触序列，拖动、动画中接触、
虚拟输入和唤醒接触不参与计数；一次双击消费一对轻触。

自定义固件取消了自己的第三键三击检测，原 MCU 按键动作继续由原系统处理。历史第三键
P3_1、bit25、低电平采样及三击版本完整保留，不能因当前版本移除入口而改写旧实验。

原界面在后台继续绘图，自定义 owner 时阻止其 PAN 和 UPDATEAREA 提交。两路原输入
继续消费样本，但隐藏原界面得到 release；顶边手势从第一 DOWN 开始截取整个接触，
动画中新接触一直消费到松手。已经按下的虚拟输入阻止新的顶边截取。

owner 交接由 GUI callback 内的事务完成：释放输入、等待旧显示队列排空、锁两个
touch publisher、核对 ring 和真实释放状态、提交新源，最后更新 owner。原界面恢复
使用持久 mmap `0x50000000`，自定义使用 owned RGB32。画布在回调/帧队列存续期间
保持有效，不通过重复启动原应用切换。

动画继承 smooth 版本：从有效的已提交位置启动，先提交起点并取得新 CLOCK，随后
限制每次逻辑推进，避免调度延迟直接吃掉全部剩余动画。PAN 接受与 LCD 扫描完成
仍是不同事件，真实原生调用耗时没有严格上界。

## 息屏与唤醒

原 `panel_apps` 在关闭背光后把 `0x384ea638` 写为 0，在恢复亮度后写为 1。
代理 timer 先执行原 TIMER，再观察该状态；观察到 off 时要求 custom owner，通过
同一安全交接完成切换，不调用背光接口。恢复 on 后，第一个物理接触一直到 UP 都
不参与双击识别，但仍允许抽屉手势。

这是对可观察状态的处理：完整 off/on 若发生在两次 timer 采样之间就无法识别，
用户于 2026-10-07 确认 c 的息屏唤醒测试正常，后续版本未借用这个用户验收。
没有找到通用的锁屏插件生命周期入口。

## 自动返回与设置

原界面连续未触摸达到等待时间后，通过已有安全 handoff 返回图片，没有动画。
默认 60 秒，网页设置 0–3600 整数秒，0 关闭定时返回。只有触摸屏接触影响计时，
物理键不重置；持续接触、待处理触摸、手势或显示交接未闭合时不执行到期 PAN。
修改设置重新开始完整间隔。定时返回不控制背光，也不影响上面的息屏返回规则。
运行计时使用 224B context 的新尾字段。

GET/POST `/api/settings` 与图片共享网络 worker，设置值通过 broker mutex 发布。
持久化使用 `/data/86v1-return.0` 和 `.1` 两个 16B `VRT1`/sequence/seconds/XOR 槽，
启动取有效新序列或默认值。保存检查两槽文件归属与 FAT 对象，完整写入、fsync、close、
读回验证后才更新运行值并返回 HTTP 200。文件与原厂身份分离，NOR 安装/恢复不修改它们。
失败不承诺旧持久值原样保留。接口、用户操作和实机验收边界见 [自动返回说明](auto-return.md)。

## 网络与图片 RAM

端口 **HTTP 18086** 采用 [HTTP 图片 API](http-image-api.md)，不提供旧 raw TCP/VACK
兼容入口。本轮 `POST /api/image` 按内容签名识别完整 PNG、JPEG 或 VIMG，
Content-Length 为 1..1048576B。PNG/JPEG 要求 480×320，受支持范围见
[HTTP 图片 API](http-image-api.md)；设备不自动裁切缩放。旧 VIMG 仍是固定 307216B
header/body 和 FNV 校验。完整接收、解码、校验并发布到 GUI 待消费槽后返回 202；
它不是 LCD 扫描或 Flash 保存完成确认。
当前版本的 `GET /` 沿用正式网页 `https://wan.sh/xiaomi-86v1/` 的 303 配置，把设备
endpoint 放在普通 `device` query 参数中，不依赖电脑开发服务器。更换目标 URL 要创建、
冻结并安装新 release。显式配置空 URL 的构建仍提供 200 说明页，但它不是本轮发布的配置。

接收端不要求 Content-Type；非 identity Content-Encoding 返回 415。PNG 使用完整 chunk、
CRC、IEND 与压缩流收尾检查，JPEG 要求受限 baseline 单扫描、真实 EOI 和无损坏警告。
仅解码出足够像素不会发布。两个解码器都使用每请求的独立状态及 row 缓冲，不初始化
或复用共享 GUI 图片缓存；JPEG 包装只进入已审查的私有初始化路径，不接管原 GUI 资源。
PNG/JPEG 先分配完整 encoded body（最多 1MiB），在 inactive RGB565 槽解码，
所有临时资源释放后才标记 pending。失败保留旧 active 图片，网络等待和解码不持
GUI/publisher 锁；可用堆及原生 RPC 的真实耗时仍须实机确认。

[图片编辑网页](frontend.md)在浏览器内完成裁切、缩放，生成 PNG 和旧 VIMG，直接调用面板
API；Cloudflare 托管静态文件，不代理图片或访问用户的局域网。设备地址可由
`device` query 或用户手动输入，图片处理与下载不依赖面板连接。只有用户点击发送才
GET `/api/image` 查询能力；当前版本返回 PNG/JPEG/VIMG，其他设备上的旧维护版明确 404 才选择
VIMG。网络错误、无效能力响应及失败 POST 都不会触发自动换格式重发。

OPTIONS/CORS 已实现，origin 为 `*`，允许 GET、POST 与 Content-Type。历史四页 a 实际 GET
默认 60 秒，POST/GET 0 与 5 一致，3601 返回 422 且仍保留运行值 0；直接 Node 图片
POST 返回 202。这些接口检查不证明浏览器预检或 LCD 扫描。
此前 g 的 Windows Chrome 跟随真实 303 打开正式 HTTPS 页面、填写 endpoint 且无页面错误，
随后出现浏览器本地网络访问授权提示，自动验证没有发送 POST。用户报告该正式页面上传
正常；随后只读状态显示新 generation 已被 GUI 消费。这不是自动采集的 HTTP 状态、
内容读回或 LCD 扫描证据。
这些旧 HTTP 检查不验证本轮 PNG/JPEG。本轮能力 GET200 返回三种格式，设置 GET60
通过。直接 Node 的 PNG/JPEG POST202 及完整 RGB565 读回通过，具体记录见下表；
不把它们作为浏览器上传、LCD扫描或用户实屏验收。
没有客户端认证。A7 socket 经 usrsock/RPMsg 使用原 MCU 网络服务。
一次处理一条连接；待发布图片被 GUI 消费前，worker 不继续接受下一次上传。

一次 1843200B owned 分配包含 RGB32 画布 614400B、原画面快照 614400B，以及两个各
307200B 的 RGB565 槽。worker 只写 inactive 槽，接收完整并通过对应格式校验后标记 pending。
GUI 在帧队列为空、无活动 gesture/overlay 时短持 broker mutex 交换槽位，再把 RGB565
合成到 RGB32。部分/损坏上传不替换现有图片，网络等待不持 GUI/publisher 锁。

图片只在 RAM 中，重启丢弃；Flash 保存程序，MMC `/data` 仅新增自动返回设置，不保存图片。
启动分配/worker 创建失败且尚未启动原应用时释放自有资源并回退原入口。原应用返回后
已发布的 allocation 仍保持存活，避免回调或 worker 引用释放内存。

HTTP header 使用另外分配的 2048B 缓冲。应用设置 5 秒无进展、30 秒总请求期限，但
底层 native/RPMsg RPC 本身没有严格时间上界；连接错误也不保证客户端收到完整错误响应。

地址由 `wlan0`、40B `ifreq` 和 `SIOCGIFADDR=0x701` 查询。接口名@0、family@20、
IPv4@24；在 broker mutex 外以约 1 秒间隔查询，仅改变地址时标记重画，查询失败清为 0。
尚无地址时显示 `0.0.0.0:18086`，它不能作为上传目标。实际设备网络地址不提交到 Git。

## 代码、页面与上下文布局

| 项目 | 当前值 |
| --- | --- |
| 主 BIN | 3368B，`0x3804b108..0x3804be30`，容器余 64B |
| 主代码容器 | 3432B，exclusive 末端 `0x3804be70` |
| 辅助 BIN | 396B，`0x3807a764..0x3807a8f0` |
| 辅助容器 | 444B，exclusive 末端 `0x3807a920` |
| Thumb 入口 | `0x3804b2f5` |
| 网络 BIN | 4012B，`0x3804d000..0x3804dfac`，容器余 68B |
| 网络代码容器 | 4080B，exclusive 末端 `0x3804dff0` |
| 解码 BIN | 2916B，`0x38047098..0x38047bfc`，容器余 432B |
| 解码代码容器 | 3348B，exclusive 末端 `0x38047dac` |
| NOR code/entry/aux/net/codec 页 | `0x92b000` / `0xccd000` / `0x95a000` / `0x92d000` / `0x927000`，各 4096B |
| 安装基线及直接回退目标 | 精确的旧图片实验版三页与原厂网络/解码页 |
| 完整 ELF SHA-256 | `3f67d12758931a05fc22e20ddd89c51688ea9ec12de185ededce821b0ead79d3` |
| candidate 输入及 SHA-256 | 471 项；`992b58c7aa72a162aca23756088ce8951467fa1d624ba8c7889a155ab430021b` |
| freeze 输入及 SHA-256 | 477 项；`627a224c619b59a6813b47685e272cd19a4f8b25bb04af1bdbf690b31cf2a330` |

所有范围末端 exclusive。入口页新增禁用 `uorb_unit_test` builtin 的单字修改：page+`0xc3c`
从 `0x3804cf3d` 改为 `0x3804b109`。它不是启动服务；其其他已发现引用属于命令描述/帮助
统计，不会调用函数。网络段位于该独立审查函数内部，保留所在页最前 4B 和最后 12B；
原厂完整网络页 SHA 为 `76a994fbd3892960f43db969b4744fbb726d23feac5c24df86041398ee5d299d`。
解码页借用 `filldisk/fillcpu/fillmem` 诊断群；入口页 `+0xd68/+0xd7c/+0xca0` 的原指针
改为相同禁用 stub。解码页前 156B、后 592B 和实际 BIN 外字节保留，原页 SHA 为
`21c40d397e6ec14f61011544f736962470f623c91ba3bbf7a6d89d120ba23c02`。
安装 codec→net→aux→code→entry，恢复 entry→code→aux→net→codec，始终核对五个完整页面。
共享 helper/be70、背光 callback/a920、JSON helper/ae28 和容器外所有字节保留。
wifi_recorder 诊断 builtin 的禁用 stub 继承此前版本，它不是 Wi-Fi 驱动或启动服务；
原工厂 socket worker 只有受控辅助容器被借用，未启用原工厂 UDP 服务。

这里的“安装基线”指设备 Flash 必须先处于指定的完整字节集合：“三页”是已装旧图片
实验程序的三个 4KiB Flash 区域，网络和解码两个区域仍为原厂字节，五页都要逐字节匹配。
它不是三个屏幕界面页，也不是任意原厂设备都能直接首刷的通用起点。

224B context 的部分布局如下，已有字段的偏移不变，新计时状态追加在尾部。
旧 tap-fast、旧图片实验版及旧维护版 212B 的字段解释不能直接套用新尾字段。

| 字节偏移 | 字段 |
| --- | --- |
| +128 | 自有双击状态（含唤醒接触排除标记） |
| +144 | screen_off：0=awake，1=off observed，2=等待首个唤醒接触松开 |
| +148 | 抽屉手势状态 |
| +164 / +168 / +172 | animation_from / pending / phase |
| +176 / +180 | image / receive 槽指针 |
| +184 | image_pending |
| +188 / +192 | generation / displayed_generation |
| +196 / +200 | server_state / server_error |
| +204 | show_address：图片/地址页选择 |
| +208 | IPv4 四个原始网络序字节 |
| +212 / +216 / +220 | return_after_ms / activity_ms / activity_valid |

## 验证检查点与局限

| 证据 | 当前版本结果 |
| --- | --- |
| 离线模型 | 420 项解码器实际 ARM 检查、36 组 UI、34 组 HTTP、17 组设置；299 项 host HTTP 检查 |
| 客户端 | 29 项网页测试；Chrome154 真实 Canvas 多 IDAT PNG 在离线 HTTP/native/GUI 路径完整像素比对通过 |
| 发布及写入流程 | 12 项 release、116 项 writer mock 及 477-input freeze 已完成 |
| 执行路径 | `C:\p86-img-a` 完整 bundle 全部 hash 核对、116 项 mock 与冻结 CLI verify 通过；旧 `C:\p86-idle-a` 只用于其自身四页 release |
| 安装及暖启动 | 五页安装、完整页/native/cache/context、outer GLOBAL 和五页暖读回通过；fresh check 为 patched=true |
| 硬件能力与设置 GET | 能力 GET200 返回 png/jpeg/vimg；设置 GET60。没有继承旧版设置 POST 验收 |
| 直接图片 HTTP 与读回 | Node上传2204B PNG为202/计数1、55134B JPEG为202/计数2；两张完整RGB565匹配独立参考 |
| 错误图保护与最终状态 | 坏PNG CRC为422且保留JPEG及计数2；恢复默认PNG为202/计数3且完整像素匹配；alive/ready1、pending0、server1/error0，GUI cycles推进 |
| 正式网页 | 版本2ee45a5f-6b04-42ce-80bb-2e92e4dc4cc5，五项资源一致、零浏览器错误、初始零自动LAN请求 |
| 实际 HTTPS 浏览器上传 | agent Chrome 点击 Send：GET 能力200、单次6050B PNG POST202，未添加 Content-Type；origin-scoped CDP 临时授予本地网络权限，非用户点击许可，结束后恢复 prompt |
| 浏览器上传后只读核验 | 完整307200B RGB565 匹配默认图参考，槽位和计数稳定；generation/displayed_generation=4、pending0、alive/ready1、server1/error0，GUI cycles 推进；不测量 LCD 扫描 |
| 用户验收 | 用户浏览器权限/上传、LCD、原界面交互、自动返回、息屏与米家待分别确认；Node请求耗时不作为性能基准 |
| 迁移前后检查 | 旧四页版 patched→自身 restore→新五页 original→五页 install→fresh patched，各自完整集合单列验证 |
| 当前恢复路线 | 旧四页版自身 restore 已通过；新五页版自身硬件 restore 尚未测试 |
| 完整断电 | **按用户明确要求跳过**，没有借用旧版冷启动结论 |

模型执行真实 ELF 和已核对 SHA 的原厂解码指令，OS、分配器、部分 libc、锁和 GUI 驱动边界
仍由 mock 提供；不证明可用堆、真实 RPC/调度、LCD 或全输入的栈上界。HTTP ELF 仅加载
allocated PROGBITS sections，保留原厂代码在 ELF 地址空洞中的字节，不能用 PT_LOAD
的空洞零填充代替。上述 Canvas 检查也不是浏览器实际网络 POST 或实机显示证据。
正式页面的独立实机浏览器请求已在上表记录，不能与离线Canvas证据混为一项。
最初浏览器本地网络 prompt 阶段 GET 等待，没有 POST；agent 仅对测试 Chrome 的正式网页
origin 临时授予 CDP 权限后才完成一次发送，测试结束后权限已恢复为 prompt，
没有把它记录为用户授予权限。完整 RGB565 与计数通过另一次只读 MEM-AP 核验，
浏览器请求和像素读回都不证明 LCD 扫描或用户交互验收。

## 历史四页自动返回版检查点

历史四页自动返回版为 `maintained-idle-return-four-page-20261007-a`：main/aux/net
3344/396/4072B，382-input freeze，候选 SHA
`6022cbd3e41cfc913a260ff17855582c47656318227dfb6defc55230be503f55`，冻结表 SHA
`660534d525762b83b8029b3adebd82a20d84723d5706e53afc6f6790a5c64cb4`。
当时 76 组实际 ARM、290 项 host、93 项短根 writer mock、12 项 release 和 19 项网页测试
通过。g 自身恢复后四页 a 安装、完整页和暖读回通过；原始结果中 a 自身恢复未测试。
其自身恢复现已在本轮五页迁移中通过，记录在新迁移证据，不改写旧发布结果。
真实默认 GET60、POST/GET0 和 5、3601 返回422且保留运行值通过；保存5后一次独立
AON GLOBAL 暖复位加载5，随后保存回60。直接 Node VIMG POST202，GUI消费后
generation/displayed_generation=1、pending0/server1/error0/return_after_ms60000。
它不证明 LCD、浏览器上传或用户交互/米家验收。正式网页部署为
`ecf90b3d-d93f-4a09-aab7-7d5b513a9d49`，精确资源和初始零LAN请求/无页面错误通过。
这类历史 result 保持原样；后续恢复结果将在新迁移记录中补充，不改写旧结果。

这些是保存的检查点，不表示实时运行监控。MEM-AP 样本非原子，HTTP 202 不测量扫描时刻。
此前 g 的 GET 与浏览器自动填地址有独立实测；HTTPS 网页上传由用户报告正常，随后只读
状态显示 generation/displayed_generation=1。本轮没有自动采集其 POST 状态或上传后
像素。用户同时收到米家、默认图等合并问题，但简短回复未
分别确认这些项目，因此保留当时未验收范围。g 自身 restore 在迁移至四页自动返回版时另行记录，
不改写旧 g 的原结果。

此前 d 的错误 FNV/magic 请求没有增加 generation；两次完整上传后 generation 和
displayed_generation 均为 2，用户确认默认卡片显示及手机 LAN 跳转。这些历史检查点
保留在 d 结果中；d 的硬件 restore 后来在 d→g 迁移中通过，不覆盖 d 原 result。
`server_error` 记录最近请求错误，不能单独当作 worker 故障。

旧图片实验版的 33 组 ARM、12 组独立检查、70 项 writer mock，以及用户确认的两图、
上下滑、key3 往返和米家控制仅属于旧三页 TCP 版本。其无效 header、half-close 和
10.038 秒 idle 观察保留在 [历史协议](image-upload-protocol.md)，不作为当前 HTTP 验收。

原字体只完成静态可行性分析，未调用实机字体文件或 glyph API。当前采用私有数字字形
显示地址，来图已经光栅化；不能宣称已复用系统字库。
