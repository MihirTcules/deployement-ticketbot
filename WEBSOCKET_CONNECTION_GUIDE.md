# 🔌 WebSocket Connection Guide for Domain Name

## 📡 How WebSocket Works with Your Deployed Bot

When you deploy to Render.com, your bot will have a domain name like:
```
https://recreation-booking-bot.onrender.com
```

### WebSocket URLs

**IMPORTANT:** On Render.com, the bot uses **Flask-Sock** for WebSocket connections (not a standalone WebSocket server).

**Production (Render.com):**
- **WebSocket URL:** `wss://your-domain.onrender.com/ws`
- All WebSocket connections go through Flask on port 5000
- Port 8765 is **disabled** in production

**Local Development:**
- **WebSocket URL:** `ws://localhost:5000/ws`
- Can optionally enable standalone WebSocket on port 8765

---

## 🌐 Web Interface Connection (Already Configured)

The web interface (`static/js/app.js`) **automatically** connects to the correct WebSocket URL:

```javascript
// This code is already in your app.js - NO CHANGES NEEDED
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  
  ws = new WebSocket(wsUrl);
}
```

**How it works:**
- On localhost: Connects to `ws://localhost:5000/ws`
- On Render: Connects to `wss://your-domain.onrender.com/ws`
- **Automatically adapts** to your domain!

---

## 🔧 Chrome Extension Connection

For your Chrome extension to connect from outside, you need to configure it with your deployed domain.

### Option 1: Hardcode the Domain (Simple)

In your Chrome extension's background script or content script:

```javascript
// Replace with your actual Render domain
// IMPORTANT: Use /ws endpoint, NOT port 8765
const WEBSOCKET_URL = "wss://recreation-booking-bot.onrender.com/ws";

// Connect to WebSocket
const ws = new WebSocket(WEBSOCKET_URL);

ws.onopen = () => {
  console.log("✅ Connected to bot");
  // Send hello message
  ws.send(JSON.stringify({
    type: "hello",
    timestamp: new Date().toISOString()
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log("Received:", data);
  // Handle messages
};

ws.onerror = (error) => {
  console.error("❌ WebSocket error:", error);
};

ws.onclose = () => {
  console.log("Disconnected from bot");
};
```

### Option 2: Configurable Domain (Recommended)

Allow users to configure the domain in extension settings:

```javascript
// In your extension's options/settings page
chrome.storage.sync.set({
  botDomain: "recreation-booking-bot.onrender.com"
});

// In your background script
chrome.storage.sync.get(['botDomain'], (result) => {
  const domain = result.botDomain || "localhost:8765";
  const protocol = domain.includes("localhost") ? "ws:" : "wss:";
  const wsUrl = `${protocol}//${domain}`;
  
  const ws = new WebSocket(wsUrl);
  // ... rest of connection code
});
```

---

## 🔐 Important: WebSocket Protocol

### Local Development
- Use `ws://` (unsecured WebSocket)
- Example: `ws://localhost:8765`

### Production (Render.com)
- Use `wss://` (secured WebSocket over TLS)
- Example: `wss://recreation-booking-bot.onrender.com:8765`
- Render automatically provides SSL/TLS certificates

---

## 🚀 After Deployment: Get Your WebSocket URL

### Step 1: Deploy to Render
Follow the `RENDER_DEPLOYMENT_GUIDE.md`

### Step 2: Get Your Domain
After deployment, Render gives you a domain like:
```
https://recreation-booking-bot.onrender.com
```

### Step 3: Your WebSocket URL
Your WebSocket URL will be:
```
wss://recreation-booking-bot.onrender.com/ws
```

**Note:** Use `/ws` endpoint, NOT port 8765!

### Step 4: Update Chrome Extension
Replace the WebSocket URL in your extension code with the one above.

---

## 🧪 Testing WebSocket Connection

### Test from Browser Console

Open your deployed web interface and run in console:

```javascript
const ws = new WebSocket("wss://your-domain.onrender.com:8765");
ws.onopen = () => console.log("✅ Connected!");
ws.onerror = (e) => console.error("❌ Error:", e);
```

### Test with Python Script

```python
import asyncio
import websockets
import json

async def test():
    uri = "wss://your-domain.onrender.com:8765"
    async with websockets.connect(uri) as ws:
        # Send hello
        await ws.send(json.dumps({
            "type": "hello",
            "timestamp": "2024-01-01T00:00:00Z"
        }))
        
        # Receive response
        response = await ws.recv()
        print(f"Received: {response}")

asyncio.run(test())
```

---

## 🔥 Common Issues & Solutions

### Issue 1: "WebSocket connection failed"
**Cause:** Wrong protocol (ws:// instead of wss://)
**Solution:** Use `wss://` for production, `ws://` for localhost

### Issue 2: "Connection refused on port 8765"
**Cause:** Port 8765 is disabled in production (Render.com doesn't expose custom ports)
**Solution:** This is expected! Always use:
- `wss://your-domain.onrender.com/ws` (correct)
- NOT `wss://your-domain.onrender.com:8765` (wrong)

### Issue 3: "Mixed content error"
**Cause:** Trying to use `ws://` from an `https://` page
**Solution:** Always use `wss://` when connecting from HTTPS pages

---

## 💡 Production WebSocket Configuration

**ALWAYS use the Flask-Sock endpoint on Render.com:**

```javascript
// In your Chrome extension
const domain = "recreation-booking-bot.onrender.com";
const wsUrl = `wss://${domain}/ws`;  // Note: /ws endpoint, no port number

const ws = new WebSocket(wsUrl);
```

**Why Flask-Sock instead of port 8765?**
- ✅ Render.com doesn't expose custom ports (8765 won't work)
- ✅ Flask-Sock runs on the same port as Flask (5000)
- ✅ Simpler URL structure
- ✅ Same SSL certificate
- ✅ No additional configuration needed

---

## 📝 Summary

### For Web Interface (Already Done ✅)
- Automatically connects to correct domain
- No configuration needed

### For Chrome Extension
**Production URL (Render.com):**
```
wss://your-domain.onrender.com/ws
```

**Local Development URL:**
```
ws://localhost:5000/ws
```

### Environment Variables (Already Configured ✅)
- `ENABLE_STANDALONE_WEBSOCKET=false` - Disables port 8765 in production
- `PORT=5000` - Flask port (WebSocket runs on this port via Flask-Sock)

---

## 🎯 Quick Setup Checklist

- [ ] Deploy bot to Render.com
- [ ] Get your domain: `https://your-service.onrender.com`
- [ ] Update Chrome extension WebSocket URL to: `wss://your-service.onrender.com/ws`
- [ ] Test connection from extension
- [ ] Verify in bot logs: "👋 Extension connected"

**Your bot is ready to accept WebSocket connections from anywhere!** 🚀

