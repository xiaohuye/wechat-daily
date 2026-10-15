# -*- coding: utf-8 -*-
"""SafeLS patch: 沙箱 iframe localStorage SecurityError 全局修复.
顺序: 先全文替换 localStorage.* 为 lsXxx(), 再插入 SafeLS 模块(内部用 LS 变量避免自替换)."""
import sys, re

src = sys.stdin.read()

# 1) 全文替换 (顺序: removeItem -> setItem -> getItem -> key -> length)
src = src.replace("localStorage.removeItem(", "lsDel(")
src = src.replace("localStorage.setItem(", "lsSet(")
src = src.replace("localStorage.getItem(", "lsGet(")
src = src.replace("localStorage.length", "lsLen()")
src = src.replace("localStorage.key(", "lsKey(")

# 2) SafeLS 模块 (锚点: const HKEY 行前插入)
SAFE_LS = """/* ---------------- 沙箱安全 localStorage (SafeLS) ----------------
   WorkBuddy 预览面板等沙箱 iframe（无 allow-same-origin）禁用 localStorage：
   访问 window.localStorage 属性即抛 SecurityError，页面一加载必炸、保存必失败。
   统一走 SafeLS：可用时直用；不可用时降级内存 Map——功能保持、数据不持久，
   并显示顶部黄条提示用户改用浏览器获得完整保存能力。 */
let _lsOK = null, LS = null;
const _mem = {};
function lsProbe(){
  if(_lsOK === null){
    try{ LS = window.localStorage; LS.setItem('__ls_probe', '1'); LS.removeItem('__ls_probe'); _lsOK = true; }
    catch(e){ _lsOK = false; }
  }
  return _lsOK;
}
function lsGet(k){ if(!lsProbe()) return (k in _mem) ? _mem[k] : null; try{ return LS.getItem(k); }catch(e){ return (k in _mem) ? _mem[k] : null; } }
function lsSet(k, v){ if(!lsProbe()){ _mem[k] = String(v); return; } try{ LS.setItem(k, v); }catch(e){ _mem[k] = String(v); } }
function lsDel(k){ if(!lsProbe()){ delete _mem[k]; return; } try{ LS.removeItem(k); }catch(e){ delete _mem[k]; } }
function lsLen(){ if(!lsProbe()) return Object.keys(_mem).length; try{ return LS.length; }catch(e){ return Object.keys(_mem).length; } }
function lsKey(i){ if(!lsProbe()) return Object.keys(_mem)[i] || null; try{ return LS.key(i); }catch(e){ return Object.keys(_mem)[i] || null; } }
/* 沙箱提示（一次性，仅环境受限时显示） */
setTimeout(function(){
  if(lsProbe() === false && document.body){
    const b = document.createElement('div');
    b.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:998;background:#a56a00;color:#fff;font:12px/1.7 sans-serif;padding:5px 12px;pointer-events:none';
    b.textContent = '⚠ 当前预览面板是沙箱环境，划线/批注/反馈可操作但不会保存。完整功能请用 Chrome/Edge 打开本地 HTML 文件使用。';
    document.body.appendChild(b);
  }
}, 600);

const HKEY = 'wxhl::';"""

anchor = "const HKEY = 'wxhl::';"
if anchor not in src:
    print("PATCH_FAIL: 锚点未找到", file=sys.stderr); sys.exit(1)
src = src.replace(anchor, SAFE_LS, 1)

# 3) 自检: 不应再有裸 localStorage 调用 (除 SafeLS 内部的 window.localStorage)
left = [l for l in src.splitlines() if re.search(r"(?<!\w)localStorage\.(?!getItem|setItem|removeItem|length|key)", l)]
print("剩余异常引用行:", len(left))
for l in left[:5]:
    print("  ", l.strip()[:80])
sys.stdout.write(src)
