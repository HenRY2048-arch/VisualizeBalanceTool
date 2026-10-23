# VisualizeBalanceTool

一个运行在 Windows 系统托盘里的余额监控工具：定时查询 DeepSeek 账户余额，并在
Codex CLI 每一轮输出结束时给出提示。

项目使用 WSL2 开发、Windows 打包。余额查询结果同时体现在托盘提示文字和托盘图标上，
任务完成提示通过 Codex CLI 的 `notify` 钩子触发。

## 功能特性

- 余额监控：默认每 120 秒查询一次 DeepSeek 余额接口，托盘悬停可看到完整余额、
  是否可用、赠送金额和充值金额。
- 托盘余额徽标：托盘图标是一块黑色矩形，上面叠加半透明淡蓝色水位和余额数字。
  - 余额小于 100 时显示整数部分，最多两位数字。
  - 余额大于等于 100 时显示为 `xH`，例如 379 显示为 `3H`，超过 999 时封顶为 `9H`。
  - 数字在水位之上绘制，透明度不影响数字颜色的辨识。
- 水位规则：水位表示当前格子内的填充比例。
  - 格子单位可在设置中修改，单位为元，必须是正整数，默认 1 元。
  - 余额正好落在格线上时视为满水，因此每一格开始时水位会重新充盈。
  - 默认单位下：10.00 为满水，10.20 为 20%，9.80 为 80%，9.00 为满水。
  - 单位改为 10 时：379 为 90%，370 为满水。
- 显示方式：可选择「数字 + 水位」「仅数字」「仅水位」三种模式。
- 颜色分段：数字颜色支持自定义分段，不再是固定的三段。
  - 余额小于 100 时按小数零头 0 到 1 分段，最多 10 段，最细粒度约为 1 元。
  - 余额大于等于 100 时按绝对金额分段，最多 20 段，最细粒度约为 5 元。
  - 每一段的起始值和颜色都可以在设置中修改，颜色通过色盘自由选择。
  - 余额正好是整数时使用单独的整数颜色（默认白色）。
- 低余额告警：余额低于告警阈值时，托盘徽标出现红色描边并闪烁，同时弹出提示窗、
  播放提示音。
- 任务完成提示：通过 Codex CLI 的 `notify` 钩子，在每一轮 AI 输出结束时触发。
- 提示控制：可分别开关托盘闪烁、任务完成提示窗和提示音，并可设置闪烁持续秒数。
- 设置界面：通过托盘右键菜单打开，包含「基本」「托盘徽标」「通知」三个标签页。
- 安装与卸载：提供 Inno Setup 安装包，创建快捷方式和卸载入口。
- 多提供商：可按统一接口扩展新的提供商。

## 运行环境

- 建议Windows 10 或 Windows 11。
- Python 3.8 及以上，推荐 3.11 或 3.12。Pillow 10 及以上和 PyInstaller 6 及以上
  都要求 Python 3.8 及以上。
- 如需打包安装包，需要安装 Inno Setup 6。
- 任务完成提示需要在 WSL2 中使用 Codex CLI。

## 快速开始

### 安装依赖

```powershell
pip install -r requirements.txt
```

注意：请使用实际要打包的那一个 Python 解释器安装依赖。如果机器上同时存在多个
Python 版本，`py -3` 可能选到较旧的版本，建议直接用 `python` 或显式指定版本。

### 配置 API Key

方式一：运行程序后，右键托盘图标选择「设置…」，在「基本」页填写 API Key。

方式二：使用环境变量作为兜底配置。

```powershell
setx DEEPSEEK_API_KEY "sk-xxxxxxxx"
```

### 以开发模式运行

```powershell
python run.py
```

## 构建与打包

### 从 WSL2 同步到 Windows 本地磁盘

项目在 WSL2 中开发时，不建议直接在 `\\wsl$\...` 这类网络路径下执行 pip 或
PyInstaller，应先同步到本地磁盘再构建。

```bash
bash scripts/sync_to_windows.sh
```

默认同步到 `/mnt/d/visualizeBalance`，也可以指定其他目录：

```bash
bash scripts/sync_to_windows.sh /mnt/e/visualizeBalance
```

同步脚本会跳过 `.git`、`__pycache__`、`dist`、`build`、`*.spec` 和
`scripts/Output`，并拒绝同步到盘符根目录。目标目录已存在但不像本项目时会中止，
确认无误后可加 `--force` 参数。

