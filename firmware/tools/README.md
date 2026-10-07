# 离线发布材料

`release.ts` 用 Node 24 的原生 TypeScript strip-types 运行，不需要 npm 依赖。
它只准备、检查及绑定独立审查材料，**没有设备连接、live read 或 execute 命令**。
当前离线候选采用本机 1.50.10 的独立四页方案：主 3432B、辅助 444B 的既有边界不变，
网络段限 `0x3804d000..0x3804dff0`（4080B）。第四页属于单独审查的 `uorb_unit_test`，
不能凭空间空闲或旧三页实验认定可写。任何段溢出立即拒绝。

## 流程

在仓库根目录运行：

```powershell
node firmware/tools/release.ts baseline
node --test firmware/tools/release.test.ts
```

`baseline` 检查已冻结 image drawer 的精确 93 项输入、递归的 317 项历史集合、完整三页
布局、168B caller，以及从完整 stock backup 提取的精确第四页。它不生成或改写旧文件，
也不启动 OpenOCD。原冻结目录的 SHA 固定为
`fa99d95a98b3abd4f3e76ce304a4d6a12623f50338d0240a6aba4b91f0a0cf61`。

维护源码通过 `firmware/build.sh` 编译到 `build/panel/`。构建器用 `build-record.ts` 在编译
前记录源文件/工具链，在成功后核对输入未变化并记录 ELF/BIN/map SHA；只有
`build-inputs.json` 的 `completed: true` 才能 prepare。缺材料、旧 BIN 与新源码错配、
容器溢出、可写 ELF 段或入口变化均先拒绝。
实际使用的 compiler headers 在构建前后保持相同，完整副本保存为
`build/panel/compiler-headers/`；release 要求非空 `headers`/`headerCopies` hash 多重集
相同，并逐项把副本纳入私有 snapshot。不会把 Clang 标准头文件提交 Git。

```powershell
node firmware/tools/release.ts prepare my-first-candidate build/reviews/storage-ownership-review.json
node firmware/tools/release.ts verify my-first-candidate
```

名称须唯一，已有目录绝不覆盖。材料写入私有 `build/releases/<name>/`：

| 路径 | 内容 |
| --- | --- |
| `candidate.json` | schema2 四页布局、来源、snapshot SHA、固定顺序，状态 candidate |
| `snapshot/firmware/` | 可维护源码、头文件、端口链接/入口、构建记录器、release 和单独审查的 hardware 工具快照 |
| `snapshot/build/panel/` | config、完成的 build 记录、三段 BIN、ELF、map |
| `snapshot/reviews/storage-ownership.json` | 第四页明确已审核的 ownership 材料 |
| `snapshot/firmware/tests/` | 当前维护版 ARM/model/host 测试源码；作为审查输入，不冒充编译依赖或已通过结果 |
| `ownership-inputs/` | ownership review 引用的逐项来源快照 |
| `workspace/` | 原冻结依赖的原字节副本、新四页及私有 writer/stage/session/mock |

当前 image drawer 的 patched 三页与精确 stock 第四页共同成为新 release 的
**original**。新代码只覆盖各容器内自己的字节；网络页头 4B、尾 12B 以及所有其他
尾部字节保留。入口页仅将 `+0xc3c` 的 `uorb_unit_test` 函数指针从 `0x3804cf3d`
改成禁用 stub `0x3804b109`。restore 返回精确 image drawer 三页和 stock 网络页；
再回更早版本必须使用原版本自己的链。

Tcl writer、完整 stages 的 foreach/proc、outer 两 session 与 Python mock 从冻结原文
生成到私有 workspace。168B caller 和原 `execute_call` 原样保留；stage 白名单仅增加
同一 erase/program/cache callee 对固定第四页的入口，每页仍是 16 个 256B program
单元及完整 4KiB 读回。四页基线必须在首次 mutation 前一起匹配；install 固定
net→aux→code→entry，restore 固定 entry→code→aux→net，阶段之间验证完整页及状态。
A7/WF/BT 持续保持复位；四页最终字节、保护/QE/WIP、I/D cache、native return/context
都闭合后才允许完成 gate。session 前有 candidate gate；设备入口须由另行审查的
`hardware.ts` 验证完整 freeze 后开放。本工具自身不执行它，也不能直接运行 candidate
session。新 writer 必须另做独立审查，旧三页通过结果不能替代。

