# 🆓 Render.com Free Plan Guide

## ⚠️ Important Limitations

### 1. **No Persistent Disk Storage**
The free plan does NOT include persistent disk storage. This means:
- ❌ Bookings will be **lost on every restart**
- ❌ Configuration will be **lost on every restart**
- ❌ You'll need to reconfigure credentials after each restart

### 2. **Automatic Restarts**
Render free services:
- Sleep after 15 minutes of inactivity
- Restart when accessed again
- **All data is lost** when the service restarts

### 3. **What Gets Lost**
When your service restarts, you lose:
- All scheduled bookings
- Recreation.gov credentials
- Any configuration settings

## ✅ What Still Works

Despite these limitations, the bot still works for:
- ✅ **Real-time bookings** - Schedule and execute bookings in the same session
- ✅ **Web interface** - Full UI functionality
- ✅ **WebSocket connections** - Chrome extension integration
- ✅ **Immediate use** - Create booking and use it right away

## 🎯 Recommended Usage on Free Plan

### Best Practice: Same-Session Bookings
1. Open the web interface
2. Configure your Recreation.gov credentials
3. Schedule your booking
4. Wait for the booking to execute
5. ✅ Done!

**Don't close the browser or let the service sleep before your booking executes!**

## 💡 Workarounds for Free Plan

### Option 1: Keep Service Awake
Use a service like [UptimeRobot](https://uptimerobot.com/) to ping your service every 5 minutes:
- Prevents the service from sleeping
- Keeps bookings in memory
- Free tier available

**Setup:**
1. Sign up at https://uptimerobot.com
2. Add new monitor
3. Monitor Type: HTTP(s)
4. URL: `https://your-bot.onrender.com`
5. Monitoring Interval: 5 minutes

### Option 2: Local Development
Run the bot locally for persistent storage:
```bash
# Clone the repository
git clone https://github.com/MihirTcules/deployement-ticketbot.git
cd deployement-ticketbot

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env

# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Add the key to .env file
# ENCRYPTION_KEY=your-generated-key

# Run the bot
python bot.py
```

**Benefits:**
- ✅ Persistent storage (data survives restarts)
- ✅ No sleep/restart issues
- ✅ Full functionality

### Option 3: Upgrade to Paid Plan
Render's paid plans start at $7/month and include:
- ✅ Persistent disk storage
- ✅ No automatic sleep
- ✅ Better performance
- ✅ More resources

## 🔄 Data Storage on Free Plan

The bot uses `/tmp` directory for storage on the free plan:

```
DATA_DIR=/tmp
```

**What this means:**
- Data is stored in temporary directory
- Cleared on every restart
- Not suitable for long-term storage

## 📊 Comparison

| Feature | Free Plan | Paid Plan ($7/mo) |
|---------|-----------|-------------------|
| **Persistent Storage** | ❌ No | ✅ Yes (1GB+) |
| **Auto Sleep** | ✅ Yes (15 min) | ❌ No |
| **Data Survives Restart** | ❌ No | ✅ Yes |
| **Bookings Persist** | ❌ No | ✅ Yes |
| **Config Persists** | ❌ No | ✅ Yes |
| **WebSocket** | ✅ Yes | ✅ Yes |
| **Web Interface** | ✅ Yes | ✅ Yes |
| **Chrome Extension** | ✅ Yes | ✅ Yes |

## 🚀 Deployment on Free Plan

The bot is already configured for the free plan:

```yaml
# render.yaml
services:
  - type: web
    plan: free  # ✅ Free plan
    envVars:
      - key: DATA_DIR
        value: /tmp  # ✅ Temporary storage
```

**No changes needed!** Just deploy and use.

## ⚠️ Important Warnings

When you start the bot on the free plan, you'll see these warnings:

```
⚠️ Using /tmp for data storage - data will be lost on restart!
⚠️ For persistent storage, upgrade to a paid Render plan with disk storage
⚠️ Using /tmp for bookings - data will be lost on restart!
```

**This is expected!** The bot is warning you that data won't persist.

## 💰 When to Upgrade

Consider upgrading to a paid plan if:
- You need bookings to survive restarts
- You schedule bookings days/weeks in advance
- You want to set it and forget it
- You need 24/7 availability

## 🎯 Summary

### Free Plan is Good For:
✅ Testing the bot  
✅ Same-session bookings  
✅ Immediate use  
✅ Learning how it works  

### Free Plan is NOT Good For:
❌ Long-term booking storage  
❌ Set-and-forget scheduling  
❌ Bookings scheduled days ahead  
❌ Persistent configuration  

## 🔗 Useful Links

- **Render Pricing**: https://render.com/pricing
- **Render Docs**: https://render.com/docs
- **UptimeRobot** (keep service awake): https://uptimerobot.com
- **GitHub Repo**: https://github.com/MihirTcules/deployement-ticketbot

---

**The bot works great on the free plan for immediate use! Just be aware of the storage limitations.** 🎉