### 冒烟测试

```powershell
cd D:\visualizeBalance
python scripts\smoke_test.py
```

测试覆盖余额徽标的文字、颜色和水位规则，图标渲染，信号到通知再到图标闪烁的完整链路。
以及 Codex 钩子的安装逻辑。缺少依赖时会自动打桩，纯 Linux 或 WSL 环境也能运行。
在Powershell中，冒烟测试最后一项可能skip，是正常现象，无伤大雅。

### 一键构建

```powershell
powershell -ExecutionPolicy Bypass -File scripts\rebuild.ps1
```

脚本会依次完成：查找可用的 Python、安装依赖、使用 PyInstaller 构建可执行文件、
查找 Inno Setup 并编译安装包。

可选参数：

- `-SkipDeps`：跳过依赖安装。
- `-SkipInstaller`：只构建可执行文件，不生成安装包。

### 分步构建

先生成可执行文件：

```powershell
python scripts\build.py
```

输出文件为 `dist\VisualizeBalance.exe`。

再编译安装包，需要先安装 Inno Setup 6：

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" scripts\build.iss
```

输出文件为 `scripts\Output\VisualizeBalance-Setup.exe`。

### 创建桌面快捷方式

```powershell
powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1
```

## Codex 任务完成钩子

### 安装

```bash
bash scripts/install_wsl_hook.sh
```

安装脚本会完成以下操作：

1. 把通知脚本安装到 `~/.visualize_balance/codex_notify.sh`。
2. 在 `~/.codex/config.toml` 中写入 `notify` 配置，原配置备份为
   `config.toml.vb_bak`。
3. 删除 `~/.bashrc` 和 `~/.zshrc` 中旧版本的 shell 钩子，备份为 `*.vb_bak`。

写入的配置形如：

```toml
notify = ["bash", "/home/<用户名>/.visualize_balance/codex_notify.sh"]
```

`notify` 是顶层配置项，必须写在第一个 `[表名]` 之前，否则会被解析进某张表里。
安装脚本会自动处理插入位置。

### 触发时机

Codex CLI 会在每一轮 AI 输出结束时调用该脚本，并把一个 JSON 作为参数传入，
其中包含事件类型、会话编号、回合编号、工作目录和最后一条助手消息。

部分 Codex 版本在一轮开始时也会回调一次。为避免误报，脚本设置了以下判断条件：

1. 事件类型必须是 `agent-turn-complete`，其他事件直接忽略。
2. `last-assistant-message` 必须存在且非空，否则说明这一轮还没有真正产出内容。
3. 同一个 `turn-id` 只通知一次，避免同一轮重复触发。

脚本不会解析消息内容，也不会修改任何 Codex 状态，出现任何异常都会正常退出，
不影响 Codex 本身。

### 排查

每次调用都会写入 `~/.visualize_balance/notify.log`，保留最近 200 行，包含调用时间
和完整 JSON：

```bash
tail -n 20 ~/.visualize_balance/notify.log
```

脚本写出信号文件后，Windows 端的程序每隔一个信号轮询周期读取一次，读取成功即删除
该文件，并触发提示音、提示窗和图标闪烁。默认轮询周期为 2 秒，因此提示最多延迟
约 2 秒。

可选环境变量：

- `VB_SIGNAL_DIR`：自定义信号目录。
- `CODEX_HOME`：自定义 Codex 配置目录，默认 `~/.codex`。

## 托盘徽标说明

### 文字

| 余额范围 | 显示内容 | 示例 |
| --- | --- | --- |
| 小于 100 | 整数部分 | 20.43 显示为 20 |
| 100 到 999 | 百位数字加 H | 379 显示为 3H |
| 大于等于 1000 | 封顶为 9H | 1234 显示为 9H |

### 水位

水位表示当前格子内的填充比例，格子单位由 `badge_water_unit` 决定。余额正好落在
格线上时视为满水，开始新的一格后水位重新充盈。

### 颜色

数字颜色由一组分段决定。每一段包含一个起始值和一个颜色，取值落入“起始值不大于
当前值”的最后一段。段数上限为：十位级 10 段，百元级 20 段。

默认分段如下：

| 条件 | 颜色 |
| --- | --- |
| 余额小于 100 且为整数 | 白色 |
| 零头小于 0.25 | 红色 |
| 零头在 0.25 到 0.50 之间 | 橙色 |
| 零头大于等于 0.50 | 草绿 |
| 余额大于等于 100 且小于 320 | 红色 |
| 余额在 320 到 360 之间 | 橙色 |
| 余额大于等于 360 | 草绿 |

设置界面中可以增删分段、修改每一段的起始值，并点击色块通过色盘选择任意颜色。
分段会自动按起始值排序；如果第一段的起始值大于 0，保存时会自动补一段从 0 开始、
颜色与第一段相同的分段，保证所有取值都有颜色。

## 设置项说明

设置窗口通过托盘右键菜单的「设置…」打开，分为三个标签页。

### 基本

| 设置项 | 说明 |
| --- | --- |
| API 提供商 | 选择 DeepSeek 或 OpenAI |
| API Key | 访问余额接口所需的密钥 |
| 告警阈值 | 余额低于该值时触发低余额告警 |
| 轮询间隔 | 余额查询间隔，单位为秒，不能小于 10 |
| 启用提示音 | 控制是否播放提示音 |
| 开机自动启动 | 控制是否写入开机启动项 |

### 托盘徽标

| 设置项 | 说明 |
| --- | --- |
| 显示方式 | 数字加水位、仅数字、仅水位 |
| 水位格单位 | 单位为元，必须是正整数 |
| 整数余额颜色 | 余额正好是整数时使用的颜色，点击色块从色盘选择 |
| 颜色分段 | 切换十位级（按零头，最多 10 段）与百元级（按绝对金额，最多 20 段） |
| 每一段的起始值 | 该段开始生效的数值，十位级取 0 到 1，百元级取绝对金额 |
| 每一段的颜色 | 点击色块打开色盘选择，支持任意 RGB 颜色 |

### 通知

| 设置项 | 说明 |
| --- | --- |
| 任务完成时闪烁托盘图标 | 关闭后仍然提示，但徽标不再出现红色描边闪烁 |
| 闪烁时长 | 单位为秒，填 0 表示不闪烁 |
| 任务完成时弹出提示窗 | 控制是否发送 Windows Toast 通知 |

## 配置文件

配置保存在 `%APPDATA%\VisualizeBalance\config.json`，完整字段如下：

```json
{
  "provider": "deepseek",
  "api_key": "sk-xxxxxxxx",
  "alert_threshold": 1.0,
  "poll_interval": 120,
  "signal_poll_interval": 2,
  "flash_interval": 500,
  "flash_timeout": 30000,
  "flash_enabled": true,
  "task_toast_enabled": true,
  "badge_integer_color": "#FFFFFF",
  "badge_bands": [
    {"at": 0.0, "color": "#FF0000"},
    {"at": 0.25, "color": "#FFA500"},
    {"at": 0.5, "color": "#7CFC00"}
  ],
  "badge_hundreds_bands": [
    {"at": 0.0, "color": "#FF0000"},
    {"at": 320.0, "color": "#FFA500"},
    {"at": 360.0, "color": "#7CFC00"}
  ],
  "badge_display_mode": "both",
  "badge_water_unit": 1,
  "sound_enabled": true,
  "auto_start": false
}
```

各项含义：

| 字段 | 含义 |
| --- | --- |
| `flash_timeout` | 闪烁总时长，单位为毫秒 |
| `flash_enabled` | 是否允许闪烁 |
| `task_toast_enabled` | 是否弹出任务完成提示窗 |
| `badge_display_mode` | `both`、`number` 或 `water` |
| `badge_water_unit` | 水位格单位，正整数 |
| `badge_integer_color` | 整数余额的颜色，格式为 `#RRGGBB` |
| `badge_bands` | 十位级颜色分段，最多 10 段 |
| `badge_hundreds_bands` | 百元级颜色分段，最多 20 段 |

