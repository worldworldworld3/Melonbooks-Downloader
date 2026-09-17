"""Offline HTML interaction test with explicitly labeled sample books."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'downloader'), str(ROOT / 'decoder')]
import base64
import json
import sys
import time
from desktop import HERE, Bridge, webview

bridge=Bridge()
bridge._state.update(logged_in=True,account='界面测试',downloaded=['0'],message='界面测试 · 示例数据，不是真实已购书架。')
for i in range(8):
    color=['#72927b','#859cb2','#be9e7e','#a9a890'][i%4]
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="400"><rect width="300" height="400" fill="{color}"/><circle cx="240" cy="120" r="95" fill="#fff" opacity=".18"/><path d="M0 350L160 160L300 320V400H0" fill="#fff" opacity=".25"/><text x="30" y="58" fill="white" font-size="14">SAMPLE BOOK / {i+1:02}</text><text x="30" y="300" fill="white" font-size="40">LIBRARY</text><text x="30" y="335" fill="white" font-size="16">INTERFACE PREVIEW</text></svg>'
    bridge._books.append(dict(id=str(i),title=['春日旅行手记','星空下的图书馆','海边的来信','午后的速写集'][i%4]+f' · 示例 {i+1}',circle='青叶社' if i%2==0 else '纸上工作室',author='作者甲' if i%2==0 else '作者乙',thumbnail='data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode(),format='ZIPJPEG',size=12345678+i*456789,date='2026-09-15',adult=False))
bridge._books[-1]['title']='<img src=x onerror="window.INJECTED=1">'
bridge._books[-1]['thumbnail']=''
html=(HERE/'frontend/index.html').read_text(encoding='utf-8').replace('/* APP_CSS */',(HERE/'frontend/style.css').read_text(encoding='utf-8')).replace('/* APP_JS */',(HERE/'frontend/app.js').read_text(encoding='utf-8'))
w=webview.create_window('书架界面测试 · 示例数据',html=html,js_api=bridge,width=1200,height=850)
bridge._window=w
results=[]
def run():
    try:
        for _ in range(40):
            time.sleep(.25)
            if w.evaluate_js('document.querySelectorAll(".book").length===8'): break
        for _ in range(30):
            if w.evaluate_js('document.querySelector(".book img")?.naturalWidth > 0'): break
            time.sleep(.1)
        def check(js):
            assert w.evaluate_js(js),js
        check('document.querySelectorAll(".book").length===8')
        check('!window.INJECTED && document.querySelectorAll(".book-title img").length===0')
        check('document.querySelector(".book img").complete && document.querySelector(".book img").naturalWidth > 0')
        check('document.querySelector(".cover-placeholder")!==null')
        check('document.getElementById("search").value="青叶社";document.getElementById("search").dispatchEvent(new Event("input"));document.querySelectorAll(".book").length===4')
        check('document.getElementById("selectAll").click();document.getElementById("selectedCount").textContent.includes("3")')
        check('document.getElementById("listView").click();document.getElementById("shelf").classList.contains("list")')
        check('document.querySelector(".book-title").click();document.getElementById("detail").open && document.getElementById("detailBody").textContent.includes("作者甲")')
        check('document.getElementById("closeDetail").click();!document.getElementById("detail").open')
        check('document.getElementById("search").value="";document.getElementById("search").dispatchEvent(new Event("input"));document.querySelector("[data-tab=circle]").click();document.querySelectorAll("#groups button").length===3')
        check('document.querySelector(".brand strong").textContent==="Melonbooks Downloader" && !document.querySelector(".favorite") && !document.querySelector("[data-filter=favorites]") && !document.getElementById("detailFavorite")')

        check('document.querySelector(".book input").disabled && !document.querySelector(".book input").checked && document.querySelector(".book .downloaded")!==null')
        check('document.querySelector(".book-title").click();document.getElementById("detailSelect").disabled')
        w.evaluate_js('document.getElementById("closeDetail").click()')
        bridge._update(downloaded=['0','2'])
        time.sleep(1)
        check('document.getElementById("selectedCount").textContent.includes("2")')
        check('[...document.querySelectorAll(".is-downloaded input")].every(n=>n.disabled&&!n.checked)')
        bridge._update(downloaded=[str(i) for i in range(8)])
        time.sleep(1)
        check('document.getElementById("selectAll").disabled && document.getElementById("download").disabled && document.getElementById("selectedCount").textContent.includes("0")')
        bridge._update(downloaded=[])
        time.sleep(1)
        check('[...document.querySelectorAll(".book input")].every(n=>!n.disabled)')
        w.evaluate_js('document.querySelector("[data-filter=all]").click();document.querySelector("[data-tab=all]").click();document.getElementById("gridView").click();document.getElementById("clear").click();')
        check('document.getElementById("clear").textContent==="取消全部选择" && document.getElementById("clear").disabled && !document.getElementById("clear").hidden')
        check('document.getElementById("selectAll").click();document.getElementById("selectedCount").textContent.includes("8")')
        check('document.getElementById("search").value="青叶社";document.getElementById("search").dispatchEvent(new Event("input"));document.querySelectorAll(".book").length===4')
        check('document.getElementById("clear").click();document.getElementById("selectedCount").textContent.includes("0") && !document.querySelector(".book input:checked")')
        check('document.getElementById("search").value="";document.getElementById("search").dispatchEvent(new Event("input"));!document.querySelector(".book input:checked") && !document.getElementById("selectAll").indeterminate && !document.getElementById("selectAll").checked')
        check('document.getElementById("emptyText").textContent==="登录 Melonbooks 账号，查看已购漫画的封面与作品信息。" && document.querySelector(".empty-icon")!==null && !document.getElementById("localEmpty") && !document.querySelector(".local-note") && !document.body.textContent.includes("你的书架，随时可取")')
        print('PASS: covers, metadata, search, selection, list, details, grouping, downloaded selection guards, branding, HTML escaping',flush=True)
        results.append(True)
        if '--hold' in sys.argv: return
    except Exception as e:
        print('FAIL:',e,flush=True)
    w.destroy()
webview.start(run,gui='edgechromium',private_mode=True)
sys.exit(0 if results else 1)
