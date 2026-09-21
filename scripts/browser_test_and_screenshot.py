import asyncio
import json
import subprocess
import time
import base64
import os
import httpx
import websockets

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = os.path.abspath(r".chrome_temp_profile")
ARTIFACT_DIR = r"C:\Users\Shann\.gemini\antigravity-ide\brain\1f8756bf-888e-4887-9fc4-ce27bf12a627"

async def cdp_send(ws, method, params=None, msg_id=[0]):
    msg_id[0] += 1
    req = {"id": msg_id[0], "method": method, "params": params or {}}
    await ws.send(json.dumps(req))
    while True:
        resp_raw = await ws.recv()
        resp = json.loads(resp_raw)
        if resp.get("id") == req["id"]:
            return resp.get("result", {})

async def main():
    print("Launching Chrome in headless mode with remote debugging...")
    proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        "--remote-debugging-port=9222",
        f"--user-data-dir={USER_DATA_DIR}",
        "--disable-gpu",
        "--no-sandbox",
        "--window-size=1440,950",
        "about:blank"
    ])
    
    try:
        # Wait for CDP to respond
        ws_url = None
        for _ in range(15):
            try:
                r = httpx.get("http://127.0.0.1:9222/json/version", timeout=1.0)
                if r.status_code == 200:
                    ws_url = r.json().get("webSocketDebuggerUrl")
                    break
            except Exception:
                time.sleep(0.5)
        
        if not ws_url:
            raise RuntimeError("Could not connect to Chrome DevTools port 9222")
            
        print(f"Connected to Chrome DevTools: {ws_url}")
        
        # Create a new page
        r = httpx.put("http://127.0.0.1:9222/json/new", timeout=2.0)
        target_ws_url = r.json().get("webSocketDebuggerUrl")
        
        async with websockets.connect(target_ws_url) as ws:
            id_gen = [0]
            await cdp_send(ws, "Page.enable", msg_id=id_gen)
            await cdp_send(ws, "Runtime.enable", msg_id=id_gen)
            
            # Navigate to localhost:5173
            print("Navigating to http://localhost:5173...")
            await cdp_send(ws, "Page.navigate", {"url": "http://localhost:5173"}, msg_id=id_gen)
            await asyncio.sleep(2.0)
            
            # Log in as SI Vikram Sharma by injecting token and officer profile
            print("Logging in...")
            login_js = """
            (async () => {
                const res = await fetch('http://localhost:8000/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: 'sharma@sentinel.gov.in', password: 'SentinelPass123!' })
                });
                const data = await res.json();
                if (data.access_token) {
                    localStorage.setItem('cryptotrace_sentinel_token', data.access_token);
                    localStorage.setItem('cryptotrace_sentinel_officer', JSON.stringify(data.officer));
                    window.location.reload();
                }
            })()
            """
            await cdp_send(ws, "Runtime.evaluate", {"expression": login_js, "awaitPromise": True}, msg_id=id_gen)
            await asyncio.sleep(2.5)
            
            # Switch to inspector view or open inspector
            print("Switching to Address / Tx Inspector...")
            switch_tab_js = """
            (() => {
                // Find button with text 'Address / Tx Inspector' or 'Inspector'
                const buttons = Array.from(document.querySelectorAll('button'));
                const btn = buttons.find(b => b.innerText.includes('Inspector') || b.innerText.includes('Address / Tx'));
                if (btn) {
                    btn.click();
                    return 'clicked inspector button: ' + btn.innerText;
                }
                return 'inspector button not found';
            })()
            """
            eval_res = await cdp_send(ws, "Runtime.evaluate", {"expression": switch_tab_js}, msg_id=id_gen)
            print("Tab switch:", eval_res.get("result", {}).get("value"))
            await asyncio.sleep(1.0)
            
            # Click Satoshi Genesis chip or set query
            print("Triggering search for Satoshi Genesis address...")
            search_js = """
            (() => {
                // Find chip button with Satoshi
                const buttons = Array.from(document.querySelectorAll('button'));
                const chip = buttons.find(b => b.innerText.includes('Satoshi Genesis'));
                if (chip) {
                    chip.click();
                    return 'clicked satoshi chip';
                }
                // Fallback: populate input
                const input = document.getElementById('forensic-address-input');
                if (input) {
                    input.value = '1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa';
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    const searchBtn = document.getElementById('forensic-search-btn');
                    if (searchBtn) searchBtn.click();
                    return 'populated input and clicked search';
                }
                return 'input not found';
            })()
            """
            eval_res = await cdp_send(ws, "Runtime.evaluate", {"expression": search_js}, msg_id=id_gen)
            print("Search trigger:", eval_res.get("result", {}).get("value"))
            
            # Capture console logs
            await cdp_send(ws, "Console.enable", msg_id=id_gen)
            await cdp_send(ws, "Network.enable", msg_id=id_gen)
            
            # Wait for mempool.space search to return and render
            print("Waiting for on-chain results to render...")
            for i in range(25):
                await asyncio.sleep(1.0)
                check_js = """
                (() => {
                    const text = document.body.innerText;
                    return {
                        hasMempool: text.includes('mempool.space') || text.includes('blockstream.info'),
                        hasBtc: text.includes('57.47') || text.includes('BTC'),
                        hasSatoshi: text.includes('Satoshi Nakamoto'),
                        hasChecksum: text.includes('Checksum verified'),
                        isLoading: text.includes('Searching...'),
                    };
                })()
                """
                check_res = await cdp_send(ws, "Runtime.evaluate", {"expression": check_js, "returnByValue": True}, msg_id=id_gen)
                val = check_res.get("result", {}).get("value", {})
                print(f"Status check {i+1}: hasMempool={val.get('hasMempool')}, hasBtc={val.get('hasBtc')}, hasSatoshi={val.get('hasSatoshi')}, hasChecksum={val.get('hasChecksum')}, isLoading={val.get('isLoading')}")
                if (val.get("hasMempool") or val.get("hasSatoshi")) and val.get("hasChecksum") and not val.get("isLoading"):
                    print("All required data rendered!")
                    break
            
            await asyncio.sleep(1.5)
            
            # Scroll the modal content to bottom to show evidence footer
            print("Scrolling modal to bottom...")
            scroll_js = """
            (() => {
                const modal = document.querySelector('.flex-1.overflow-y-auto');
                if (modal) {
                    modal.scrollTop = 1400;
                    return 'scrolled modal to ' + modal.scrollTop;
                }
                return 'modal scroll container not found';
            })()
            """
            scroll_res = await cdp_send(ws, "Runtime.evaluate", {"expression": scroll_js}, msg_id=id_gen)
            print("Scroll res:", scroll_res.get("result", {}).get("value"))
            await asyncio.sleep(1.0)
            
            # Capture footer screenshot
            print("Capturing footer screenshot...")
            shot_footer = await cdp_send(ws, "Page.captureScreenshot", {"format": "png"}, msg_id=id_gen)
            img_footer_data = base64.b64decode(shot_footer["data"])
            
            footer_path = os.path.abspath("artifacts/genesis_search_result_footer.png")
            with open(footer_path, "wb") as f:
                f.write(img_footer_data)
            print(f"Footer screenshot saved to: {footer_path}")
            
            if os.path.isdir(ARTIFACT_DIR):
                art_footer_path = os.path.join(ARTIFACT_DIR, "genesis_search_result_footer.png")
                with open(art_footer_path, "wb") as f:
                    f.write(img_footer_data)
                print(f"Footer screenshot saved to artifact: {art_footer_path}")
            
            print("Browser test and screenshot completed successfully!")
            
    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(main())