配置文件可以被手工编辑。加载时会自动校验：如果分段格式非法、显示方式无法识别、
整数颜色格式错误或水位格单位不是正整数，相关配置会回退到默认值。旧版本
使用的四个阈值键（`badge_green_at`、`badge_red_below`、
`badge_hundreds_green_at`、`badge_hundreds_red_below`）会在加载时自动转换为三段
色带，不需要手动迁移。

也可以用环境变量覆盖部分配置，具体映射关系见 `src/config.py`。

## 项目结构

```
visualizeBalance/
├── run.py                      入口文件
├── requirements.txt            Python 依赖
├── src/
│   ├── __init__.py             版本号
│   ├── main.py                 日志初始化与入口
│   ├── app.py                  应用主控与后台循环
│   ├── config.py               配置文件读写与环境变量兜底
│   ├── settings.py             tkinter 设置窗口
│   ├── notification.py         提示音与 Toast 通知
│   ├── signal_monitor.py       信号文件监听
│   ├── tray.py                 托盘图标管理
│   ├── icons.py                徽标与图标绘制
│   └── providers/
│       ├── __init__.py         提供商注册表
│       ├── base.py             提供商抽象基类
│       ├── deepseek.py         DeepSeek 实现
│       └── openai.py           OpenAI 实现
├── assets/                     图标与提示音资源
├── scripts/
│   ├── build.py                PyInstaller 构建脚本
│   ├── build.iss               Inno Setup 安装包脚本
│   ├── rebuild.ps1             Windows 一键构建
│   ├── create_shortcut.ps1     桌面快捷方式创建脚本
│   ├── codex_notify.sh         Codex 回合结束钩子
│   ├── install_wsl_hook.sh     钩子安装脚本
│   ├── sync_to_windows.sh      WSL 到 Windows 同步脚本
│   ├── init_repo.sh            Git 仓库初始化脚本
│   └── smoke_test.py           冒烟测试
└── dist/                       构建产物目录
```

