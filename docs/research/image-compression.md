# 图片压缩传输研究

日期：2026-10-07。对象：本机 `xiaomi.controller.86v1` 的精确原厂 1.50.10 映像，
本轮当时安装为 `maintained-http-four-page-20261007-g`。
本文保留迁移到四页自动返回 a 时的无损传输研究；随后已接入并安装标准 PNG/JPEG，见
[直接图片上传研究](direct-image-upload.md)。本文的 g 容量与接口选择属于当轮记录。

## 结论与范围

优先研究复用原厂 zlib，将网页已经生成的 RGB565 画面无损压缩后发送。
这保留裁切、颜色量化、VIMG/FNV 和 GUI 交接的语义，不需要先接入 PNG/JPEG 的整套图像解码。
原厂解压函数已经定位，并通过 36 个实际原 A7 指令的离线模型案例。
本轮没有安装压缩版固件；现有网页和 g 仍使用未压缩上传。

研究分为电脑压缩基准、原厂代码静态定位和离线 ARM 执行。
它们不证明设备端解压速度、实时堆余量、网络延迟或实机线程集成正确。
地址和 ABI 只属于下列精确原厂备份：
`777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b`。

## 大小基准

现有完整 VIMG 是 16B 头加 307200B RGB565，总长 **307216B**。
以下将整个 VIMG 用 zlib 包装的 DEFLATE 压缩，包含压缩头和校验尾，不包含 HTTP 头。

| 输入 | level 1 | level 6 | level 9 | level 6 占原大小 |
| --- | ---: | ---: | ---: | ---: |
| 默认 GitHub 卡片 | 3660B | 1178B | 1016B | 0.38% |
| 合成平滑渐变 | 32685B | 23637B | 21614B | 7.69% |
| 合成界面色块 | 3667B | 1561B | 1095B | 0.51% |
| 确定性高熵数据 | 307317B | 307317B | 307317B | 100.03% |
| 用户提供的主板照片 | 167194B | 155966B | 155427B | 50.77% |

五例均验证解压后 VIMG/RGB565 字节完全相同。Node 24 的
`CompressionStream("deflate")` 与 Node zlib 双向互通，生成的完整 VIMG 大小与 level 6 相同。
这不是网页浏览器兼容性或面板速度测量。

基准使用实际 `web/src/panel-api.ts` 的颜色量化函数。主板照片只在电脑内存中用 Lanczos3
cover 到 480×320，是单张 PCB 摄影样本，不能代表所有壁纸。默认卡片源文件本身为 2204B PNG。

另测了 gzip、raw DEFLATE、PNG 和最简单的 RGB565 游程编码：

- gzip/raw DEFLATE 与 zlib 的差别主要是包装与校验，不能把三种格式混用。
- PNG 的逐行过滤能改善某些图案：平滑渐变 PNG 为 3333B，而直接压 RGB565 为 23623B。
  这里 PNG 存储 RGB8，量化回 RGB565 完全一致，但它和压缩 RGB565 不是同一种字节表示。
- 简单游程编码每包是 16 位 count 加 16 位颜色；照片增至 452560B，不宜作为通用路径。
  此结果不是另一个带 literal/repeat 包的 RLE 设计的基准。
- 高熵内容会膨胀，客户端应在压缩更小时采用压缩，否则发送原始 VIMG。
- JPEG 未参加无损比较；它需要单独定义画质误差，无法保证原 RGB565/FNV 字节不变。

私有基准目录：`build/compression-research/benchmark-20261007/`。
`report.json` SHA-256：`5550e206fcb57994e2afea8456aa99f1c37d5ae5f8114a3a70c61ba3a35b9256`。
其中源照片路径、像素 fixture 和原图不进入 Git。

## 原厂解码能力

原 A7 映像包含 libpng、JPEG-turbo 和 zlib。静态证据支持原系统拥有压缩图像与 HTTP
内容解码路径；它不证明每张设备图标或每次网络下载都使用压缩。
完整图像资源文件及实际下载响应尚未采集；NOR 备份也不包含 MMC 上的全部资源。
有代码引用的版本信息为 libpng `1.6.38.git`、zlib `1.2.12`。

目前定位的 zlib 函数如下，地址包含 Thumb 位：

