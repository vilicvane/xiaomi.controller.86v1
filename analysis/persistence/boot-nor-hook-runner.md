# 固定范围 BOOT hook 安装与恢复

`diagnostics/boot-nor-hook-runner.cfg` 为新文件，仅定义函数；载入不会连接设备、复位或运行代码。公开操作为 `bnh_run_hook capture_dir install|restore remove_fpb_command`。必须先在同一调试进程完成独立只读 runner，并处于新鲜原始 BOOT 停点、A7/WF/BT CPU 被保持复位、原生 AON 看门狗已验证停止的状态。根代理拥有所有硬件动作和最终 GLOBAL reset。

安装先确认 `150000` 与 `824000` 两个完整 4 KiB sector 都等于原始 1.50.10 备份，再测真实 SR1/SR2，保存实际 BP/QE。BP 非零时仅修改 mask `407c`，BP 零时跳过状态写。先向原本全 FF 的 `824400` 页 program 256 B：32 B 已审查 stub 加 224 B FF，不擦除 payload sector；验证整个 payload 4 KiB 正确后，才擦除 entry sector `150000` 并写其 16 个固定 patched pages。

恢复接受每个 sector 精确等于 original 或 patched 的已知 baseline。先擦除并写回 entry 的 16 个原始 pages，验证整个 entry；随后擦除 payload sector，并只写回其 4 个非 FF 原始 pages，再验证完整 payload。未知半写 sector 会拒绝，保留暂停和证据，由根代理审核独立固定恢复动作。

最后检查真实状态寄存器：WIP/WEL 清零，BP、QE 以及全部其他稳定位与最初测量一致；对两个 sector 分别进行 I/D cache 范围失效，并再次比较两份完整 4 KiB。单次调用复制已审查 BOOT padding 执行器的 1 KiB 临时栈尾、所有整数/core/debug 状态和 HAL/controller 检查；增加已证明初始化的两字 `20003ad0/3ad4` 的独立 8 B before/after 等值检查。SP/limit 不变，payload 与 HAL 最大 232 B 栈不重叠。每次调用都要求看门狗 CTRL 为零；host deadline 为 erase 5000 ms、program/BP 1000 ms、读状态 250 ms。

失败不自动重试、继续下一页、擦除、恢复保护或 resume。无法确认原生返回、SPI post、reset/fault/security 状态时，不回放原来的 core/RAM 状态；保持当前 halt。每次原生调用的 CPU-run 提交前已记录 Flash 可能改变，传输错误不能被当作没有执行。

安装总实际补丁为 entry 4 B 加 payload 28 B，既有 header、启动 RW、build-info 不变。独立 byte/ABI 审查见 `boot-hook-install-independent-review.json`：stub 使用 8 B 临时栈并恢复 r0/r1、flags、LR，尾跳回原始目标；没有已知额外 checksum 更新要求，但不能据此推断所有 ROM/eFuse 安全校验都不存在。槽位位于现有主应用 partition，并非已知 linker 永久保留位置；OTA 可以替换本实验。

成功后仍停在原始 BOOT，由根代理先清 DCRDR marker 再 GLOBAL reset。冷启动后需要通过 MEM-AP 在任何 DCRSR/core-register transfer 前查看 DCRDR，避免调试器覆盖 marker。离线模拟仅验证流程和拒绝行为，实际安装与全断电后恢复仍由根代理验证。

执行 kernel 固定来自 `boot-nor-hook-kernel-source-68b1b7fb.cfg`（已验证 padding SHA `68b1b7fb778cd507bee20837979f2529af4ed31bf369437dc45ebf8917d4655c`）。看门狗 CTRL 检查覆盖源码入口、最后 A7 gate 之后且 CPU-run 提交之前、以及读取后；不是只在操作开始检查一次。Host poll 按 `timeout/5+2` 限定次数并间隔 5 ms，erase 为 1002 次上限，不再使用旧 150 次紧循环。

若安装的 entry sector 半写，正常 `restore` 会拒绝未知 baseline。根代理的手工恢复路线是：保存当前两 sector 的完整证据，用独立 BOOT 恢复入口重新到达原始停点，停止看门狗，并重新完成独立 reader。根据实际 SR1/SR2，若 BP 非零则调用固定 `unprotect` 并确认状态；然后只调用 `bnh_write_sector recovery_dir restore-entry $bhi_entry_original_words $original_bp callback`，该 helper 只允许 entry 地址 `28150000`、长度 4 KiB、16 个固定原始 pages，不能接受当前未知内容作为写入源，也不会触及 payload。调用 `bnh_verify_sector recovery_dir entry $bhi_entry_original_words` 验证完整原始 4 KiB。之后重新测状态，按实际原 BP 恢复保护、验证 QE/全部稳定位，调用固定 `invalidate-entry-i/d`，再次验证 entry。每步需根代理显式监督；任一步原生调用未关闭、reset/fault 或检查失败，都停止，不触发自动恢复写。

这条手工 helper 路线没有新增 public mode 或任意地址接口，并要求新鲜 BOOT/reader/controller 证据，不能从未关闭的旧调用直接回放上下文。已知 entry 原始而 payload 补丁的组合可进入普通 `restore`，或由根代理在重新核对 payload 所属和状态后监督固定 `restore-payload` helper；BOOT/recovery/A7/factory 仍不在 admission 范围。

手工路线的日志 setup 也必须显式完成：选择不存在的 `recovery_dir`，创建它并设置 `bnh_hook_result` 为 `open recovery_dir/supervised-entry-restore.txt w`；`bnh_status_stage`、`bnh_write_sector` 的跳页日志以及 `bnh_verify_sector` 使用这个外层 channel。每个 `bnh_execute_call` 自己保存和关闭独立 stage channel。步骤由外层 catch 逐次监督，失败停止；根代理诊断完成后关闭外层 channel，不无条件 GLOBAL。`bnh_write_sector` 在 erase 前还要求 prefix 与传入的完整 sector words 等于对应固定原始/补丁常量，拒绝任意源数据导致错误跳页。
