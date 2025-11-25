# 🎫 Recreation.gov Automated Booking Bot

A production-ready Python bot for automated booking on Recreation.gov with web interface and Chrome extension integration.

## 🚀 Quick Deploy to Render.com

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

### Prerequisites
- Render.com account (free tier available)
- GitHub account
- Chrome browser with extension installed

### Deployment Steps

1. **Fork/Clone this repository**
   ```bash
   git clone https://github.com/MihirTcules/deployement-ticketbot.git
   cd deployement-ticketbot
   ```

2. **Generate Encryption Key**
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Save this key - you'll need it for the `ENCRYPTION_KEY` environment variable.

3. **Deploy to Render**
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Render will automatically detect `render.yaml` and configure the service
   - **Important**: Set the `ENCRYPTION_KEY` environment variable with the key you generated

4. **Configure Environment Variables** (if not using render.yaml)
   
   Required variables:
   - `ENCRYPTION_KEY` - Your generated encryption key
   - `TIMEZONE` - Your timezone (default: Asia/Kolkata)
   - `PORT` - Port for Flask (default: 5000)
   - `DATA_DIR` - Data directory (use: /opt/render/project/data)

5. **Add Persistent Disk**
   - In Render dashboard, go to your service
   - Navigate to "Disks" tab
   - Add disk: Mount path `/opt/render/project/data`, Size: 1GB

6. **Deploy!**
   - Click "Create Web Service"
   - Wait for deployment to complete
   - Your bot will be live at `https://your-service-name.onrender.com`

## 🌍 Timezone Configuration

The bot timezone is controlled by the `TIMEZONE` environment variable. Common values:

- `America/New_York` - Eastern Time
- `America/Los_Angeles` - Pacific Time
- `America/Chicago` - Central Time
- `Europe/London` - UK Time
- `Asia/Kolkata` - India Time
- `Australia/Sydney` - Australian Eastern Time

[Full list of timezones](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)

## 📦 Local Development

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set Environment Variables**
   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

3. **Run the Bot**
   ```bash
   python bot.py
   ```

4. **Access Web Interface**
   Open `http://localhost:5000` in your browser

## 🔧 Environment Variables

See `.env.example` for all available configuration options.

## 📚 Features

- ✅ Web-based scheduling interface
- ✅ Chrome extension integration
- ✅ Automated booking at precise times
- ✅ Multi-slot booking support
- ✅ Secure credential storage
- ✅ Persistent booking data
- ✅ Real-time WebSocket communication
- ✅ Production-ready for Render.com

## 🔒 Security

- Passwords are encrypted using Fernet encryption
- Encryption key stored in environment variables
- No sensitive data in repository
- HTTPS enforced on Render.com

## 📖 Documentation

For detailed deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md)

## 🐛 Troubleshooting

### Bot won't start
- Check logs in Render dashboard
- Verify `ENCRYPTION_KEY` is set
- Ensure `DATA_DIR` is set to `/opt/render/project/data`

### WebSocket connection fails
- Verify WebSocket port is accessible
- Check browser console for errors
- Ensure Chrome extension is installed

### Bookings not persisting
- Verify persistent disk is mounted at `/opt/render/project/data`
- Check `DATA_DIR` environment variable

## 📄 License

MIT License - See LICENSE file for details