Python 仅用于私有生成的独立 mock，TypeScript 管理准备和冻结；没有新增 Python 业务
生成器。mock 的 rollback fixture 改为 image drawer 加 stock net，保留 70 个原有故障
场景并增加 23 个第四页场景。旧 case 标签中的 fast-tap/image 命名属于历史名称，私有
fixture 的明确含义以四页原始/补丁数据为准。OpenOCD exe 沿用冻结值，两份 DLL 和
CMSIS-DAP 接口配置作为新的 snapshot 输入绑定，不能声称它们属于旧 93 项冻结。
Windows xPack 的原配置位于 `tools/xpack-openocd-0.12.0-7/openocd/scripts/interface/cmsis-dap.cfg`；
release 保留这个路径的原字节副本，同时为 `-s diagnostics` 提供
`diagnostics/interface/cmsis-dap.cfg`。两个副本必须 hash/字节完全相同。离线 mock 会
禁止 adapter/init，因此 writer mock 通过本身不能证明设备连接所需包装依赖完整。
所有包含原厂字节的 release 材料都保持 ignored，不能提交 Git。

## 运行私有 writer mock

在 Windows PowerShell 切入该 release 的 `workspace/`：

```powershell
python -X utf8 analysis/persistence/test_panel_maintained_runner_offline.py
```

mock 使用复制的 exe/Jim 引擎，harness 屏蔽 init、adapter、reset、halt、resume 等真实
硬件入口，只模拟读取/调用，不连设备。输出留在独立 run 目录，不更新旧研究结果。
新 payload 的完整结果须单独检查，不能沿用原型的 70/70 标签。第四页验证包括原始/
补丁混合拒绝，erase/program/native error/timeout，完整读回错误，QE/WIP/保护变化，
closed-return/posted transport，reset/fault，cache 闭合，错误来源/页号/任意 stage 拒绝，
以及安装/回滚依赖顺序。离线通过不证明实机时序或掉电恢复。

## 第四页 ownership 输入

`prepare` 必须显式传入已经完成的 `storage-ownership-review` JSON；缺省拒绝。字段为
`role`、`passed: true`、`firmware: "1.50.10"`、`baseline_freeze_sha256`、
`stock_backup_sha256`、`net_page_sha256`、`net_offset`、`runtime_start`、
`runtime_end_exclusive`、`builtin_entry_offset`、`builtin_original_word`、
`builtin_disabled_word`，以及非空 `evidence_sha256`。地址接受十六进制字符串或数字，
但必须精确匹配上述布局。

stock backup SHA 是 `777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b`；
net 页 SHA 是 `76a994fbd3892960f43db969b4744fbb726d23feac5c24df86041398ee5d299d`。
`evidence_sha256` 必须包含完整 backup 路径/上述 hash，并绑定实际 ownership 审查来源。
工具验证已提供审查材料与字节，不会自动把扫描结果标成 approved。

## 独立证据与 freeze

准备和验证不会把 candidate 自动标成已审核。先独立完成 storage ownership review、
program review、writer review、当前 actual ARM ELF model 和当前 writer mock。
`freeze` 接收一个引用表：

```json
{
  "storage-ownership-review": { "path": "build/reviews/storage-final.json", "sha256": "..." },
  "program-review": { "path": "build/reviews/program.json", "sha256": "..." },
  "writer-review": { "path": "build/reviews/writer.json", "sha256": "..." },
  "arm-model": { "path": "build/reviews/arm.json", "sha256": "..." },
  "writer-mock": { "path": "build/reviews/mock.json", "sha256": "..." }
}
```

每份证据必须是不同的 JSON artifact，并明确包含 `role`、`passed: true`、
`release_manifest_sha256`（candidate.json 完整 hash）、`reviewed_inputs`（candidate
全部 inputs 的逐项 hash）。ARM artifact 另须 `scope: "actual-arm"`、正数 `check_count`
和当前 `elf_sha256`；mock artifact 须 `all_passed: true` 及 93 个全通过、名称不重复、
精确覆盖继承和新增场景的 `cases`（`case`/`passed`）。storage artifact 另须
`ownership_sha256` 绑定 candidate 的 ownership JSON。不能给旧 result 补字段冒充审查。

```powershell
node firmware/tools/release.ts freeze my-first-candidate build/reviews/evidence.json
node firmware/tools/release.ts verify my-first-candidate
```

freeze 把五份 evidence 复制到私有快照，再写不可覆盖的 `freeze.json`。之后改动
canonical `firmware/src/` 不影响这个 release；verify 仍核对冻结旧基线、snapshot、
完整页重构及证据覆盖。freeze 记录已经完成的审查，不提供硬件授权，也不声称实机
安装、显示、触摸、HTTP、米家或完整断电已经验证。
