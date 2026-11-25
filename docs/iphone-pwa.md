# Life Optimizer on iPhone (local PWA)

Use the app from Safari on your iPhone over the same Wi‑Fi as the computer running Flask. This is **local / LAN only** — no Cursor App publish and no `SECRET_KEY` setup required.

## 1. Start the server on your computer

From the repo root:

```bash
./start.sh
```

Or:

```bash
python3 run.py
```

The app listens on **all interfaces** (`0.0.0.0:5000`), so phones on your LAN can reach it.

`start.sh` prints a LAN URL like `http://192.168.x.x:5000/today/` when it can detect your IP.

## 2. Find your computer’s LAN IP (if needed)

**macOS**

```bash
ipconfig getifaddr en0
```

**Linux**

```bash
hostname -I | awk '{print $1}'
```

**Windows (PowerShell)**

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' }
```

Use the address on the same Wi‑Fi as the phone (usually `192.168.…` or `10.…`).

## 3. Open on iPhone

1. Join the **same Wi‑Fi** as the computer.
2. In **Safari**, open: `http://<LAN-IP>:5000/today/`  
   Example: `http://192.168.1.42:5000/today/`
3. Confirm Today loads and you can tick a routine item.

> Firewall: allow inbound TCP **5000** on the computer if the phone cannot connect.

## 4. Add to Home Screen (standalone)

1. In Safari, tap the **Share** button.
2. Scroll and tap **Add to Home Screen**.
3. Name it **Life Optimizer** (or keep the default) → **Add**.
4. Open the new home-screen icon — it should launch full-screen without Safari chrome.

Home-screen launch uses the web app manifest and Apple meta tags (`apple-mobile-web-app-capable`, icons, theme color). Data stays on the computer’s local SQLite database; the phone is just a client over Wi‑Fi.

## Notes

- The computer must stay on and the Flask process must keep running.
- Leaving Wi‑Fi or sleeping the machine will make the home-screen icon fail to load until the server is reachable again.
- This path does **not** use Cursor App hosting or production secrets.