| 函数 | 地址 | 参数/用途 |
| --- | --- | --- |
| 内部初始化函数 | `0x3838cc15` | `int init(z_stream *, int windowBits)` |
| inflate | `0x380f9009` | `int inflate(z_stream *, int flush)` |
| inflateEnd | `0x380fa855` | `int end(z_stream *)` |

初始化函数经过链接优化，只有两个参数，版本和结构体大小检查已折叠；
**不能按公开四参数 `inflateInit2_` 或三参数 `inflateInit_` ABI 调用**。
本映像中的 32 位 `z_stream` 为 56B：next/avail/total input 在 +0/+4/+8，
next/avail/total output 在 +12/+16/+20，msg/state 在 +24/+28，
zalloc/zfree/opaque 在 +32/+36/+40，其余 data_type/adler/reserved 在 +44/+48/+52。

默认分配包装调用本机已使用的 malloc/free，初始化状态分配 7120B；
分次解码还可能分配 32768B 的历史窗口。状态属于每个解码实例，不必初始化共享 GUI 或字体缓存。
实机仍需核对当前线程栈、堆余量、指令字节和调用上下文；离线模型用模拟堆替代了真实分配器。

### 实际 ARM 指令验证

模型加载完整原 A7 程序段，实际执行初始化、inflate、inflateEnd、复制及 Adler32 指令，
只替代原 malloc/free；没有用电脑 zlib 或 stub 代替原解压函数。
除初始 RGB565 单次解压外，三组 **36 个 case** 通过：

- 五个完整 VIMG 样本均逐字节一致，包括 155966B 的摄影输入。
- 2048B/1B 输入分片、31B 输出分片，以及不连续的 16B 头与 RGB565 输出槽。
- 截断、坏 Adler、错误包装、预设字典、输出不足和多 1B 输出；状态/窗口分配失败。
- 满输出后的 1B 流尾探针能继续处理分片 Adler；超额输出可被单独识别。
- 成功和初始化成功后的失败路径都调用 end，模拟堆存活分配归零，边界 guard 保持不变。
  模型中的原 A7 程序段也保持原字节。

流式峰值为 **39888B = 7120B 状态 + 32768B 窗口**，不含现有画布、接收缓冲和调用栈。
完整单次解码部分案例只需 7120B；不能据此给网络分片接收按 7120B 预算。
这些是此库与模型内 allocator 请求的大小，不是实机可用堆测量。

实际代码也确认：END 后尾随字节和第二个 zlib 流不会自动报错，而是留作未消费输入。
接收器必须自行核对输入完全消费，不能把 inflate 返回 1 单独视为完整请求成功。
私有证据目录为 `build/compression-research/native-20261007-01/`，不包含硬件执行结果。
`native-compression-summary.json` SHA-256：
`ccbf1defd89d6862cb054bd0c2ccb54a6bc45a8f9b079114157ec398e55f4cf2`。

另有计数边界：需要预设字典时可已消费 6B，但 total_in 仍为 0；窗口分配失败时可已写
部分输出，但 total_out 尚未更新。接收进度应由实际供给和 avail_in 维护，失败缓冲区
无条件作废，不根据这些失败计数决定发布。END 成功时再核对完整输入和输出长度。

## 接入当前接收器

当前 GUI 已拥有两个各 307200B 的 RGB565 槽。网络 worker 写未显示的 `receive` 槽，
成功后设置 pending，GUI 在没有手势和动画占用时交换 image/receive。
流式解压可以沿用这条路径，无需保存整份压缩输入；失败时不发布 pending，旧图继续显示。

