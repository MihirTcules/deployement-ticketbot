# 🚀 Deployment Guide: Recreation.gov Booking Bot on Render.com

This guide provides step-by-step instructions for deploying the Recreation.gov Automated Booking Bot to Render.com.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Pre-Deployment Checklist](#pre-deployment-checklist)
3. [Deployment Steps](#deployment-steps)
4. [Environment Variables Configuration](#environment-variables-configuration)
5. [Persistent Storage Setup](#persistent-storage-setup)
6. [WebSocket Configuration](#websocket-configuration)
7. [Chrome Extension Configuration](#chrome-extension-configuration)
8. [Post-Deployment Verification](#post-deployment-verification)P
9. [Troubleshooting](#troubleshooting)
10. [Monitoring & Maintenance](#monitoring--maintenance)

---

## 🔧 Prerequisites

Before deploying, ensure you have:

- ✅ A [Render.com](https://render.com) account (free tier available)
- ✅ Your code pushed to a Git repository (GitHub, GitLab, or Bitbucket)
- ✅ Python 3.11+ installed locally for testing
- ✅ Basic understanding of environment variables and web services

---

## ✅ Pre-Deployment Checklist

### 1. **Generate Encryption Key**

The application uses encryption for secure password storage. Generate a key:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Save this key securely** - you'll need it for the `ENCRYPTION_KEY` environment variable.

### 2. **Test Locally**

Before deploying, test the application locally:

```bash
cd Ticketbot/Python-bot

# Install dependencies
pip install -r requirements.txt

# Set environment variables (optional for local testing)
export PORT=5000
export WEBSOCKET_PORT=8765
export FLASK_ENV=development

# Run the application
python bot.py
```

Visit `http://localhost:5000` to verify the application works.

### 3. **Commit All Changes**

Ensure all files are committed to your Git repository:

```bash
git add .
git commit -m "Prepare for Render deployment"
git push origin main
```

---

## 🚀 Deployment Steps

### Step 1: Create New Web Service

1. Log in to [Render Dashboard](https://dashboard.render.com)
2. Click **"New +"** → **"Web Service"**
3. Connect your Git repository
4. Select the repository containing your bot code

### Step 2: Configure Service Settings

Fill in the following settings:

| Setting | Value |
|---------|-------|
| **Name** | `recreation-booking-bot` (or your preferred name) |
| **Region** | Choose closest to your location |
| **Branch** | `main` (or your default branch) |
| **Root Directory** | `Ticketbot/Python-bot` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python bot.py` |
| **Plan** | `Starter` (or higher for production) |

### Step 3: Add Persistent Disk

**IMPORTANT:** This ensures your booking data persists across deployments.

1. Scroll to **"Disks"** section
2. Click **"Add Disk"**
3. Configure:
   - **Name:** `booking-data`
   - **Mount Path:** `/opt/render/project/data`
   - **Size:** `1 GB` (sufficient for JSON files)
4. Click **"Save"**

---

## 🔐 Environment Variables Configuration

### Step 4: Set Environment Variables

In the Render dashboard, scroll to **"Environment Variables"** and add:

#### **Required Variables:**

```bash
# Server Configuration
PORT=5000
WEBSOCKET_PORT=8765
WEBSOCKET_HOST=0.0.0.0
FLASK_ENV=production
FLASK_DEBUG=false

# Security & Encryption
ENCRYPTION_KEY=<your-generated-encryption-key-here>

# Data Storage
DATA_DIR=/opt/render/project/data

# Logging
LOG_LEVEL=INFO

# Timezone
TZ=Asia/Kolkata

# WebSocket Configuration
MAX_MESSAGE_SIZE=1048576
PING_INTERVAL=20
PING_TIMEOUT=20

# Application Settings
MAX_QUANTITY_PER_TAB=50
```

#### **How to Add Variables:**

1. Click **"Add Environment Variable"**
2. Enter **Key** and **Value**
3. Repeat for all variables above
4. **IMPORTANT:** Replace `<your-generated-encryption-key-here>` with the key you generated earlier

---

## 💾 Persistent Storage Setup

### Understanding Render's Disk Storage

Render provides persistent disk storage that survives deployments and restarts.

**Configuration:**
- **Mount Path:** `/opt/render/project/data`
- **Files Stored:**
  - `scheduled_bookings.json` - Active bookings
  - `scheduled_bookings.backup.json` - Backup file
  - `bot_config.json` - User configuration
  - `.config_key` - Encryption key (if not using env var)

**Important Notes:**
- ✅ Data persists across deployments
- ✅ Data persists across service restarts
- ⚠️ Data is NOT backed up by Render - implement your own backup strategy
- ⚠️ Disk is tied to the service - if you delete the service, data is lost

---

## 🔌 WebSocket Configuration

### Understanding WebSocket on Render

Render supports WebSocket connections, but there are some considerations:

#### **WebSocket URL Format:**

Your deployed WebSocket URL will be:
```
wss://your-service-name.onrender.com:8765
```

**Note:** Render automatically handles SSL/TLS, so use `wss://` (secure WebSocket) instead of `ws://`.

#### **Firewall & Port Configuration:**

- Render allows custom ports (like 8765 for WebSocket)
- No additional firewall configuration needed
- WebSocket connections are automatically upgraded from HTTP

#### **Connection Timeout:**

- Render has a 30-second connection timeout for idle connections
- The bot is configured with ping/pong to keep connections alive
- Default ping interval: 20 seconds (configurable via `PING_INTERVAL`)

---

## 🔧 Chrome Extension Configuration

### Update Extension to Connect to Deployed Server

After deployment, update your Chrome Extension to connect to the deployed WebSocket server.

#### **Step 1: Get Your Service URL**

From Render dashboard, copy your service URL:
```
https://recreation-booking-bot.onrender.com
```

#### **Step 2: Update Extension Configuration**

In your Chrome Extension's background script or configuration:

```javascript
// Replace localhost with your Render service URL
const WEBSOCKET_URL = "wss://recreation-booking-bot.onrender.com:8765";

// Connect to WebSocket
const ws = new WebSocket(WEBSOCKET_URL);
```

#### **Step 3: Update Web Interface URL**

If your extension needs to open the web interface:

```javascript
const WEB_INTERFACE_URL = "https://recreation-booking-bot.onrender.com";
```

#### **Step 4: Reload Extension**

1. Go to `chrome://extensions/`
2. Click **"Reload"** on your extension
3. Test the connection

---

## ✅ Post-Deployment Verification

### Step 5: Verify Deployment

After deployment completes, verify everything works:

#### **1. Check Service Status**

In Render dashboard:
- ✅ Service status should be **"Live"**
- ✅ Build logs should show no errors
- ✅ Service logs should show startup messages

#### **2. Test Web Interface**

Visit your service URL:
```
https://your-service-name.onrender.com
```

You should see the booking bot interface.

#### **3. Check Logs**

In Render dashboard, go to **"Logs"** tab and verify:

```
🚀 Recreation.gov Booking Bot Starting
📍 Environment: production
🌐 Flask Port: 5000
🔌 WebSocket Port: 8765
🌍 WebSocket Host: 0.0.0.0
🕐 Timezone: Asia/Kolkata
📊 Log Level: INFO
🌐 Starting Flask server on 0.0.0.0:5000
🛰️ Starting WebSocket server at ws://0.0.0.0:8765
✅ WebSocket server ready at ws://0.0.0.0:8765
✅ Waiting for connections from Chrome Extension...
```

#### **4. Test WebSocket Connection**

Use a WebSocket testing tool or your Chrome Extension to connect:

```javascript
const ws = new WebSocket("wss://your-service-name.onrender.com:8765");

ws.onopen = () => {
  console.log("✅ Connected to WebSocket server");
};

ws.onerror = (error) => {
  console.error("❌ WebSocket error:", error);
};
```

#### **5. Test Booking Creation**

1. Open the web interface
2. Create a test booking
3. Verify it appears in the calendar
4. Refresh the page
5. Verify the booking persists (loaded from `scheduled_bookings.json`)

---

## 🐛 Troubleshooting

### Common Issues and Solutions

#### **Issue 1: Service Won't Start**

**Symptoms:**
- Build succeeds but service crashes
- Logs show import errors or missing dependencies

**Solutions:**
1. Check `requirements.txt` has all dependencies
2. Verify Python version compatibility (3.11+)
3. Check logs for specific error messages
4. Ensure `DATA_DIR` environment variable is set

#### **Issue 2: WebSocket Connection Fails**

**Symptoms:**
- Chrome Extension can't connect
- "Connection refused" or "Connection timeout" errors

**Solutions:**
1. Verify `WEBSOCKET_PORT` is set to `8765`
2. Verify `WEBSOCKET_HOST` is set to `0.0.0.0`
3. Use `wss://` (not `ws://`) in extension
4. Check Render logs for WebSocket startup messages
5. Ensure firewall/network allows WebSocket connections

#### **Issue 3: Bookings Don't Persist**

**Symptoms:**
- Bookings disappear after page refresh
- Bookings disappear after deployment

**Solutions:**
1. Verify persistent disk is configured correctly
2. Check `DATA_DIR` environment variable: `/opt/render/project/data`
3. Verify disk is mounted at correct path
4. Check logs for file write errors
5. Verify disk has sufficient space

#### **Issue 4: Encryption Key Errors**

**Symptoms:**
- "Invalid ENCRYPTION_KEY" warnings in logs
- Can't save/load passwords

**Solutions:**
1. Verify `ENCRYPTION_KEY` is set in environment variables
2. Regenerate key: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
3. Update environment variable with new key
4. Restart service

#### **Issue 5: Service Sleeps (Free Tier)**

**Symptoms:**
- Service becomes unresponsive after inactivity
- First request after inactivity is slow

**Solutions:**
- Render's free tier spins down after 15 minutes of inactivity
- Upgrade to paid plan for always-on service
- Use external monitoring service to ping your service periodically

---

## 📊 Monitoring & Maintenance

### Monitoring Your Deployment

#### **1. Render Dashboard**

Monitor your service health:
- **Metrics:** CPU, Memory, Request count
- **Logs:** Real-time application logs
- **Events:** Deployment history, restarts

#### **2. Application Logs**

Key log messages to monitor:

```bash
# Successful startup
✅ WebSocket server ready

# Booking operations
✅ Saved booking <id>
💾 Persisted status update for booking <id>

# Errors to watch for
❌ Failed to save booking
❌ Failed to start WebSocket server
❌ Failed to persist booking message
```

#### **3. Health Checks**

Render automatically monitors your service health:
- **Health Check Path:** `/` (main page)
- **Timeout:** 30 seconds
- **Restart Policy:** Automatic restart on failure

### Backup Strategy

**IMPORTANT:** Render does NOT automatically backup your persistent disk.

#### **Manual Backup:**

1. Download `scheduled_bookings.json` via API or direct access
2. Store backups in external storage (S3, Google Drive, etc.)
3. Schedule regular backups (daily/weekly)

#### **Automated Backup (Optional):**

Add a backup endpoint to your application:

```python
@app.route('/api/backup', methods=['GET'])
def backup_bookings():
    """Download backup of all bookings"""
    # Implement authentication here
    bookings = booking_storage.get_all_bookings()
    return jsonify(bookings)
```

### Updating Your Deployment

#### **Automatic Deployments:**

Render automatically deploys when you push to your Git repository:

```bash
git add .
git commit -m "Update application"
git push origin main
```

Render will:
1. Pull latest code
2. Run build command
3. Restart service with new code
4. Persistent disk data remains intact

#### **Manual Deployments:**

In Render dashboard:
1. Go to your service
2. Click **"Manual Deploy"**
3. Select **"Deploy latest commit"**

---

## 🔒 Security Best Practices

### Production Security Checklist

- ✅ Use strong `ENCRYPTION_KEY` (never commit to Git)
- ✅ Set `FLASK_ENV=production` and `FLASK_DEBUG=false`
- ✅ Use environment variables for all secrets
- ✅ Enable HTTPS (automatic on Render)
- ✅ Implement authentication for sensitive endpoints
- ✅ Regularly update dependencies
- ✅ Monitor logs for suspicious activity
- ✅ Backup data regularly

### Environment Variable Security

**DO:**
- ✅ Set sensitive variables in Render dashboard
- ✅ Use `.env.example` for documentation
- ✅ Add `.env` to `.gitignore`

**DON'T:**
- ❌ Commit `.env` files to Git
- ❌ Hardcode secrets in code
- ❌ Share encryption keys publicly

---

## 📞 Support & Resources

### Render Documentation

- [Render Docs](https://render.com/docs)
- [Python on Render](https://render.com/docs/deploy-flask)
- [Persistent Disks](https://render.com/docs/disks)
- [Environment Variables](https://render.com/docs/environment-variables)

### Application Support

- Check application logs in Render dashboard
- Review this deployment guide
- Test locally before deploying
- Monitor service health regularly

---

## 🎉 Deployment Complete!

Your Recreation.gov Booking Bot is now deployed and running on Render.com!

**Next Steps:**
1. ✅ Configure Chrome Extension with deployed URL
2. ✅ Test booking creation and persistence
3. ✅ Set up monitoring and alerts
4. ✅ Implement backup strategy
5. ✅ Share deployed URL with users

**Deployed URLs:**
- **Web Interface:** `https://your-service-name.onrender.com`
- **WebSocket:** `wss://your-service-name.onrender.com:8765`
- **API:** `https://your-service-name.onrender.com/api/*`

---

**Happy Booking! 🎫🏕️**

