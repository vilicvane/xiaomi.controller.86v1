# 米家面板配网恢复记录

原固件为 1.48.5。最初 Wi-Fi 已认证、关联并获 IP，失败发生在米家云 TLS 握手，不能用这次失败证明 Wi-Fi 名称或密码残留导致故障。

只读固件分析发现：生成 `/data/etc/device.info` 的输出文件打开失败时，初始化函数没有继续读取 `/dev/misc_etc` 出厂记录，却返回成功。此时初始化标志为 0，RAM 内身份缓存等于固件编译时预置值，前五项都与 NOR 内真实出厂记录不同。具体文件打开错误原因尚未确认。

用户授权后，每轮只在 DID（0x34000844）和 key（0x34000870）的两个 32 字节 RAM 缓冲区写入真实出厂值，均读回验证。没有写 Flash、修改代码或初始化标志，也没有暂停／复位 CPU 或调用目标函数。第一轮后参数丢失；第二轮写入后日志出现 `login ack, code=0` 和 `cloud_connected`，随后业务返回 `device unbind`。第三轮用户完成联网，首次授权提示登录失败，界面按钮重试后配网与授权成功。授权失败对应日志没有保留下来，因此 BLE 广播与云端 DID 不一致仍是未确认假设。

随后只读检查显示，固件已自行加载 SN、Wi-Fi MAC、蓝牙 MAC、DID 和 key 五项真实出厂值，初始化标志为 1。

更新前，用户完全断开面板和 nanoDAP USB 电源约 10 秒后重新上电。coldboot06 未进行任何 RAM 修改，初始化标志仍为 1，前五项身份值均等于真实出厂记录，数字 DID 缓存及蓝牙 mesh DID 字符串也与真实出厂 DID 一致。蓝牙 mesh 字符串是否是手机发现设备时使用的字段尚未定位。冷启动日志于 21:22:43 收到 `sync ack`，用户确认自动在线且控制正常，断电后的功能验证通过。

用户报告官方 OTA 提供 1.50.10。断电后的身份、云通信及正常控制检查均通过，可从米家官方 OTA 升级，再检查更新后的启动、在线和控制；当前还未更新。原 16 MiB NOR 备份已保留，但它不包含 MMC 上的可写 `/data`。已保存成功状态与各轮只读证据，报告不包含身份或密钥的实际值。

主要证据：`current-diagnosis.json`、`wifi/ram-identity-test-round02-result.json`、`logs/identity-test-02-start/post-write-report.md`、`wifi/pairing-success05.json`、`wifi/coldboot06-verification.json`。
