# Melonbooks Downloader

Windows 已购漫画下载与独立转换工具。当前版本：**1.0.0**。

## 下载与运行

从本仓库的 **Releases → v1.0.0** 下载 `Melonbooks.Downloader-1.0.0-windows-x64.zip`，解压后运行 `Melonbooks Downloader.exe`。也可单独下载 EXE。

- Windows 10/11 x64。
- 需要 Microsoft Edge WebView2 Runtime；EXE 已包含 Python 及应用依赖，无需安装 Python 或蜜瓜阅读器。
- 使用自己的 Melonbooks 账号登录。首次运行默认输出到用户的 `Downloads/Melonbooks Downloader`，可在底部更换目录。

## 功能

- 官方网页登录、同步已购书架、切换账号。
- 批量选择、顺序分段下载。
- 每本下载后自动独立解码，支持的结果输出为 ZIP 或 PDF。
- 登录后批量添加或拖入本地 `.melon` / `.ebg` 文件，逐个校验当前账号授权与作品密钥，并转换通过校验的文件。

## 文件与缓存

输出目录只写转换结果。源文件和下载 JSON 保存在 `%LOCALAPPDATA%/Melonbooks Downloader/source-cache`，设置与随机设备编号保存在该应用目录。源码运行时，设置及缓存位于 `downloader/`。

缓存不会自动删除。“清除缓存”清除所有输出位置对应的应用下载缓存。

本地文件只在本机读取。账号会话及作品授权仅存于运行内存。

## 支持范围

独立解码支持 RIFF/BeBG、KEY v1、AES-128-CBC 的 ZIP/PDF。输出文件系统需支持硬链接，例如 NTFS。

本工具为独立项目，不是 Melonbooks 官方软件。

## 从源码运行

安装 Python **3.12 x64**，在仓库根目录打开 PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe downloader/app.pyw
```

## 测试

离线单元及整合测试不使用真实账号、不联网、不启动界面：

```powershell
.\.venv\Scripts\python.exe run_tests.py
```

可选界面测试使用虚拟数据，需要桌面和 WebView2：

```powershell
.\.venv\Scripts\python.exe tests/ui_smoke.py
.\.venv\Scripts\python.exe tests/ui_local_smoke.py
```

## 构建单文件 EXE

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build.ps1
```

默认使用仓库内的 `.venv`，不存在时使用 PATH 中的 `python`。也可通过 `-Python` 指定解释器，通过 `-DistPath` 指定输出位置。产物为 `dist/Melonbooks Downloader.exe`，文件属性中的产品版本为 `1.0.0`。

两个 `client_material.json` 文件是固定客户端参数，不是个人账号密钥；构建时必须保留。

可执行文件离线自测（只使用虚拟会话和临时缓存）：

```powershell
Start-Process -Wait -FilePath '.\dist\Melonbooks Downloader.exe' -ArgumentList '--smoke-test',"$PWD\smoke-result.json"
Get-Content .\smoke-result.json
```

## 许可证

项目自有代码采用 [MIT License](LICENSE)。第三方组件、版权归属和许可原文见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 [licenses/](licenses/)。