## 卸载与清理

### 卸载程序

打开「设置」「应用」「已安装的应用」，找到 VisualizeBalance 后选择卸载；也可以直接
运行安装目录中的 `unins000.exe`。

### 清理用户数据

卸载程序不会删除以下用户数据，需要手动清理：

```
%APPDATA%\VisualizeBalance\                  配置文件，含 API Key
%USERPROFILE%\.visualize_balance\            信号目录与通知脚本
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\VisualizeBalance.lnk
HKCU\Software\Microsoft\Windows\CurrentVersion\Run 下的 VisualizeBalance 项
```

### 清理 WSL 钩子

```bash
rm -f ~/.visualize_balance/codex_notify.sh
```

然后删除 `~/.codex/config.toml` 中的 `notify` 一行。安装脚本会自动备份原配置，
也可以直接从 `~/.codex/config.toml.vb_bak` 恢复。

## 常见问题

### 托盘没有出现图标

检查任务管理器中是否存在 `VisualizeBalance.exe`，并确认
`%APPDATA%\VisualizeBalance\config.json` 中的 API Key 是否正确。

### 余额没有更新

将鼠标悬停在托盘图标上查看提示文字，或右键选择「立即刷新余额」。

### AI 回答完成后没有提示

依次检查以下内容：

```bash
grep '^notify' ~/.codex/config.toml
tail -n 20 ~/.visualize_balance/notify.log
ls -l /mnt/c/Users/<Windows用户名>/.visualize_balance/signal
```

确认当前使用的是新启动的 Codex 会话，并且 `notify.log` 中出现了
`agent-turn-complete` 事件。

### 刚开始回答就提示完成

说明当前 Codex 版本在回合开始时也回调了 `notify`。新版本的钩子脚本会检查
`last-assistant-message` 是否为空，并校验 `turn-id` 是否重复。如果问题仍然存在，
请查看 `notify.log` 中提前那次回调的完整内容。

### 安装包编译失败

安装包编译前必须先成功生成 `dist\VisualizeBalance.exe`，否则 Inno Setup 会报告
找不到源文件。另外请确认 Inno Setup 的实际安装路径，5 和 6 的默认目录不同。

## 扩展新的提供商

1. 在 `src/providers/` 下新建提供商模块。
2. 继承 `BaseProvider` 并实现 `parse_response`，可参考 `deepseek.py`。
3. 使用 `@register` 装饰器注册。
4. 在 `src/providers/__init__.py` 中导入该模块。
5. 在 `src/settings.py` 的提供商下拉列表中加入名称。

## 谨慎保管您的Windows文件，本工具在设置页面中已对api-key做脱敏处理

## 许可证

本项目使用 MIT 许可证，详见 [LICENSE](LICENSE)。
