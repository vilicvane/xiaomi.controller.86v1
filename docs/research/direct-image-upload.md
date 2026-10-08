# 直接上传 PNG / JPEG 研究

日期：2026-10-08。对象：本机精确原厂 1.50.10 的 A7 映像。
研究开始时安装为 `maintained-idle-return-four-page-20261007-a`，只接受 VIMG。
以下保留第一阶段离线研究结果；后续实现状态另见文末，不把研究模型当作设备验收。

## 结论

普通 PNG / JPEG 文件可以成为后继固件的上传格式。原厂图像解码代码已在离线 ARM
模型中输出完整像素，PNG 还验证了使用独立实例和内存读取回调的路径。
这比只确认库名、字符串或电脑端解码更进一步，但不是已安装固件的 API 能力。

用户希望直接提交图片文件，不必制作 VIMG。2026-10-07 的
[无损 VIMG 压缩研究](image-compression.md)保留为另一种传输方案；本轮优先验证标准
图片格式。PNG 适合界面、文字及无损画面，JPEG 可减少照片的传输量。

所有原厂地址仅属于 SHA-256 为
`777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b`
的原 NOR 备份。模型将其中 `0x8e0004..0xdd3fe4` 映射到 A7 的 `0x38000000`，
执行原指令，使用受限模拟堆。实机可用内存、耗时、线程栈和并发尚未测量。

## PNG 实际解码

原 LVGL 文件解码 callback 不是可以直接调用的通用内存 API。此次另建私有
`png_image`/control/png_struct，配置有界读取回调，再调用原厂初始化、头部解析、
颜色变换和逐行解码代码；没有打开文件、初始化 LVGL 或借用 GUI 图片缓存。
第一阶段的私有结构初始布局由 host 模型写入；完整 ARM 初始化器在后续实现中另验。
下表地址包含 Thumb 位，名称是反汇编及离线执行确认的内部职责，不能直接套用公开头文件 ABI。

| 内部职责 | 本映像地址 |
| --- | --- |
| 创建 read 状态 | `0x3838d925` |
| safe execute / 错误返回包装 | `0x38100f05` |
| 简化图片头部处理 | `0x38073489` |
| direct 变换及像素读取 | `0x38071a19` |
| 原生逐行读取 | `0x3838a221` |
| 释放图片状态 | `0x383c3475` |

六个 480×320 PNG 包含仓库原 GitHub 卡片、RGB、调色板、灰度、带透明度 RGBA、
主板照片。原厂输出的 straight RGBA8 与 host 参考逐字节相同；按当前网页的黑底
合成及 RGB565 量化规则转换后，六个最终 RGB565 也逐字节一致。
目前样本为 8-bit、非交错 PNG；不把这个集合推广为所有 PNG 位深、交错和色彩配置均已验证。

整幅 RGBA 路线需要 614400B 临时输出，原库请求分配字节峰值为 46234–53252B，
另加编码输入长度；不含 guard、分配对齐、私有 context 或原库栈，不是实机堆峰值测量。
后续逐行原型使用 1920B RGBA scratch 转换到 307200B inactive RGB565，避免整幅 RGBA。
逐行原型暂以改写私有 `png_image.height` 跳过 direct 内部整幅循环、随后单独读取 320 行；
这是针对本映像的实验适配，不能作为稳定公开 API 或已完成的正式解码器。

### 完整性缺口

