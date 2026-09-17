# Third-party notices

The project MIT license covers the project's own contributions. Third-party software retains its original copyright and license. Melonbooks names and fixed client/protocol data are not claimed as this project's original intellectual property. No user account credentials or purchased-book license records are distributed.

License files copied from the installed dependency distributions are preserved verbatim in `licenses/`. Dependencies are installed from `requirements.txt`; the source repository does not vendor their implementation or binaries. The EXE bundles runtime dependencies and embeds this notice and `licenses/`.

| Component | Version / purpose | License evidence |
| --- | --- | --- |
| Python | 3.12 runtime | `licenses/Python-LICENSE.txt` |
| pywebview | 6.2.1 desktop WebView host | `licenses/pywebview-6.2.1.dist-info/` |
| cryptography | 50.0.1 cryptographic implementation | `licenses/cryptography-50.0.1.dist-info/`; includes Apache/BSD notices |
| cffi | 2.1.1 | `licenses/cffi-2.1.1.dist-info/` |
| clr_loader | 0.3.1 | `licenses/clr_loader-0.3.1.dist-info/` |
| pythonnet | 3.1.0 | `licenses/pythonnet-3.1.0.dist-info/` |
| bottle | 0.13.4 | `licenses/bottle-0.13.4.dist-info/` |
| pycparser | 3.0 | `licenses/pycparser-3.0.dist-info/` |
| typing_extensions | 4.16.0 | `licenses/typing_extensions-4.16.0.dist-info/` |
| proxy_tools | 0.1.0 | `licenses/proxy_tools-LICENSE.txt`; upstream BSD text, Armin Ronacher / Jonathan Tushman. Package metadata labels it MIT, while its source header and upstream license specify BSD; preserve the upstream text. |
| Microsoft WebView2 SDK | Assemblies/loader distributed by pywebview; Runtime installed separately | Microsoft SDK terms; see Microsoft-WebView2 license material in `licenses/` |
| PyInstaller and build dependencies | See `requirements-build.txt` | Corresponding directories in `licenses/`; PyInstaller bootloader exception is included in its license text |

Sources:

- https://github.com/jtushman/proxy_tools/blob/master/LICENSE.txt
- https://github.com/r0x0r/pywebview
- https://www.nuget.org/packages/Microsoft.Web.WebView2

The legacy viewer automation and bundled reader from the development workspace are not included in this source release. The independent decoder is provided with account-authorized conversion only in the application UI.
