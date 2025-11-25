# 🚀 Quick Render.com Deployment Guide

## ✅ Your Code is Ready!

Your Recreation.gov Booking Bot has been successfully prepared for production deployment on Render.com and pushed to:
**https://github.com/MihirTcules/deployement-ticketbot.git**

## 📋 Pre-Deployment Checklist

### 1. Generate Encryption Key

Run this command locally to generate your encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Copy and save this key** - you'll need it in step 4!

Example output: `xK8vN2mP9qR5sT7uV1wX3yZ4aB6cD8eF0gH2iJ4kL6m=`

## 🚀 Deploy to Render.com (5 Minutes)

### Step 1: Create New Web Service

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **"New +"** → **"Web Service"**
3. Click **"Connect account"** to link your GitHub
4. Select repository: `MihirTcules/deployement-ticketbot`

### Step 2: Configure Service

Render will auto-detect `render.yaml`, but verify these settings:

| Setting | Value |
|---------|-------|
| **Name** | `recreation-booking-bot` |
| **Region** | Choose closest to you |
| **Branch** | `main` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python bot.py` |

### Step 3: Add Persistent Disk

**CRITICAL**: Your bookings need persistent storage!

1. Scroll to **"Disk"** section
2. Click **"Add Disk"**
3. Configure:
   - **Name**: `booking-data`
   - **Mount Path**: `/opt/render/project/data`
   - **Size**: `1 GB` (free tier)

### Step 4: Set Environment Variables

**IMPORTANT**: You must set the `ENCRYPTION_KEY`!

1. Scroll to **"Environment Variables"**
2. The `render.yaml` sets most variables automatically
3. **Manually add** (if not auto-generated):
   - **Key**: `ENCRYPTION_KEY`
   - **Value**: Paste the key you generated in Pre-Deployment step 1

### Step 5: Deploy!

1. Click **"Create Web Service"**
2. Wait 2-3 minutes for deployment
3. Your bot will be live at: `https://recreation-booking-bot.onrender.com`

## 🌍 Customize Timezone (Optional)

The default timezone is `Asia/Kolkata`. To change it:

1. Go to your service in Render dashboard
2. Click **"Environment"** tab
3. Find `TIMEZONE` variable
4. Change to your timezone:
   - `America/New_York` - Eastern Time
   - `America/Los_Angeles` - Pacific Time
   - `America/Chicago` - Central Time
   - `Europe/London` - UK Time
   - `Australia/Sydney` - Australian Time

[Full timezone list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)

## ✅ Verify Deployment

### 1. Check Service Status
- In Render dashboard, status should show **"Live"** (green)

### 2. View Logs
- Click **"Logs"** tab
- Look for:
  ```
  🌍 Using timezone: Asia/Kolkata
  🔐 Using encryption key from environment variable
  🌐 Flask web server starting on http://0.0.0.0:5000
  ✅ WebSocket server ready on 0.0.0.0:8765
  ```

### 3. Test Web Interface
- Open your service URL: `https://your-service-name.onrender.com`
- You should see the booking interface

### 4. Test Booking Creation
1. Click "New Booking" in the web interface
2. Fill in booking details
3. Save booking
4. Refresh page - booking should persist (stored in disk)

## 🔧 Environment Variables Reference

All variables are pre-configured in `render.yaml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `TIMEZONE` | `Asia/Kolkata` | Your timezone |
| `PORT` | `5000` | Flask server port |
| `WEBSOCKET_PORT` | `8765` | WebSocket port |
| `ENCRYPTION_KEY` | *required* | Encryption key for passwords |
| `DATA_DIR` | `/opt/render/project/data` | Data storage path |
| `LOG_LEVEL` | `INFO` | Logging level |

## 🐛 Troubleshooting

### Service Won't Start
- **Check logs** for error messages
- **Verify** `ENCRYPTION_KEY` is set
- **Ensure** disk is mounted at `/opt/render/project/data`

### Bookings Not Persisting
- **Verify** persistent disk is added
- **Check** `DATA_DIR` = `/opt/render/project/data`
- **View logs** for file write errors

### Can't Access Web Interface
- **Wait** 2-3 minutes after deployment
- **Check** service status is "Live"
- **Try** hard refresh (Ctrl+Shift+R)

## 📞 Support

- **Render Docs**: https://render.com/docs
- **View Logs**: Render Dashboard → Your Service → Logs
- **Check Status**: Render Dashboard → Your Service → Events

## 🎉 You're Done!

Your bot is now running in production on Render.com with:
- ✅ Timezone control via environment variable
- ✅ Secure password encryption
- ✅ Persistent booking storage
- ✅ Auto-scaling and monitoring
- ✅ HTTPS enabled by default

**Next Steps:**
1. Configure your Chrome extension with the deployed URL
2. Create your first booking
3. Monitor logs for any issues

Happy booking! 🎫