原简化读取完成像素后仍留下 12B IEND；缺 IEND、损坏 IEND、尾随数据和拼接第二张 PNG
均能返回像素成功。这个行为也符合 libpng 1.6.38 的 simplified 路径没有调用
`png_read_end` 的实现。[libpng 原实现](https://raw.githubusercontent.com/pnggroup/libpng/v1.6.38/pngread.c)

接收器必须另外验证完整 chunk 边界、顺序、CRC、零长度 IEND 及其恰好位于 body 末尾，
并严格处理 IDAT/zlib 收尾及解码 warning。只检查尺寸、像素数量或 finish 返回值不够。
是否采用完整容器预检查加简化读取，或复用 owned classic reader/read_end，仍需在正式候选中决定。
原库某些 IDAT 异常是 benign warning，不能把没有 fatal error 等同于文件完整。
[IDAT 实现](https://raw.githubusercontent.com/pnggroup/libpng/v1.6.38/pngrutil.c)

失败样本覆盖签名、截断、IHDR/IDAT CRC、Adler 及晚期分配失败；已测退出路径释放后
模拟堆存活分配为零，guard 与原 A7 程序字节保持不变。ARM 编译读取回调版本在执行
原厂函数时只以 host 函数替代 malloc/free，结构初始化仍由模型写入；早期定位版本
的读取回调也是 host shim，两者证据分开保存。
基础模型执行 23 例，编译 ARM 回调模型执行 15 例，共 38 次案例执行；不等于 38 张图片。
私有 ARM glue 为 334B，包含读取及逐行 RGB565；自身读取/行处理栈帧为 16/72B，
不包含原库栈、正式初始化、容器完整性或 HTTP 接收代码。

## JPEG 实际解码

内存源在本映像中确实保留，不只存在文件读取接口。两个 JPEG 的独立头部探针执行
原厂 create、memory source、header，得到 480×320、三分量；另有截断头和坏 SOI，
共六例，错误后通过原 memory manager 清理，guards/原程序保持不变。

| 已确认内部职责 | 本映像地址 / ABI |
| --- | --- |
| 内部 create decompress | `0x3838cfa5`，一个 cinfo 参数，公开 version/size 检查已折叠 |
| memory source | `0x380d16c5`，cinfo、输入指针、输入长度 |
| 内部 read header | `0x3838d259`，一个 cinfo 参数 |
| 原 LVGL 整图 callback | `0x3806b375`，用于此轮整幅像素模型 |

本机 cinfo 分配范围为 464B，error manager 为 128B；这些不是从电脑库头文件推定的 ABI。
整图探针把原文件装载 helper 换成私有内存输入，替代 native/LVGL heap 边界及 OS getenv、
错误/日志边界；JPEG 头部、熵解码、IDCT、颜色变换和行处理均执行原 ARM 指令。
它验证了原 decoder 的像素能力，仍未成为脱离 LVGL wrapper 的正式上传入口。

两张 quality 85、4:4:4 JPEG 都输出 614400B；观测到 B,G,R,255 排列，交换 R/B 后
与电脑解码同一 JPEG 的 RGBA8 逐字节相同。这个一致性不代表 JPEG 与压缩前原画无损。
全图 wrapper 堆峰值分别为 658375/702503B，包含编码文件、输出及内部状态；清理后为零。
头部探针的 18154B 峰值不能代替整图内存预算。

另测缺 EOI、只保留半个文件、追加尾垃圾：三例 wrapper 仍返回完整尺寸的像素；
前两例出现 warning，尾垃圾没有 warning。这不能用于接收成功条件，必须核对真实
JPEG 结束、输入消费及损坏警告。默认内存源会注入合成 EOI 是官方库的行为。
[JPEG 内存源实现](https://raw.githubusercontent.com/libjpeg-turbo/libjpeg-turbo/2.1.3/jdatasrc.c)

此轮未验证 progressive、CMYK/YCCK、其他 subsampling、EXIF 旋转或逐行独立 JPEG glue。
后续可复用 RGB scanline，再逐行转 RGB565；公开库的 RGB565 枚举也需要本机 ABI 与
抖动规则的额外验证，不能直接照抄数字。
[JPEG API](https://raw.githubusercontent.com/libjpeg-turbo/libjpeg-turbo/2.1.3/libjpeg.txt)

## 传输大小

所有输入已在电脑裁到 480×320。数字是编码文件字节，不包含 HTTP 头。

| 画面 | 直接 PNG | JPEG 85 / 4:4:4 | 完整 VIMG zlib level 6 | 原 VIMG |
| --- | ---: | ---: | ---: | ---: |
| GitHub 卡片 | 原文件 2204B；RGB 1751B；调色板 1007B | 11006B | 1178B | 307216B |
| 主板照片 | RGB 192178B | 55134B | 155966B | 307216B |

PNG 参考回环无损；card 的调色板编码也保留相同 RGB565。JPEG 对比编码前画面，
card 的 RGB RMS 误差为 1.808、5.74% RGB565 像素变化；照片为 4.535、73.30% 像素变化。
只有一张照片样本，这些值不是通用画质或壁纸压缩率结论。

## 建议的后继 API

同一个 `POST /api/image` 接收普通文件 body，按 PNG/JPEG 内容签名识别；
Content-Type 可声明，也可省略，不要求 multipart、VIMG 头或 Content-Encoding。
首版固定图片尺寸 480×320，网页继续负责裁切缩放并直接导出 PNG。
透明图片明确铺黑底，最终仍是 RGB565。JPEG 属于另一条有损路线。

以下是第一阶段提出的接口示例，**当时安装的 idle-return a 不接受它**；后继实现已支持：

```sh
curl --data-binary "@wallpaper-480x320.png" "http://PANEL_IPV4:18086/api/image"
```

`@` 表示读取文件。继续要求唯一、准确、已知的 Content-Length；长度改为有上限的可变值。
解码器每请求拥有独立状态和内存预算，先在头部检查尺寸，再只写 inactive receive 槽。
现有 GUI 的 RGB32 pixels/snapshot 不作临时解码区；只有文件完整、无损坏警告、所有像素
完成且状态清理后，才在既有短锁中 publish pending，返回 202。失败保留当前显示。
202 仍表示 RAM 排队，不表示完成扫描输出或图片持久化。

原厂 libpng 简化 API 会跳过不用的文本等 chunk，但启用时仍检查 iCCP；输入长度与尺寸
限制不能单独限制全部内部元数据分配。正式实现要核实 vendor 配置并施加预算或明确忽略策略。
[libpng API 定义](https://raw.githubusercontent.com/pnggroup/libpng/v1.6.38/png.h)

## 容量与落地边界

第一阶段 idle-return a 的冻结 map 中 prefix 已满，main/aux/network 分别只余 88/48/8B，共分散 144B。
这不是整颗 Flash 的可用空间统计，也不证明额外胶水可直接放入这些位置。
旧 g 的网络段余 1104B 是历史事实，不能用于当前集成。

第一阶段没有创建或安装后继 release，也没有运行 OpenOCD 或设备原生调用。
后续实现使用下述独立区域和逐行解码，不把这一阶段的 wrapper 实验当作集成结果。

## 后继实现

维护源码新增 `image-codec.c`。HTTP 接收完整的有界文件，按内容签名选择 PNG、JPEG
或原有 VIMG；图片尺寸固定 480×320，输入最大 1MiB，仍要求唯一、准确的 Content-Length。
能力查询 `GET /api/image` 返回支持的格式。网页在显式发送时查询能力，支持时发送
裁切后的普通 PNG；只有明确的旧接口 404 才选择 VIMG，不自动重试失败上传。

PNG 使用本映像的原生 libpng，每次独立创建状态、reader、allocator 和一行 RGBA
缓冲区。提前核对 chunk CRC、顺序、尺寸和白名单；逐行转换为铺黑底的 RGB565，
拒绝 warning、损坏压缩流和尾部数据。首版支持 8-bit、非隔行的灰度、RGB、索引色
及其透明度；元数据范围见 [API](../http-image-api.md)。

JPEG 使用本映像的原生解码器。LTO 将 master 初始化内联进 GUI wrapper，因此用独立
私有 frame 进入已审查的初始化片段，在其一行分配处通过私有 callback 和原生
setjmp/longjmp 返回，然后逐行调用私有 main processor。不会进入 FILE 加载、GUI
整帧分配或原界面 cache，也不修改原生代码及全局回调。首版限单扫描 baseline、8-bit，
灰度或 4:4:4/4:2:2/4:2:0；核对实际 EOI、消费完输入且无损坏 warning。不处理 EXIF 旋转。

两种格式只写既有 inactive receive 槽，状态和输入内存清理完成后才发布 pending。
失败可以留下备用槽的部分像素，但不交换当前图，也不推进 generation。GUI 继续负责
换图与显示交接；图片仍只保存在 RAM。网络 worker 保留原调度属性，栈从 4KiB 改为
16KiB，避免解码调用链使用原来的小栈。

新增解码容器位于 `0x38047098..0x38047dac`，对应 NOR 页 `0x927000` 内的
`filldisk/fillcpu/fillmem` 诊断组。独立 ownership 审查包括完整备份、引用扫描和
启动命令检查；禁用三个诊断 builtin，并保留页头 156B、页尾 592B 及 payload 外字节。
这是第五个完整验证区域，不能在旧四页 release 上叠加 writer。新安装顺序为
codec→net→aux→code→entry；恢复反向，先移除入口引用，再恢复依赖。原生 caller
和不确定结果保留停点的规则不变。

ARM 测试须先加载精确 stock A7，再覆盖 ELF 的实际 allocated PROGBITS sections。
不能复制整个 PT_LOAD：分段代码之间的 ELF 填零空隙会覆盖仍需调用的原生库。
测试保护输入、输出、堆和原生/项目代码，禁止 FILE/GUI wrapper 路径；完整 HTTP
模型另外验证 GUI 换图、连续 PNG→JPEG→PNG、上传中断和 OOM。离线解码与 mock
不代表实机堆预算、调度、LCD 或冷启动已验证；安装状态以独立发布结果为准。

### 本次安装与验证

`maintained-images-five-page-20261008-a` 已通过旧版自身恢复、精确基线检查及五页安装，
完整页读回、原生调用收尾和暖启动检查通过。直接 PNG、JPEG 请求均返回 202，
全部 RGB565 像素读回与参考一致；损坏 PNG 返回 422，当前图片和 generation 不变。
正式网页在 Chrome 中发送的 6050B PNG 也返回 202，随后完整像素读回一致，
generation/displayed_generation 为 4、pending 为 0。

网页测试使用临时、限于 `https://wan.sh` 的 CDP 本地网络授权，测试后已恢复 prompt；
这不代表用户点击了权限提示或所有浏览器都可用。LCD、手势和米家用户观察尚待确认，
新版自身恢复未做实机测试，冷断电测试按用户要求跳过。完整范围见
[发布结果](../../firmware/releases/maintained-images-20261008-a.json)。

## 私有证据

- `build/compression-research/direct-image-fixtures-20261008/manifest.json`：8 个文件及 host 参考，
  SHA `d046be710497626fbd7784da84b9a5bd718b89895991dbd437708cb341611c89`。
- `build/compression-research/direct-image-native-20261008/native-png-summary.json`：PNG 静态、
  host-reader 及编译 ARM glue 模型，SHA
  `0f68b58a06c3c1dda4aeab9c2201f3e94d64bd0875a7ad611f19ab09f438307e`。
- `build/compression-research/direct-jpeg-static-20261008/header-result.json`：6 个原 ARM JPEG 头部案例。
- `build/compression-research/direct-jpeg-static-20261008/pixels-result.json`：2 个完整像素及 3 个尾部/截断案例。
- `build/compression-research/direct-jpeg-static-20261008/native-jpeg-summary.json`：JPEG 模型边界与输入 hash，
  SHA `7e04348123d05bef3e099740a86ed450315f92a31903ec81285841ce12a4392f`。

原图、像素 buffers、反汇编和编译产物均保留在 ignored 私有目录，不进入 Git。
