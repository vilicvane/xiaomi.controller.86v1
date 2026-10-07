# 图片上传协议与客户端

范围：已安装 `native-image-drawer`、本机 1.50.10 映像。协议实现在
[设备程序](../analysis/image-push/native-image-drawer.c)和
[上传器](../analysis/image-push/push_panel_image.py)。下一版 HTTP 入口尚未实现。

## 上传

使用面板默认画面显示的非零 IPv4 地址，端口默认 **18086**：

```powershell
python -X utf8 analysis/image-push/push_panel_image.py PANEL_IP --pattern
python -X utf8 analysis/image-push/push_panel_image.py PANEL_IP --image picture.png --fit contain
python -X utf8 analysis/image-push/push_panel_image.py PANEL_IP --raw picture.rgb565
```

PNG/JPEG 转换需在电脑安装 Pillow（`python -m pip install Pillow`）；pattern 和 raw
只依赖 Python 标准库。其他选项以 `--help` 为准。

| `--fit` | 行为 |
| --- | --- |
| `contain` | 保持比例，空余部分加深色边 |
| `cover` | 保持比例，裁切到完整画面 |
| `stretch` | 缩放填满，可能改变比例 |

电脑将图片转换为 480×320、little-endian RGB565 位图。设备不解码 PNG/JPEG，传输
不使用它们的压缩格式；单次像素 payload 为 **307200B（300KiB）**。屏幕驱动处理
旋转，协议尺寸是逻辑画面尺寸。

## 请求

一条 TCP 连接只上传一张图片：16B header 后紧接恰好 307200B payload。
传输层可以任意分片，receiver 处理 partial I/O。

| header 偏移 | 类型 | 内容 |
| --- | --- | --- |
| 0 | 4B ASCII | `VIMG` |
| 4 | u16 LE | width=480 |
| 6 | u16 LE | height=320 |
| 8 | u32 LE | payload length=307200 |
| 12 | u32 LE | payload 的 FNV-1a 32 位校验和 |

RGB565 每个像素先存低字节，再存高字节，bit15..11 为 R、bit10..5 为 G、bit4..0 为 B。
像素按逻辑行顺序排列。FNV-1a 从 `0x811c9dc5` 开始，每个 byte 先 xor，再乘
`0x01000193`，以 32 位截断；校验不包含 header。

设备只在完整接收及校验后发布，部分、超时或损坏内容不会替换当前图片。连接结束
不用于标记 payload 长度；上传器发送后等待 ACK，**不使用 `SHUT_WR` 半关闭**。

## 确认

reply 共 8B：ASCII `VACK`，随后为 u32 LE status。

| status | 当前含义 |
| --- | --- |
| 0 | 内容被接受并发布供 GUI 消费 |
| 1 | header 无效、内容截断或接收被拒绝 |
| 2 | 校验不匹配，或完整接收后无法发布 |

VACK0 不表示 LCD 已完成扫描，不保证内容在重启后存在。后续新上传替换前一张，
所有图片 RAM-only；重启恢复地址画面。协议监听局域网接口，没有 sender 认证，
FNV 只检测内容错误，不建立可信来源。

## 已知连接边界

当前 worker 串行处理连接，非阻塞 socket 与 `MSG_DONTWAIT` 处理 EAGAIN/EINTR，
接收阶段有 5 秒无进展、30 秒总时长的应用单调时钟检查；ACK 使用独立 deadline。
这些检查没有证明底层 native RPC、mutex 等待或整笔交易的严格墙钟上限。

两张完整测试图分别在约 5.582 秒和 7.031 秒收到 VACK0，并有用户实屏确认。
一次空连接到回复/退出耗时 10.038 秒；不能承诺 5 秒内断开。初次无效 header 和
客户端半关闭截断没有完整 ACK，随后无效 header 得到 VACK1，完整错误校验和得
到 VACK2。拒绝回复不是每条错误连接都保证送达，缺少 ACK 时客户端应报告不确定
结果，不据此推断图片已发布。

实际网络结果保存在 [硬件记录](../analysis/persistence/native-image-drawer-hardware-result.json)，
半关闭条件路径的静态复核见 [ACK 分析](../analysis/image-push/ack-path-static-recheck-1.50.10.json)。
半关闭无回复的准确实机原因尚未完整捕获，不能把条件路径分析写成已证明根因。