建议先采用标准 HTTP 编码：同一个 `POST /api/image`，body 为整个 VIMG 的 zlib 压缩流，
附 `Content-Encoding: deflate`。未编码请求仍发送原 VIMG。
HTTP 中的 deflate 和浏览器 CompressionStream 的 deflate 都是 RFC1950 zlib 包装，
不是 `deflate-raw`。[HTTP 定义](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.4.1.2)、
[浏览器压缩标准](https://compression.spec.whatwg.org/#supported-formats)。

解码接收必须满足：

1. 单一 Content-Length 表示压缩长度；保持不支持 chunked、Expect 和连接复用。
   压缩请求可限制为不超过原 VIMG 大小，客户端对更大结果选择 raw。
2. 先解出 16B 头并验证 VIMG、480×320、未压像素长度 307200，再将像素写 receive。
3. 得到 307216B 输出不等于成功：继续校验 Adler32，必须获得 `Z_STREAM_END`。
   满输出后可用 1B scratch 检测超出长度的输出。
4. END 时输入消费量必须恰好等于 Content-Length；拒绝尾垃圾和拼接的第二个流。
   不以 TCP EOF 作为唯一结束条件，也不能只相信输出长度或 FNV。
5. 所有初始化成功后的退出路径都执行 end。`Z_BUF_ERROR` 应结合是否还能提供输入/输出判断，
   不能无进展地反复调用。[zlib 流式语义](https://zlib.net/manual.html)。
6. 解码和网络等待不持 GUI 锁。沿用请求总期限和无进展期限，并在解码循环检查时间；
   不把循环检查误写为原生调用严格可中断。
7. 最后验证解压后 RGB565 的 FNV，才进入原有短锁发布。202 仍只代表 RAM 排队，
   不代表 LCD 完成或图片持久化。

当前 g 网络代码为 2976B，独立容器上限 4080B，余 **1104B**。
其他分散空位不能直接当作一个连续解码器区域。复用原厂 inflate 避免新增整套算法代码；
完整 HTTP/parser/能力探测的编译容量和线程集成仍需在新候选中验证。

私有 `build/compression-research/capacity-20261007/` 另做了最小流式胶水编译：
使用项目 LLVM18、Cortex-A7 Thumb、`-Oz` 参数，`.text` 为 **276B**，其中 260B 指令、
16B literal，`.rodata/.data/.bss` 为 0，自身栈帧 96B。该对象只编译、没有执行，
也没有接入 HTTP/parser、VIMG/FNV、能力探测、发布或 GUI；它只证明适配代码量有可行基础，
不能从 276B 推导整个压缩功能一定容纳或已验证安全。
`report.json` SHA-256：`c1499aaeb00d8d661784539dd288ac71a1543d0cceba716d582864983b956778`。

## 网页、API 与上线顺序

网页应先压缩完成为 ArrayBuffer，再 fetch；不要直接把压缩 ReadableStream 用作当前设备请求体。
新增 Content-Encoding 会触发编码相关的 CORS 预检，固件需要允许该头，Content-Type 仍可省略。
[Fetch 规则](https://fetch.spec.whatwg.org/#cors-safelisted-request-header)。

已部署 g 只接受固定 307216B body，官网不能直接改成默认发压缩请求。
先在后继固件接入 raw/deflate，再发布客户端能力选择。可让 `GET /api/image` 返回空 200 和
`Accept-Encoding: deflate`，并通过 CORS expose 该响应头；旧 g 的同一路径 GET 返回 404，
客户端继续 raw。该响应头有“支持后续请求编码”的标准语义，无需增加一个版本 JSON。
未知能力也保持 raw，不能用失败 POST 后自动重试来探测。
[请求编码能力响应](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.5.3)。

标准方案的压缩下载可命名 `.vimg.zlib`，cURL 需要明确编码头：

```sh
curl -X POST "http://PANEL_IPV4:18086/api/image" \
  -H "Content-Encoding: deflate" --data-binary "@picture-480x320.vimg.zlib"
```

这只是未来接口示例，当前 g 不接受它。`@` 仍表示读取文件内容；解压后才得到完整 VIMG。

另一种选择是应用内 `VIMZ` 魔数：保留 16B 尺寸/未压长度/FNV 头，仅压缩尾部像素。
文件可用 `.vimz` 自描述，cURL 无须额外编码头，也不新增这个头引起的预检；代价是维护私有格式。
两种设计不能混合声称同一压缩范围，目前均未接入正式固件。

## 后续验证

在已完成的原厂 inflate 离线证据基础上，在独立候选中接入接收器，核对整体代码容量及
ARM HTTP 模型。随后按现有发布流程审查、冻结、安装及测量实机解码/上传表现。
安装仍使用各版本自己的精确恢复与冻结执行器；本研究不修改现有 release。
