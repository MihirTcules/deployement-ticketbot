import asyncio
import websockets
import json
import os
from datetime import datetime, timedelta
import pytz
import logging
import uuid
from threading import Thread
from flask import Flask, render_template, send_from_directory, request, jsonify
from flask_sock import Sock
from config import config_manager
from booking_storage import booking_storage

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Get timezone from environment variable or use default
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
try:
    LOCAL_TZ = pytz.timezone(TIMEZONE)
    logger.info(f"🌍 Using timezone: {TIMEZONE}")
except pytz.exceptions.UnknownTimeZoneError:
    logger.warning(f"⚠️  Unknown timezone '{TIMEZONE}', falling back to Asia/Kolkata")
    LOCAL_TZ = pytz.timezone("Asia/Kolkata")

# Get configuration from environment variables
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("PORT", "5000"))
WEBSOCKET_HOST = os.getenv("WEBSOCKET_HOST", "0.0.0.0")
WEBSOCKET_PORT = int(os.getenv("WEBSOCKET_PORT", "8765"))
MAX_QUANTITY_PER_TAB = int(os.getenv("MAX_QUANTITY_PER_TAB", "50"))

# Detect if running on Render.com (or production environment)
IS_PRODUCTION = os.getenv("RENDER") is not None or os.getenv("FLASK_ENV") == "production"
ENABLE_STANDALONE_WEBSOCKET = os.getenv("ENABLE_STANDALONE_WEBSOCKET", "false").lower() == "true"

connected_clients = set()  # Extension clients (standalone WebSocket - disabled in production)
extension_clients = set()  # Extension clients via Flask-Sock
web_clients = set()  # Web interface clients via Flask-Sock
pending_tasks = {}  # Track pending URL triggers
active_bookings = {}  # Track active bookings
main_event_loop = None  # Store reference to main asyncio event loop

# ==============================
# 🎯 Quantity Splitting Logic
# ==============================
def split_quantities_for_multi_tab(time_slots):
    """
    Split time slots with quantities > 50 into multiple tabs

    Args:
        time_slots: List of dicts with 'time' and 'quantity' keys

    Returns:
        List of dicts with 'time' and 'quantity' keys, where each quantity <= 50

    Example:
        Input: [{'time': '9:00 AM', 'quantity': 120}]
        Output: [
            {'time': '9:00 AM', 'quantity': 50},
            {'time': '9:00 AM', 'quantity': 50},
            {'time': '9:00 AM', 'quantity': 20}
        ]
    """
    result = []

    for slot in time_slots:
        time = slot['time']
        quantity = slot['quantity']

        # If quantity <= 50, no splitting needed
        if quantity <= MAX_QUANTITY_PER_TAB:
            result.append({'time': time, 'quantity': quantity})
        else:
            # Calculate number of tabs needed
            num_tabs = (quantity + MAX_QUANTITY_PER_TAB - 1) // MAX_QUANTITY_PER_TAB  # Ceiling division

            # Split quantity across tabs
            for i in range(num_tabs):
                remaining = quantity - (i * MAX_QUANTITY_PER_TAB)
                tab_quantity = min(remaining, MAX_QUANTITY_PER_TAB)
                result.append({'time': time, 'quantity': tab_quantity})

            # Log the split
            quantities_str = " + ".join([str(min(MAX_QUANTITY_PER_TAB, quantity - i * MAX_QUANTITY_PER_TAB))
                                        for i in range(num_tabs)])
            logger.info(f"📊 Split {quantity} tickets for '{time}' across {num_tabs} tabs ({quantities_str})")

    return result

# ==============================
# 🌐 Flask Web Server
# ==============================
app = Flask(__name__,
            template_folder='templates',
            static_folder='static')
sock = Sock(app)

@app.route('/')
def index():
    """Serve the main web interface"""
    return render_template('index.html')

@app.route('/static/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory('static', path)

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration (password masked)"""
    try:
        config = config_manager.get_config_for_api()
        return jsonify({
            'success': True,
            'config': config
        })
    except Exception as e:
        logger.error(f"❌ Failed to get configuration: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/config', methods=['POST'])
def save_config():
    """Save configuration"""
    try:
        data = request.get_json()

        # Validate required fields
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400

        # Save configuration
        success = config_manager.update_config(data)

        if success:
            logger.info("✅ Configuration updated via API")
            return jsonify({
                'success': True,
                'message': 'Configuration saved successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save configuration'
            }), 500
    except Exception as e:
        logger.error(f"❌ Failed to save configuration: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/config', methods=['DELETE'])
def clear_config():
    """Clear configuration"""
    try:
        success = config_manager.clear_config()

        if success:
            logger.info("🗑️ Configuration cleared via API")
            return jsonify({
                'success': True,
                'message': 'Configuration cleared successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to clear configuration'
            }), 500
    except Exception as e:
        logger.error(f"❌ Failed to clear configuration: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ==============================
# 📅 Booking Persistence API
# ==============================

@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    """Get all scheduled bookings"""
    try:
        bookings = booking_storage.get_all_bookings()
        return jsonify({
            'success': True,
            'bookings': bookings
        })
    except Exception as e:
        logger.error(f"❌ Failed to get bookings: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/bookings', methods=['POST'])
def create_booking():
    """Save a new booking"""
    try:
        booking = request.get_json()

        if not booking:
            return jsonify({
                'success': False,
                'error': 'No booking data provided'
            }), 400

        # Validate required fields
        required_fields = ['id', 'url', 'booking_date']
        for field in required_fields:
            if field not in booking:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400

        success = booking_storage.save_booking(booking)

        if success:
            logger.info(f"✅ Booking {booking.get('id')} saved via API")
            return jsonify({
                'success': True,
                'message': 'Booking saved successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save booking'
            }), 500
    except Exception as e:
        logger.error(f"❌ Failed to create booking: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/bookings/<booking_id>', methods=['PUT'])
def update_booking(booking_id):
    """Update an existing booking"""
    try:
        updates = request.get_json()

        if not updates:
            return jsonify({
                'success': False,
                'error': 'No update data provided'
            }), 400

        success = booking_storage.update_booking(booking_id, updates)

        if success:
            logger.info(f"✅ Booking {booking_id} updated via API")
            return jsonify({
                'success': True,
                'message': 'Booking updated successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Booking not found or update failed'
            }), 404
    except Exception as e:
        logger.error(f"❌ Failed to update booking: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/bookings/<booking_id>', methods=['DELETE'])
def delete_booking(booking_id):
    """Delete a booking"""
    try:
        success = booking_storage.delete_booking(booking_id)

        if success:
            logger.info(f"✅ Booking {booking_id} deleted via API")
            return jsonify({
                'success': True,
                'message': 'Booking deleted successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Booking not found'
            }), 404
    except Exception as e:
        logger.error(f"❌ Failed to delete booking: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/bookings/<booking_id>/logs', methods=['POST'])
def add_booking_log(booking_id):
    """Add a log entry to a booking"""
    try:
        log_entry = request.get_json()

        if not log_entry:
            return jsonify({
                'success': False,
                'error': 'No log data provided'
            }), 400

        success = booking_storage.add_log_to_booking(booking_id, log_entry)

        if success:
            return jsonify({
                'success': True,
                'message': 'Log added successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Booking not found'
            }), 404
    except Exception as e:
        logger.error(f"❌ Failed to add log to booking: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@sock.route('/ws')
def websocket_handler(ws):
    """Handle WebSocket connections from web interface AND Chrome extension"""
    # Initially add to web_clients, will move to extension_clients if "hello" message received
    web_clients.add(ws)
    is_extension = False
    logger.info(f"✅ Client connected via Flask-Sock (total web: {len(web_clients)}, extension: {len(extension_clients)})")

    try:
        while True:
            message = ws.receive()
            if message:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")

                    # Check if this is an extension connection (hello message)
                    if msg_type == "hello" and not is_extension:
                        # Move from web_clients to extension_clients
                        web_clients.discard(ws)
                        extension_clients.add(ws)
                        is_extension = True
                        logger.info(f"👋 Chrome extension connected via Flask-Sock (total: {len(extension_clients)})")

                        # Send welcome message
                        ws.send(json.dumps({"type": "welcome", "message": "Bot is ready"}))

                        # Send configuration to extension
                        try:
                            config = config_manager.load_config()
                            if config:
                                ws.send(json.dumps({
                                    "type": "config",
                                    "email": config.get("email"),
                                    "password": config.get("password")
                                }))
                                logger.info("📤 Sent configuration to extension via Flask-Sock")
                        except Exception as e:
                            logger.error(f"❌ Failed to send configuration to extension: {e}")

                        # Notify web clients
                        broadcast_to_web({"type": "log", "message": "✅ Chrome extension connected", "level": "success"})
                        continue

                    # Schedule the coroutine in the main event loop from Flask thread
                    if main_event_loop:
                        if is_extension:
                            asyncio.run_coroutine_threadsafe(handle_extension_message(data, ws), main_event_loop)
                        else:
                            asyncio.run_coroutine_threadsafe(handle_web_message(data, ws), main_event_loop)
                    else:
                        logger.error("❌ Main event loop not available")
                except json.JSONDecodeError as e:
                    logger.error(f"❌ Invalid JSON from client: {e}")
                except Exception as e:
                    logger.error(f"❌ Error handling message: {e}")
    except Exception as e:
        logger.warning(f"❌ Client disconnected: {e}")
    finally:
        if is_extension:
            extension_clients.discard(ws)
            logger.info(f"Remaining extension clients: {len(extension_clients)}")
        else:
            web_clients.discard(ws)
            logger.info(f"Remaining web clients: {len(web_clients)}")

async def handle_web_message(data: dict, ws):
    """Handle messages from web interface"""
    msg_type = data.get("type")

    if msg_type == "web_hello":
        ws.send(json.dumps({"type": "welcome", "message": "Bot is ready"}))
        logger.info("👋 Web interface connected")

    elif msg_type == "schedule_booking":
        # Schedule a new booking from web interface
        try:
            booking_id = str(uuid.uuid4())[:8]
            url = data.get("url")
            email = data.get("email")
            password = data.get("password")
            booking_date = data.get("booking_date")

            # Support both old format (separate fields) and new format (combined datetime)
            trigger_datetime = data.get("trigger_datetime")
            trigger_time = data.get("trigger_time")
            time_format = data.get("time_format")
            time_slots = data.get("time_slots", [])

            # Parse trigger time - support both formats for backward compatibility
            if trigger_datetime:
                # New format: combined datetime string
                target_time = parse_trigger_datetime(trigger_datetime)
            elif trigger_time and time_format:
                # Old format: separate time and format
                target_time = parse_trigger_time(trigger_time, time_format)
            else:
                raise ValueError("Either trigger_datetime or (trigger_time + time_format) must be provided")

            # Convert time_slots to slots_with_quantities format
            # Split quantities > 50 into multiple tabs
            original_slots_count = len(time_slots)
            slots_with_quantities = split_quantities_for_multi_tab(time_slots)
            time_slots_list = [slot['time'] for slot in slots_with_quantities]

            # Log multi-tab booking info
            if len(slots_with_quantities) > original_slots_count:
                total_tabs = len(slots_with_quantities)
                logger.info(f"🔀 Multi-tab booking: {original_slots_count} slot(s) split into {total_tabs} tab(s) due to quantity limits")

                # Broadcast to web clients
                broadcast_to_web({
                    "type": "log",
                    "message": f"🔀 Splitting booking into {total_tabs} tabs to handle quantity limits",
                    "level": "info"
                })

            # Store booking info
            # Format trigger_time for display (use combined datetime if available, otherwise use legacy format)
            trigger_time_display = trigger_datetime if trigger_datetime else trigger_time

            booking = {
                "id": booking_id,
                "url": url,
                "booking_date": booking_date,
                "trigger_time": trigger_time_display,
                "trigger_datetime": target_time.isoformat(),  # Store parsed datetime for reference
                "time_slots": time_slots,
                "status": "scheduled",
                "created_at": datetime.now().isoformat()
            }
            active_bookings[booking_id] = booking

            # Persist booking to storage
            booking_storage.save_booking(booking)

            # Send confirmation to web client
            ws.send(json.dumps({
                "type": "booking_scheduled",
                "booking_id": booking_id,
                "booking": booking
            }))

            # Schedule the booking
            asyncio.create_task(schedule_and_trigger(
                target_time, url, email, password,
                time_slots_list, booking_date, slots_with_quantities,
                booking_id
            ))

            logger.info(f"✅ Booking {booking_id} scheduled from web interface")

        except Exception as e:
            logger.error(f"❌ Failed to schedule booking: {e}")
            ws.send(json.dumps({
                "type": "error",
                "message": f"Failed to schedule booking: {str(e)}"
            }))

    elif msg_type == "cancel_booking":
        booking_id = data.get("booking_id")
        if booking_id in active_bookings:
            del active_bookings[booking_id]
            # Delete from persistent storage
            booking_storage.delete_booking(booking_id)
            logger.info(f"🗑️ Booking {booking_id} cancelled")

    elif msg_type == "ping":
        ws.send(json.dumps({"type": "pong", "timestamp": datetime.now().timestamp()}))

def parse_trigger_time(trigger_time: str, time_format: str):
    """Parse trigger time from web interface (legacy format - separate time field)"""
    now = datetime.now(LOCAL_TZ)

    if time_format == "relative":
        # Format: +N (minutes from now)
        minutes = int(trigger_time.replace('+', ''))
        return now + timedelta(minutes=minutes)
    else:
        # Format: HH:MM or H:MM AM/PM
        trigger_time = trigger_time.strip()

        # Check if it's 12-hour format (contains AM/PM)
        if 'AM' in trigger_time.upper() or 'PM' in trigger_time.upper():
            # Parse 12-hour format
            time_obj = datetime.strptime(trigger_time, "%I:%M %p")
            target_time = now.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
        else:
            # Parse 24-hour format
            hour, minute = map(int, trigger_time.split(":"))
            target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # If time is in the past, schedule for tomorrow
        if target_time <= now:
            target_time += timedelta(days=1)

        return target_time

def parse_trigger_datetime(trigger_datetime: str):
    """Parse combined trigger datetime from web interface (new format)

    Supports multiple datetime formats:
    - ISO format: "2025-12-15T10:00" or "2025-12-15 10:00"
    - Flatpickr format: "December 15, 2025 10:00"
    - Custom format: "2025-12-15 10:00 AM"
    """
    trigger_datetime = trigger_datetime.strip()

    # List of datetime formats to try
    formats = [
        "%Y-%m-%dT%H:%M",           # ISO format: 2025-12-15T10:00
        "%Y-%m-%d %H:%M",           # Space-separated: 2025-12-15 10:00
        "%Y-%m-%d %I:%M %p",        # 12-hour with AM/PM: 2025-12-15 10:00 AM
        "%B %d, %Y %H:%M",          # Flatpickr format: December 15, 2025 10:00
        "%B %d, %Y %I:%M %p",       # Flatpickr 12-hour: December 15, 2025 10:00 AM
        "%m/%d/%Y %H:%M",           # US format: 12/15/2025 10:00
        "%m/%d/%Y %I:%M %p",        # US 12-hour: 12/15/2025 10:00 AM
        "%d/%m/%Y %H:%M",           # European format: 15/12/2025 10:00
        "%d/%m/%Y %I:%M %p",        # European 12-hour: 15/12/2025 10:00 AM
    ]

    target_time = None
    for fmt in formats:
        try:
            # Parse the datetime string
            parsed_dt = datetime.strptime(trigger_datetime, fmt)
            # Apply local timezone
            target_time = LOCAL_TZ.localize(parsed_dt)
            logger.info(f"✅ Parsed trigger datetime '{trigger_datetime}' using format '{fmt}' -> {target_time}")
            break
        except ValueError:
            continue

    if target_time is None:
        raise ValueError(f"Could not parse trigger datetime: '{trigger_datetime}'. Supported formats: YYYY-MM-DD HH:MM, Month DD, YYYY HH:MM, etc.")

    # Validate that the datetime is in the future
    now = datetime.now(LOCAL_TZ)
    if target_time <= now:
        raise ValueError(f"Trigger datetime must be in the future. Provided: {target_time}, Current: {now}")

    return target_time

async def handle_extension_message(data: dict, ws):
    """Handle messages from Chrome extension via Flask-Sock"""
    msg_type = data.get("type")
    booking_id = data.get("booking_id")  # Extract booking_id from all messages

    if msg_type == "ack":
        # Acknowledgment that URL was stored
        status = data.get("status")
        url = data.get("url")
        if status == "stored":
            logger.info(f"✅ Extension confirmed URL stored: {url}")
            broadcast_to_web({"type": "log", "message": f"✅ Extension confirmed URL stored", "level": "success"})

            # Update booking status
            if booking_id:
                broadcast_to_web({
                    "type": "booking_update",
                    "booking_id": booking_id,
                    "status": "extension_ready",
                    "message": "Extension confirmed URL stored and ready"
                })
        elif status == "error":
            logger.error(f"❌ Extension failed to store URL: {data.get('error')}")
            broadcast_to_web({"type": "log", "message": f"❌ Extension failed to store URL: {data.get('error')}", "level": "error"})

            # Update booking status
            if booking_id:
                broadcast_to_web({
                    "type": "booking_update",
                    "booking_id": booking_id,
                    "status": "error",
                    "message": f"Extension error: {data.get('error')}"
                })

    elif msg_type == "session_status":
        # Session check result
        status = data.get("status")
        url = data.get("url")
        username = data.get("username")
        if status == "already_logged_in":
            logger.info(f"✅ User already logged in as '{username}' on {url}")
            broadcast_to_web({"type": "log", "message": f"✅ Already logged in as '{username}'", "level": "success"})

            # Update booking status
            if booking_id:
                broadcast_to_web({
                    "type": "booking_update",
                    "booking_id": booking_id,
                    "status": "logged_in",
                    "message": f"Already logged in as '{username}'"
                })
        elif status == "not_logged_in":
            logger.info(f"🔓 User not logged in on {url}, will attempt auto-login")
            broadcast_to_web({"type": "log", "message": "🔓 Not logged in, attempting auto-login...", "level": "info"})

            # Update booking status
            if booking_id:
                broadcast_to_web({
                    "type": "booking_update",
                    "booking_id": booking_id,
                    "status": "logging_in",
                    "message": "Attempting auto-login..."
                })

    elif msg_type == "login_result":
        # Login attempt result
        status = data.get("status")
        url = data.get("url")
        if status == "success":
            username = data.get("username")
            logger.info(f"🎉 LOGIN SUCCESS: Logged in as '{username}' on {url}")
            broadcast_to_web({"type": "log", "message": f"🎉 Login successful as '{username}'", "level": "success"})

            # Update booking status
            if booking_id:
                broadcast_to_web({
                    "type": "booking_update",
                    "booking_id": booking_id,
                    "status": "logged_in",
                    "message": f"Login successful as '{username}'"
                })
        elif status == "failed":
            error = data.get("error")
            logger.error(f"❌ LOGIN FAILED on {url}: {error}")
            broadcast_to_web({"type": "log", "message": f"❌ Login failed: {error}", "level": "error"})

            # Update booking status
            if booking_id:
                broadcast_to_web({
                    "type": "booking_update",
                    "booking_id": booking_id,
                    "status": "error",
                    "message": f"Login failed: {error}"
                })

    elif msg_type == "pre_login_result":
        # Pre-login trigger result
        status = data.get("status")
        url = data.get("url")
        if status == "success":
            if data.get("alreadyLoggedIn"):
                username = data.get("username")
                logger.info(f"✅ Pre-login check: Already logged in as '{username}' on {url}")
                broadcast_to_web({"type": "log", "message": f"✅ Pre-login: Already logged in as '{username}'", "level": "success"})

                # Update booking status
                if booking_id:
                    broadcast_to_web({
                        "type": "booking_update",
                        "booking_id": booking_id,
                        "status": "pre_login_complete",
                        "message": f"Pre-login: Already logged in as '{username}'"
                    })
            elif data.get("loggedIn"):
                username = data.get("username")
                logger.info(f"🎉 Pre-login: Successfully logged in as '{username}' on {url}")
                broadcast_to_web({"type": "log", "message": f"🎉 Pre-login: Logged in as '{username}'", "level": "success"})

                # Update booking status
                if booking_id:
                    broadcast_to_web({
                        "type": "booking_update",
                        "booking_id": booking_id,
                        "status": "pre_login_complete",
                        "message": f"Pre-login: Logged in as '{username}'"
                    })
        elif status == "error":
            error = data.get("error")
            logger.error(f"❌ Pre-login failed on {url}: {error}")
            broadcast_to_web({"type": "log", "message": f"❌ Pre-login failed: {error}", "level": "error"})

            # Update booking status
            if booking_id:
                broadcast_to_web({
                    "type": "booking_update",
                    "booking_id": booking_id,
                    "status": "error",
                    "message": f"Pre-login failed: {error}"
                })

    elif msg_type == "result":
        # Final result from extension
        status = data.get("status")
        message = data.get("message", "")

        if status == "success":
            logger.info(f"✅ Extension completed successfully: {message}")
            broadcast_to_web({"type": "log", "message": f"✅ Booking completed: {message}", "level": "success"})

            # Update booking status to completed
            if booking_id:
                broadcast_to_web({
                    "type": "booking_update",
                    "booking_id": booking_id,
                    "status": "completed",
                    "message": message or "Booking completed successfully"
                })
        elif status == "partial":
            logger.warning(f"⚠️ Extension completed with partial success: {message}")
            broadcast_to_web({"type": "log", "message": f"⚠️ Partial success: {message}", "level": "warning"})

            # Update booking status to partial
            if booking_id:
                broadcast_to_web({
                    "type": "booking_update",
                    "booking_id": booking_id,
                    "status": "partial",
                    "message": message or "Some bookings succeeded, some failed"
                })
        elif status == "error":
            error = data.get("error", message)
            logger.error(f"❌ Extension error: {error}")
            broadcast_to_web({"type": "log", "message": f"❌ Error: {error}", "level": "error"})

            # Update booking status to failed
            if booking_id:
                broadcast_to_web({
                    "type": "booking_update",
                    "booking_id": booking_id,
                    "status": "failed",
                    "message": error or "Booking failed"
                })

    elif msg_type == "booking_result":
        # Detailed result for individual slot booking
        slot = data.get("slot")
        slot_status = data.get("status")
        steps = data.get("steps", {})
        timings = data.get("timings", {})
        error = data.get("error")
        requested_qty = data.get("requestedQuantity")
        available_qty = data.get("availableQuantity")
        actual_qty = data.get("actualQuantity")

        # Log detailed result
        if slot_status == "success":
            logger.info(f"✅ Slot '{slot}' booked successfully - Quantity: {actual_qty}/{requested_qty}")
            msg = f"✅ Slot '{slot}' booked: {actual_qty} ticket(s)"
            if available_qty and available_qty < requested_qty:
                msg += f" (only {available_qty} available)"
            broadcast_to_web({"type": "log", "message": msg, "level": "success"})
        else:
            logger.error(f"❌ Slot '{slot}' booking failed: {error}")
            broadcast_to_web({"type": "log", "message": f"❌ Slot '{slot}' failed: {error}", "level": "error"})

        # Update booking with detailed event log
        if booking_id:
            event_log = {
                "timestamp": data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                "slot": slot,
                "status": slot_status,
                "steps": steps,
                "timings": timings,
                "quantities": {
                    "requested": requested_qty,
                    "available": available_qty,
                    "actual": actual_qty
                },
                "error": error
            }

            broadcast_to_web({
                "type": "booking_event_log",
                "booking_id": booking_id,
                "event": event_log
            })

def broadcast_to_web(message: dict):
    """Send message to all web clients (synchronous for Flask-Sock)"""
    if web_clients:
        msg = json.dumps(message)
        for ws in list(web_clients):  # Create a copy to avoid modification during iteration
            try:
                ws.send(msg)
            except Exception as e:
                logger.error(f"Failed to send to web client: {e}")
                web_clients.discard(ws)  # Remove disconnected client

    # Persist booking updates and logs to storage
    _persist_booking_message(message)

def _persist_booking_message(message: dict):
    """Persist booking updates and logs to JSON storage"""
    try:
        msg_type = message.get("type")
        booking_id = message.get("booking_id")

        if not booking_id:
            return

        # Handle booking status updates
        if msg_type == "booking_update":
            updates = {}
            if message.get("status"):
                updates["status"] = message.get("status")
            if message.get("message"):
                updates["message"] = message.get("message")

            if updates:
                booking_storage.update_booking(booking_id, updates)
                logger.info(f"💾 Persisted status update for booking {booking_id}: {updates}")

        # Handle booking event logs
        elif msg_type == "booking_event_log":
            log_entry = {
                "message": message.get("message", ""),
                "level": message.get("level", "info"),
                "event_type": message.get("event_type", "general"),
                "timestamp": datetime.now().isoformat()
            }
            booking_storage.add_log_to_booking(booking_id, log_entry)
            logger.info(f"💾 Persisted log for booking {booking_id}")
    except Exception as e:
        logger.error(f"❌ Failed to persist booking message: {e}")

def run_flask():
    """Run Flask server in a separate thread"""
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)

# ==============================
# 🌐 WebSocket Handler
# ==============================
async def handler(websocket):
    connected_clients.add(websocket)
    logger.info(f"✅ Client connected: {websocket.remote_address} (total {len(connected_clients)})")

    try:
        async for message in websocket:
            logger.info(f"📨 Received from {websocket.remote_address}: {message}")
            try:
                data = json.loads(message)
                await handle_client_message(data, websocket)
            except json.JSONDecodeError as e:
                logger.error(f"❌ Invalid JSON from client: {e}")
            except Exception as e:
                logger.error(f"❌ Error handling message: {e}")
    except websockets.exceptions.ConnectionClosed:
        logger.warning(f"❌ Client disconnected: {websocket.remote_address}")
    finally:
        connected_clients.discard(websocket)
        logger.info(f"Remaining clients: {len(connected_clients)}")

# ==============================
# 📩 Handle Messages from Extension
# ==============================
async def handle_client_message(data: dict, websocket):
    """Handle incoming messages from the Chrome extension"""
    msg_type = data.get("type")

    if msg_type == "hello":
        logger.info(f"👋 Extension connected at {data.get('timestamp')}")
        await websocket.send(json.dumps({"type": "welcome", "message": "Bot is ready"}))

        # Send configuration to extension
        try:
            config = config_manager.load_config()
            await websocket.send(json.dumps({
                "type": "config_update",
                "config": {
                    "monitoring_time": config.get("slot_monitoring_time", 30),
                    "monitoring_interval": config.get("monitoring_interval", 50)
                }
            }))
            logger.info("📤 Sent configuration to extension")
        except Exception as e:
            logger.error(f"❌ Failed to send configuration to extension: {e}")

        # Notify web clients
        broadcast_to_web({"type": "log", "message": "✅ Chrome extension connected", "level": "success"})

    elif msg_type == "ack":
        # Acknowledgment that URL was stored
        status = data.get("status")
        url = data.get("url")
        if status == "stored":
            logger.info(f"✅ Extension confirmed URL stored: {url}")
            broadcast_to_web({"type": "log", "message": f"✅ Extension confirmed URL stored", "level": "success"})
        elif status == "error":
            logger.error(f"❌ Extension failed to store URL: {data.get('error')}")
            broadcast_to_web({"type": "log", "message": f"❌ Extension failed to store URL: {data.get('error')}", "level": "error"})

    elif msg_type == "session_status":
        # Session check result
        status = data.get("status")
        url = data.get("url")
        username = data.get("username")
        if status == "already_logged_in":
            logger.info(f"✅ User already logged in as '{username}' on {url}")
            broadcast_to_web({"type": "log", "message": f"✅ Already logged in as '{username}'", "level": "success"})
        elif status == "not_logged_in":
            logger.info(f"🔓 User not logged in on {url}, will attempt auto-login")
            broadcast_to_web({"type": "log", "message": "🔓 Not logged in, attempting auto-login...", "level": "info"})

    elif msg_type == "login_result":
        # Login attempt result
        status = data.get("status")
        url = data.get("url")
        if status == "success":
            username = data.get("username")
            logger.info(f"🎉 LOGIN SUCCESS: Logged in as '{username}' on {url}")
            broadcast_to_web({"type": "log", "message": f"🎉 Login successful as '{username}'", "level": "success"})
        elif status == "failed":
            error = data.get("error")
            logger.error(f"❌ LOGIN FAILED on {url}: {error}")
            broadcast_to_web({"type": "log", "message": f"❌ Login failed: {error}", "level": "error"})

    elif msg_type == "pre_login_result":
        # Pre-login trigger result (2 min before scheduled time)
        status = data.get("status")
        url = data.get("url")
        if status == "success":
            if data.get("alreadyLoggedIn"):
                username = data.get("username")
                logger.info(f"✅ Pre-login check: Already logged in as '{username}' on {url}")
                broadcast_to_web({"type": "log", "message": f"✅ Pre-login: Already logged in as '{username}'", "level": "success"})
            elif data.get("loggedIn"):
                username = data.get("username")
                logger.info(f"🎉 Pre-login: Successfully logged in as '{username}' on {url}")
                broadcast_to_web({"type": "log", "message": f"🎉 Pre-login successful as '{username}'", "level": "success"})
            elif data.get("noLogin"):
                logger.info(f"ℹ️ Pre-login check completed (no auto-login configured)")
                broadcast_to_web({"type": "log", "message": "ℹ️ Pre-login check completed", "level": "info"})
            logger.info(f"🗑️ Pre-login tab closed. Final tab will open in 1 minute.")
            broadcast_to_web({"type": "log", "message": "🗑️ Pre-login tab closed. Final tab opens in 1 minute.", "level": "info"})
        elif status == "error":
            error = data.get("error")
            logger.error(f"❌ Pre-login failed on {url}: {error}")
            broadcast_to_web({"type": "log", "message": f"❌ Pre-login failed: {error}", "level": "error"})

    elif msg_type == "result":
        # Result of opening the URL (single or multi-slot)
        status = data.get("status")
        url = data.get("url")
        multi_slot = data.get("multiSlot", False)

        if multi_slot:
            # Multi-slot result
            slots = data.get("slots", [])
            total_slots = data.get("totalSlots", 0)
            success_count = data.get("successCount", 0)
            failed_count = data.get("failedCount", 0)

            if status == "success":
                logger.info(f"📂 Opening {total_slots} tabs for slots: {', '.join([s['slot'] for s in slots])}")
                broadcast_to_web({"type": "log", "message": f"📂 Opening {total_slots} tabs for time slots", "level": "info"})
                for slot_info in slots:
                    slot = slot_info.get("slot")
                    tab_id = slot_info.get("tabId")
                    slot_status = slot_info.get("status")
                    if slot_status == "loaded":
                        logger.info(f"✅ Slot \"{slot}\" loaded in tab {tab_id}")
                        broadcast_to_web({"type": "log", "message": f"✅ Slot \"{slot}\" loaded successfully", "level": "success"})
                    else:
                        error = slot_info.get("error", "Unknown error")
                        logger.error(f"❌ Slot \"{slot}\" failed: {error}")
                        broadcast_to_web({"type": "log", "message": f"❌ Slot \"{slot}\" failed: {error}", "level": "error"})
                logger.info(f"🎉 SUCCESS: All {total_slots} tabs opened successfully")
                broadcast_to_web({"type": "log", "message": f"🎉 All {total_slots} tabs opened successfully!", "level": "success"})

            elif status == "partial_success":
                logger.info(f"📂 Opening {total_slots} tabs for slots: {', '.join([s['slot'] for s in slots])}")
                broadcast_to_web({"type": "log", "message": f"📂 Opening {total_slots} tabs for time slots", "level": "info"})
                for slot_info in slots:
                    slot = slot_info.get("slot")
                    tab_id = slot_info.get("tabId")
                    slot_status = slot_info.get("status")
                    if slot_status == "loaded":
                        logger.info(f"✅ Slot \"{slot}\" loaded in tab {tab_id}")
                        broadcast_to_web({"type": "log", "message": f"✅ Slot \"{slot}\" loaded successfully", "level": "success"})
                    else:
                        error = slot_info.get("error", "Unknown error")
                        logger.error(f"❌ Slot \"{slot}\" failed: {error}")
                        broadcast_to_web({"type": "log", "message": f"❌ Slot \"{slot}\" failed: {error}", "level": "error"})
                logger.warning(f"⚠️ PARTIAL SUCCESS: {success_count} of {total_slots} tabs opened successfully")
                broadcast_to_web({"type": "log", "message": f"⚠️ Partial success: {success_count}/{total_slots} tabs opened", "level": "warning"})

            elif status == "error":
                error = data.get("error")
                logger.error(f"❌ FAILED to open multi-slot tabs: {error}")
                broadcast_to_web({"type": "log", "message": f"❌ Failed to open tabs: {error}", "level": "error"})
        else:
            # Single tab result
            if status == "success":
                tab_id = data.get("tabId")
                logger.info(f"🎉 SUCCESS: URL opened in tab {tab_id}: {url}")
                broadcast_to_web({"type": "log", "message": f"🎉 URL opened successfully in tab {tab_id}", "level": "success"})
            elif status == "warning":
                tab_id = data.get("tabId")
                message = data.get("message")
                logger.warning(f"⚠️ WARNING: {message} (tab {tab_id})")
                broadcast_to_web({"type": "log", "message": f"⚠️ {message}", "level": "warning"})
            elif status == "error":
                error = data.get("error")
                logger.error(f"❌ FAILED to open URL: {url} - Error: {error}")
                broadcast_to_web({"type": "log", "message": f"❌ Failed to open URL: {error}", "level": "error"})

    elif msg_type == "booking_result":
        # Automated booking result from extension
        slot = data.get("slot")
        tab_id = data.get("tabId")
        status = data.get("status")
        steps = data.get("steps", {})
        timings = data.get("timings", {})
        error = data.get("error")
        requested_quantity = data.get("requestedQuantity", data.get("quantity", 1))  # Fallback for backward compatibility
        available_quantity = data.get("availableQuantity")
        actual_quantity = data.get("actualQuantity", requested_quantity)

        # Find the booking ID for this result (match by URL and date)
        url = data.get("url")
        booking_id = None
        for bid, booking in active_bookings.items():
            if booking.get("url") == url:
                booking_id = bid
                break

        if status == "success":
            # Build quantity message
            if available_quantity is not None and actual_quantity != requested_quantity:
                quantity_msg = f"({actual_quantity} ticket(s) - requested {requested_quantity}, but only {available_quantity} available)"
                quantity_info = f"📊 Quantity adjusted: Booked {actual_quantity} tickets (requested {requested_quantity}, available {available_quantity})"
            else:
                quantity_msg = f"({actual_quantity} ticket(s))"
                quantity_info = None

            logger.info(f"🎉 BOOKING SUCCESS: Slot \"{slot}\" {quantity_msg} - Tab {tab_id}")

            # Send event-based log to frontend
            if booking_id:
                broadcast_to_web({
                    "type": "booking_event_log",
                    "booking_id": booking_id,
                    "message": f"🎉 BOOKING SUCCESS: Slot \"{slot}\" {quantity_msg}",
                    "level": "success",
                    "event_type": "booking_result"
                })

                # Update booking status to completed
                broadcast_to_web({
                    "type": "booking_update",
                    "booking_id": booking_id,
                    "status": "completed",
                    "message": f"✅ Booking completed successfully for slot \"{slot}\""
                })

            # Display quantity adjustment info if applicable
            if quantity_info:
                logger.info(f"   {quantity_info}")
                if booking_id:
                    broadcast_to_web({
                        "type": "booking_event_log",
                        "booking_id": booking_id,
                        "message": quantity_info,
                        "level": "warning",
                        "event_type": "quantity_adjustment"
                    })

            logger.info(f"   ✅ Date selection: {steps.get('dateSelection', 'unknown')}")
            logger.info(f"   ✅ Quantity selection: {steps.get('quantitySelection', 'unknown')}")
            logger.info(f"   ✅ Slot monitoring: {steps.get('slotMonitoring', 'unknown')}")
            logger.info(f"   ✅ Ticket request: {steps.get('ticketRequest', 'unknown')}")

            # Send step details to frontend
            if booking_id:
                broadcast_to_web({
                    "type": "booking_event_log",
                    "booking_id": booking_id,
                    "message": f"✅ Date selection: {steps.get('dateSelection', 'unknown')}",
                    "level": "info",
                    "event_type": "step_detail"
                })
                broadcast_to_web({
                    "type": "booking_event_log",
                    "booking_id": booking_id,
                    "message": f"✅ Quantity selection: {steps.get('quantitySelection', 'unknown')}",
                    "level": "info",
                    "event_type": "step_detail"
                })
                broadcast_to_web({
                    "type": "booking_event_log",
                    "booking_id": booking_id,
                    "message": f"✅ Slot monitoring: {steps.get('slotMonitoring', 'unknown')}",
                    "level": "info",
                    "event_type": "step_detail"
                })
                broadcast_to_web({
                    "type": "booking_event_log",
                    "booking_id": booking_id,
                    "message": f"✅ Ticket request: {steps.get('ticketRequest', 'unknown')}",
                    "level": "info",
                    "event_type": "step_detail"
                })

            # Display timing information
            if timings:
                logger.info(f"   ⏱️ TIMING BREAKDOWN:")
                total_time = timings.get('totalBookingTime', 0)
                if timings.get('dateSelectionDuration'):
                    logger.info(f"      Date Selection: {timings['dateSelectionDuration']}ms ({timings['dateSelectionDuration']/1000:.2f}s)")
                if timings.get('quantitySelectionDuration'):
                    logger.info(f"      Quantity Selection: {timings['quantitySelectionDuration']}ms ({timings['quantitySelectionDuration']/1000:.2f}s)")
                if timings.get('slotMonitoringDuration'):
                    logger.info(f"      Slot Monitoring: {timings['slotMonitoringDuration']}ms ({timings['slotMonitoringDuration']/1000:.2f}s)")
                if timings.get('ticketRequestDuration'):
                    logger.info(f"      Ticket Request: {timings['ticketRequestDuration']}ms ({timings['ticketRequestDuration']/1000:.2f}s)")
                if total_time:
                    logger.info(f"      ⏱️ TOTAL BOOKING TIME: {total_time}ms ({total_time/1000:.2f}s)")
                    if booking_id:
                        broadcast_to_web({
                            "type": "booking_event_log",
                            "booking_id": booking_id,
                            "message": f"⏱️ Total booking time: {total_time/1000:.2f}s",
                            "level": "info",
                            "event_type": "timing"
                        })

        elif status == "failed":
            # Build quantity message for failed booking
            if available_quantity is not None and actual_quantity != requested_quantity:
                quantity_msg = f"({actual_quantity} ticket(s) - requested {requested_quantity}, but only {available_quantity} available)"
            else:
                quantity_msg = f"({actual_quantity} ticket(s))"

            logger.error(f"❌ BOOKING FAILED: Slot \"{slot}\" {quantity_msg} - Tab {tab_id}")
            logger.error(f"   Error: {error}")

            # Send event-based log to frontend
            if booking_id:
                broadcast_to_web({
                    "type": "booking_event_log",
                    "booking_id": booking_id,
                    "message": f"❌ BOOKING FAILED: Slot \"{slot}\" - {error}",
                    "level": "error",
                    "event_type": "booking_result"
                })

                # Update booking status to failed
                broadcast_to_web({
                    "type": "booking_update",
                    "booking_id": booking_id,
                    "status": "failed",
                    "message": f"❌ Booking failed for slot \"{slot}\": {error}"
                })

            logger.info(f"   Date selection: {steps.get('dateSelection', 'unknown')}")
            logger.info(f"   Quantity selection: {steps.get('quantitySelection', 'unknown')}")
            logger.info(f"   Slot monitoring: {steps.get('slotMonitoring', 'unknown')}")
            logger.info(f"   Ticket request: {steps.get('ticketRequest', 'unknown')}")

            # Send step details to frontend
            if booking_id:
                broadcast_to_web({
                    "type": "booking_event_log",
                    "booking_id": booking_id,
                    "message": f"Date selection: {steps.get('dateSelection', 'unknown')}",
                    "level": "info",
                    "event_type": "step_detail"
                })
                broadcast_to_web({
                    "type": "booking_event_log",
                    "booking_id": booking_id,
                    "message": f"Quantity selection: {steps.get('quantitySelection', 'unknown')}",
                    "level": "info",
                    "event_type": "step_detail"
                })
                broadcast_to_web({
                    "type": "booking_event_log",
                    "booking_id": booking_id,
                    "message": f"Slot monitoring: {steps.get('slotMonitoring', 'unknown')}",
                    "level": "info",
                    "event_type": "step_detail"
                })
                broadcast_to_web({
                    "type": "booking_event_log",
                    "booking_id": booking_id,
                    "message": f"Ticket request: {steps.get('ticketRequest', 'unknown')}",
                    "level": "info",
                    "event_type": "step_detail"
                })

            # Display timing information even for failed bookings
            if timings:
                logger.info(f"   ⏱️ TIMING BREAKDOWN:")
                if timings.get('dateSelectionDuration'):
                    logger.info(f"      Date Selection: {timings['dateSelectionDuration']}ms ({timings['dateSelectionDuration']/1000:.2f}s)")
                if timings.get('quantitySelectionDuration'):
                    logger.info(f"      Quantity Selection: {timings['quantitySelectionDuration']}ms ({timings['quantitySelectionDuration']/1000:.2f}s)")
                if timings.get('slotMonitoringDuration'):
                    logger.info(f"      Slot Monitoring: {timings['slotMonitoringDuration']}ms ({timings['slotMonitoringDuration']/1000:.2f}s)")
                if timings.get('ticketRequestDuration'):
                    logger.info(f"      Ticket Request: {timings['ticketRequestDuration']}ms ({timings['ticketRequestDuration']/1000:.2f}s)")
                if timings.get('totalBookingTime'):
                    logger.info(f"      ⏱️ TOTAL TIME: {timings['totalBookingTime']}ms ({timings['totalBookingTime']/1000:.2f}s)")

    elif msg_type == "ping":
        await websocket.send(json.dumps({"type": "pong", "timestamp": datetime.now().timestamp()}))

    elif msg_type == "pong":
        logger.debug("🏓 Pong received from extension")

    else:
        logger.warning(f"⚠️ Unknown message type: {msg_type}")

# ==============================
# 🌍 Broadcast Utility
# ==============================
async def broadcast(message: dict):
    """Send message to all connected extension clients (both standalone and Flask-Sock)"""
    msg = json.dumps(message)
    sent_count = 0

    # Send to standalone WebSocket clients (if enabled)
    if connected_clients:
        results = await asyncio.gather(
            *(ws.send(msg) for ws in connected_clients),
            return_exceptions=True
        )
        # Log any send failures
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Failed to send to standalone client: {result}")
            else:
                sent_count += 1

    # Send to Flask-Sock extension clients (production mode)
    if extension_clients:
        for ws in list(extension_clients):
            try:
                ws.send(msg)
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send to Flask-Sock extension client: {e}")
                extension_clients.discard(ws)

    if sent_count == 0:
        logger.warning("⚠️ No extension clients connected to send message.")
    else:
        logger.info(f"📤 Sent message to {sent_count} extension client(s)")

# ==============================
# ⏰ Schedule + Trigger Logic
# ==============================
async def schedule_and_trigger(target_time: datetime, url: str, email: str = None, password: str = None,
                               time_slots: list = None, booking_date: str = None, slots_with_quantities: list = None,
                               booking_id: str = None):
    """Schedule a URL to be opened at a specific time with optional login credentials, time slots, and automated booking

    Timeline with auto-login:
    - 2 minutes before: Check login status, perform auto-login if needed, close tab
    - 1 minute before: Open URL in new tab(s) (user is logged in and ready)
    - At scheduled time: User interacts with the page

    If time_slots is provided, multiple tabs will be opened (one per slot)
    If slots_with_quantities is provided, automated booking will be performed in each tab
    """
    now = datetime.now(LOCAL_TZ)
    wait_seconds = (target_time - now).total_seconds()

    if wait_seconds < 0:
        logger.warning("⚠️ Time is in the past. Adjusting to +1 day.")
        target_time += timedelta(days=1)
        wait_seconds = (target_time - now).total_seconds()

    # Validate URL format
    if not url.startswith(('http://', 'https://')):
        logger.warning(f"⚠️ URL doesn't start with http:// or https://, adding https://")
        url = 'https://' + url

    # Log multi-slot info
    if time_slots and len(time_slots) > 0:
        slots_str = ", ".join(time_slots)
        logger.info(f"📋 Multi-slot booking: {len(time_slots)} time slots: {slots_str}")

    # Log automated booking info
    if booking_date and slots_with_quantities:
        logger.info(f"🤖 Automated booking enabled for date: {booking_date}")
        for slot in slots_with_quantities:
            logger.info(f"   - {slot['time']}: {slot['quantity']} ticket(s)")

    # Security warning if credentials are provided
    if email and password:
        logger.warning("⚠️ SECURITY WARNING: Credentials will be transmitted via WebSocket and stored temporarily.")
        logger.info(f"🔐 Login enabled for: {email}")
        if time_slots and len(time_slots) > 0:
            logger.info(f"⏳ Scheduled multi-slot trigger with auto-login at {target_time.strftime('%Y-%m-%d %H:%M:%S')} "
                        f"(in {int(wait_seconds)}s) for URL: {url}")
        else:
            logger.info(f"⏳ Scheduled trigger with auto-login at {target_time.strftime('%Y-%m-%d %H:%M:%S')} "
                        f"(in {int(wait_seconds)}s) for URL: {url}")
        logger.info(f"📅 Timeline: Login check at 2min before, Final tab(s) at 1min before")
    else:
        if time_slots and len(time_slots) > 0:
            logger.info(f"⏳ Scheduled multi-slot trigger at {target_time.strftime('%Y-%m-%d %H:%M:%S')} "
                        f"(in {int(wait_seconds)}s) for URL: {url}")
        else:
            logger.info(f"⏳ Scheduled trigger at {target_time.strftime('%Y-%m-%d %H:%M:%S')} "
                        f"(in {int(wait_seconds)}s) for URL: {url}")

    # Send URL and credentials to extension for storage
    message = {
        "type": "store_url",
        "url": url,
        "scheduled_time": target_time.isoformat(),
        "booking_id": booking_id  # Add booking_id for unique identification
    }

    # Add time_slots if provided
    if time_slots and len(time_slots) > 0:
        message["time_slots"] = time_slots

    # Add booking parameters if provided
    if booking_date:
        message["booking_date"] = booking_date
    if slots_with_quantities:
        message["slots_with_quantities"] = slots_with_quantities

    if email and password:
        message["email"] = email
        message["password"] = password
        message["auto_login"] = True
    else:
        message["auto_login"] = False

    await broadcast(message)
    logger.info(f"📦 Sent 'store_url' to extension(s) for booking {booking_id}.")

    # Notify web clients
    if booking_id:
        broadcast_to_web({
            "type": "log",
            "message": f"📦 Booking {booking_id} parameters sent to extension",
            "level": "info"
        })

    # Two-stage trigger for auto-login
    if email and password and wait_seconds > 120:  # Only if more than 2 minutes away
        # Stage 1: Login check and auto-login (2 minutes before)
        pre_login_wait = wait_seconds - 120  # Wait until 2 minutes before
        logger.info(f"⏰ Stage 1: Waiting {int(pre_login_wait)}s until login check (2 min before scheduled time)...")
        await asyncio.sleep(pre_login_wait)

        logger.info(f"🚀 Stage 1: Triggering login check for booking {booking_id} — sending 'pre_login_trigger' to extension(s).")
        await broadcast({"type": "pre_login_trigger", "url": url, "booking_id": booking_id})

        # Notify web clients
        if booking_id:
            broadcast_to_web({
                "type": "booking_update",
                "booking_id": booking_id,
                "status": "login_check",
                "message": "🔐 Performing login check..."
            })
            broadcast_to_web({
                "type": "booking_event_log",
                "booking_id": booking_id,
                "message": "🔐 Performing login check (2 minutes before booking time)...",
                "level": "info",
                "event_type": "login_check"
            })

        # Stage 2: Final tab opening (1 minute before)
        logger.info("⏰ Stage 2: Waiting 60s until final tab opening (1 min before scheduled time)...")
        await asyncio.sleep(60)

        if time_slots and len(time_slots) > 0:
            logger.info(f"🚀 Stage 2: Opening final tabs for {len(time_slots)} time slots for booking {booking_id} — sending 'trigger' to extension(s).")
            await broadcast({"type": "trigger", "url": url, "time_slots": time_slots, "booking_id": booking_id})
        else:
            logger.info(f"🚀 Stage 2: Opening final tab for booking {booking_id} — sending 'trigger' to extension(s).")
            await broadcast({"type": "trigger", "url": url, "booking_id": booking_id})

        # Notify web clients
        if booking_id:
            broadcast_to_web({
                "type": "booking_update",
                "booking_id": booking_id,
                "status": "running",
                "message": f"🚀 Opening {len(time_slots) if time_slots else 1} tab(s) for booking..."
            })
            broadcast_to_web({
                "type": "booking_event_log",
                "booking_id": booking_id,
                "message": f"🚀 Opening {len(time_slots) if time_slots else 1} tab(s) for booking...",
                "level": "info",
                "event_type": "booking_start"
            })

        # Stage 3: Execute booking at exact trigger time (T-0)
        # Wait the remaining 60 seconds until the scheduled time
        logger.info("⏰ Stage 3: Waiting 60s until exact trigger time (T-0) for date selection...")
        await asyncio.sleep(60)

        # Send execute_booking message with booking parameters
        if slots_with_quantities and len(slots_with_quantities) > 0:
            logger.info(f"🎯 Stage 3: TRIGGER TIME (T-0) - Sending 'execute_booking' for {len(slots_with_quantities)} slots to extension(s).")
            execute_message = {
                "type": "execute_booking",
                "booking_id": booking_id,
                "booking_date": booking_date,
                "slots_with_quantities": slots_with_quantities
            }
            await broadcast(execute_message)

            # Notify web clients
            broadcast_to_web({
                "type": "booking_event_log",
                "booking_id": booking_id,
                "message": f"🎯 TRIGGER TIME (T-0): Executing booking for {len(slots_with_quantities)} slot(s)...",
                "level": "info",
                "event_type": "execute_booking"
            })
        else:
            logger.info(f"⚠️ Stage 3: No automated booking configured for booking {booking_id}, skipping execute_booking message.")

    else:
        # No auto-login or less than 2 minutes away - use single trigger
        # For automated bookings, we need to open tabs 1 minute before and execute at T-0
        if slots_with_quantities and len(slots_with_quantities) > 0 and wait_seconds > 60:
            # Wait until 1 minute before
            pre_trigger_wait = wait_seconds - 60
            logger.info(f"⏰ Waiting {int(pre_trigger_wait)}s until tab opening (1 min before scheduled time)...")
            await asyncio.sleep(pre_trigger_wait)

            # Open tabs (1 minute before)
            if time_slots and len(time_slots) > 0:
                logger.info(f"🚀 Opening tabs for {len(time_slots)} slots for booking {booking_id} — sending 'trigger' to extension(s).")
                await broadcast({"type": "trigger", "url": url, "time_slots": time_slots, "booking_id": booking_id})
            else:
                logger.info(f"🚀 Opening tab for booking {booking_id} — sending 'trigger' to extension(s).")
                await broadcast({"type": "trigger", "url": url, "booking_id": booking_id})

            # Notify web clients
            if booking_id:
                broadcast_to_web({
                    "type": "booking_update",
                    "booking_id": booking_id,
                    "status": "running",
                    "message": f"🚀 Opening {len(time_slots) if time_slots else 1} tab(s) for booking..."
                })
                broadcast_to_web({
                    "type": "booking_event_log",
                    "booking_id": booking_id,
                    "message": f"🚀 Opening {len(time_slots) if time_slots else 1} tab(s) for booking...",
                    "level": "info",
                    "event_type": "booking_start"
                })

            # Wait until exact trigger time (T-0)
            logger.info("⏰ Waiting 60s until exact trigger time (T-0) for date selection...")
            await asyncio.sleep(60)

            # Send execute_booking message
            logger.info(f"🎯 TRIGGER TIME (T-0) - Sending 'execute_booking' for {len(slots_with_quantities)} slots to extension(s).")
            execute_message = {
                "type": "execute_booking",
                "booking_id": booking_id,
                "booking_date": booking_date,
                "slots_with_quantities": slots_with_quantities
            }
            await broadcast(execute_message)

            # Notify web clients
            if booking_id:
                broadcast_to_web({
                    "type": "booking_event_log",
                    "booking_id": booking_id,
                    "message": f"🎯 TRIGGER TIME (T-0): Executing booking for {len(slots_with_quantities)} slot(s)...",
                    "level": "info",
                    "event_type": "execute_booking"
                })

        else:
            # No automated booking or less than 60 seconds away - use immediate trigger
            if wait_seconds > 0:
                logger.info(f"⏰ Waiting {int(wait_seconds)} seconds until trigger time...")
                await asyncio.sleep(wait_seconds)

            # Trigger the URL opening (with login if credentials provided)
            if time_slots and len(time_slots) > 0:
                logger.info(f"🚀 Triggering multi-slot event for {len(time_slots)} slots for booking {booking_id} — sending 'trigger' to extension(s).")
                await broadcast({"type": "trigger", "url": url, "time_slots": time_slots, "booking_id": booking_id})
            else:
                logger.info(f"🚀 Triggering event for booking {booking_id} — sending 'trigger' to extension(s).")
                await broadcast({"type": "trigger", "url": url, "booking_id": booking_id})

            # If automated booking is configured, send execute_booking immediately
            if slots_with_quantities and len(slots_with_quantities) > 0:
                logger.info(f"🎯 Sending 'execute_booking' immediately for {len(slots_with_quantities)} slots to extension(s).")
                execute_message = {
                    "type": "execute_booking",
                    "booking_id": booking_id,
                    "booking_date": booking_date,
                    "slots_with_quantities": slots_with_quantities
                }
                await broadcast(execute_message)

# ==============================
# 🕓 Input Parser
# ==============================
def parse_input_line(line: str):
    """Parse user input for time, URL, email, password, optional booking_date, and slots_with_quantities

    Formats:
    - <time> <URL>
    - <time> <URL> <email> <password>
    - <time> <URL> <email> <password> <time_slots_json>
    - <time> <URL> <email> <password> <booking_date> <slots_with_quantities_json>
    """
    parts = line.strip().split(None, 5)

    # Check if we have the minimum required parameters (time and URL)
    if len(parts) < 2:
        raise ValueError("❌ Invalid input. Format: <time> <URL> [email password] [booking_date slots_with_quantities_json]")

    time_part = parts[0]
    url = parts[1]
    email = None
    password = None
    time_slots = None
    booking_date = None
    slots_with_quantities = None

    # Parse based on number of parameters
    if len(parts) == 2:
        # Old format: just time and URL (no login)
        pass
    elif len(parts) == 4:
        # Format: time, URL, email, password (no time slots)
        email = parts[2]
        password = parts[3]
    elif len(parts) == 5:
        # Format: time, URL, email, password, time_slots_json (simple time slots)
        email = parts[2]
        password = parts[3]
        time_slots_str = parts[4]

        # Parse time_slots JSON
        try:
            time_slots = json.loads(time_slots_str)

            # Validate it's a list
            if not isinstance(time_slots, list):
                raise ValueError("Time slots must be a JSON array")

            # Validate all items are strings
            if not all(isinstance(slot, str) for slot in time_slots):
                raise ValueError("All time slots must be strings")

            # Warn if too many slots
            if len(time_slots) > 10:
                logger.warning(f"⚠️ Warning: {len(time_slots)} time slots requested. This may overwhelm the browser.")

            # If empty array, treat as None (fall back to single tab)
            if len(time_slots) == 0:
                logger.info("ℹ️ Empty time slots array - will open single tab")
                time_slots = None

        except json.JSONDecodeError as e:
            raise ValueError(f"❌ Invalid JSON format for time_slots: {e}")
    elif len(parts) == 6:
        # New format: time, URL, email, password, booking_date, slots_with_quantities_json
        email = parts[2]
        password = parts[3]
        booking_date = parts[4].strip('"')  # Remove quotes if present
        slots_with_quantities_str = parts[5]

        # Validate booking_date format (YYYY-MM-DD)
        try:
            from datetime import datetime as dt
            dt.strptime(booking_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"❌ Invalid booking_date format. Expected YYYY-MM-DD, got: {booking_date}")

        # Parse slots_with_quantities JSON
        try:
            slots_with_quantities = json.loads(slots_with_quantities_str)

            # Validate it's a list
            if not isinstance(slots_with_quantities, list):
                raise ValueError("Slots with quantities must be a JSON array")

            # Validate each item is an object with 'time' and 'quantity' fields
            for i, slot in enumerate(slots_with_quantities):
                if not isinstance(slot, dict):
                    raise ValueError(f"Slot {i+1} must be an object with 'time' and 'quantity' fields")
                if 'time' not in slot or 'quantity' not in slot:
                    raise ValueError(f"Slot {i+1} must have 'time' and 'quantity' fields")
                if not isinstance(slot['time'], str):
                    raise ValueError(f"Slot {i+1}: 'time' must be a string")
                if not isinstance(slot['quantity'], int) or slot['quantity'] < 1:
                    raise ValueError(f"Slot {i+1}: 'quantity' must be a positive integer")

            # Warn if too many slots
            if len(slots_with_quantities) > 10:
                logger.warning(f"⚠️ Warning: {len(slots_with_quantities)} time slots requested. This may overwhelm the browser.")

            # If empty array, treat as None
            if len(slots_with_quantities) == 0:
                logger.info("ℹ️ Empty slots array - will open single tab")
                slots_with_quantities = None
            else:
                # Extract time slots for tab opening
                time_slots = [slot['time'] for slot in slots_with_quantities]

        except json.JSONDecodeError as e:
            raise ValueError(f"❌ Invalid JSON format for slots_with_quantities: {e}")
    else:
        raise ValueError("❌ Invalid input. Format: <time> <URL> [email password] [booking_date slots_with_quantities_json]")

    # Parse time
    time_part = time_part.strip().lower()
    now = datetime.now(LOCAL_TZ)

    if time_part == "now":
        target_time = now
    elif time_part.startswith("+"):
        try:
            minutes = int(time_part[1:])
            if minutes < 0:
                raise ValueError("❌ Minutes must be positive")
            target_time = now + timedelta(minutes=minutes)
        except ValueError as e:
            raise ValueError(f"❌ Invalid time format '+N': {e}")
    else:
        try:
            hour, minute = map(int, time_part.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("❌ Invalid time: hour must be 0-23, minute must be 0-59")
            target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)
        except ValueError as e:
            raise ValueError(f"❌ Invalid time format 'HH:MM': {e}")

    return target_time, url, email, password, time_slots, booking_date, slots_with_quantities

# ==============================
# 🚀 WebSocket Server
# ==============================
async def start_websocket_server():
    """Start the WebSocket server"""
    logger.info(f"🛰️ Starting WebSocket server at ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT} ...")
    try:
        # Get WebSocket configuration from environment
        max_size = int(os.getenv("MAX_MESSAGE_SIZE", "1048576"))  # 1MB default
        ping_interval = int(os.getenv("PING_INTERVAL", "20"))
        ping_timeout = int(os.getenv("PING_TIMEOUT", "20"))

        async with websockets.serve(
            handler,
            WEBSOCKET_HOST,
            WEBSOCKET_PORT,
            max_size=max_size,
            ping_interval=ping_interval,
            ping_timeout=ping_timeout
        ):
            logger.info(f"✅ WebSocket server ready on {WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
            await asyncio.Future()  # Keeps running forever
    except OSError as e:
        logger.error(f"❌ Failed to start WebSocket server: {e}")
        logger.error(f"Make sure port {WEBSOCKET_PORT} is not already in use.")
        raise

# ==============================
# 🧑‍💻 CLI Task
# ==============================
async def cli_task():
    """Handle user input from command line"""
    print("\n" + "="*70)
    print("🤖 HYBRID AUTOMATION BOT WITH AUTO-LOGIN")
    print("="*70)
    print(f"\n🌐 WEB INTERFACE: http://{FLASK_HOST}:{FLASK_PORT}")
    print("   Open this URL in your browser for the web interface")
    print("="*70)
    print("\n📋 Usage examples:")
    print("  Basic (no login):")
    print("    now https://www.google.com")
    print("    +2 https://www.example.com")
    print("    15:45 https://github.com")
    print("\n  With Auto-Login:")
    print("    now https://site.com user@email.com password123")
    print("    +5 https://site.com user@email.com password123")
    print("    14:30 https://site.com user@email.com password123")
    print("\n  With Multi-Slot Booking:")
    print('    +3 https://site.com user@email.com pass123 ["8:15 AM", "8:30 AM"]')
    print('    14:00 https://site.com user@email.com pass123 ["8:15 AM", "11:00 AM", "2:30 PM"]')
    print("\n  With Automated Booking (date + quantities):")
    print('    +3 https://recreation.gov/... user@email.com pass "2025-11-13" [{"time":"8:15 AM","quantity":2}]')
    print('    14:00 https://recreation.gov/... user@email.com pass "2025-11-13" [{"time":"8:15 AM","quantity":2},{"time":"8:30 AM","quantity":1}]')
    print("\n💡 Commands:")
    print("  status  - Show connected clients")
    print("  exit    - Quit the bot")
    print("\n⚠️  SECURITY WARNING:")
    print("  Credentials are transmitted via WebSocket and stored temporarily.")
    print("  Only use on trusted networks and devices.")
    print("="*70 + "\n")

    while True:
        try:
            line = await asyncio.to_thread(input, "⚡ > ")
            line = line.strip()

            if not line:
                continue

            if line.lower() == "exit":
                logger.info("👋 Exiting bot...")
                break

            if line.lower() == "status":
                total_extensions = len(connected_clients) + len(extension_clients)
                logger.info(f"📊 Connected extension clients: {total_extensions}")

                if connected_clients:
                    logger.info(f"  Standalone WebSocket (port 8765): {len(connected_clients)}")
                    for i, client in enumerate(connected_clients, 1):
                        logger.info(f"    {i}. {client.remote_address}")

                if extension_clients:
                    logger.info(f"  Flask-Sock (/ws endpoint): {len(extension_clients)}")

                if web_clients:
                    logger.info(f"  Web interface clients: {len(web_clients)}")

                if total_extensions == 0 and len(web_clients) == 0:
                    logger.info("  No clients connected")
                continue

            target_time, url, email, password, time_slots, booking_date, slots_with_quantities = parse_input_line(line)
            asyncio.create_task(schedule_and_trigger(target_time, url, email, password, time_slots, booking_date, slots_with_quantities))

            if booking_date and slots_with_quantities:
                logger.info(f"✅ Automated booking task scheduled with {len(slots_with_quantities)} slot(s) for {booking_date}")
            elif time_slots and len(time_slots) > 0:
                logger.info(f"✅ Multi-slot task scheduled successfully with {len(time_slots)} time slots")
            elif email and password:
                logger.info(f"✅ Task scheduled successfully with auto-login for {email}")
            else:
                logger.info(f"✅ Task scheduled successfully")

        except ValueError as e:
            logger.error(str(e))
        except KeyboardInterrupt:
            logger.info("\n👋 Exiting bot...")
            break
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")

# ==============================
# 🏁 Entry Point
# ==============================
async def main():
    """Main entry point - runs WebSocket server, Flask server, and CLI concurrently"""
    global main_event_loop

    try:
        # Store reference to the main event loop for Flask thread
        main_event_loop = asyncio.get_running_loop()

        # Start Flask server in a separate thread
        flask_thread = Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info(f"🌐 Flask web server starting on http://{FLASK_HOST}:{FLASK_PORT}")

        tasks = []

        # Only start standalone WebSocket server if enabled (for local development)
        if ENABLE_STANDALONE_WEBSOCKET and not IS_PRODUCTION:
            logger.info(f"🔌 Starting standalone WebSocket server on port {WEBSOCKET_PORT}")
            server_task = asyncio.create_task(start_websocket_server())
            tasks.append(server_task)
        else:
            if IS_PRODUCTION:
                logger.info("🌐 Production mode: Using Flask-Sock for WebSocket (port 8765 disabled)")
                logger.info(f"📡 WebSocket available at: wss://your-domain/ws")
            else:
                logger.info("💡 Standalone WebSocket disabled. Using Flask-Sock only.")
                logger.info(f"📡 WebSocket available at: ws://{FLASK_HOST}:{FLASK_PORT}/ws")

        # Start CLI task (only if not in production)
        if not IS_PRODUCTION:
            cli_task_obj = asyncio.create_task(cli_task())
            tasks.append(cli_task_obj)
        else:
            logger.info("🚀 Production mode: CLI disabled, running as web service")
            # In production, just keep running forever
            await asyncio.Future()  # Run forever

        # If we have tasks (local development), wait for them
        if tasks:
            _, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        logger.info("✅ Bot shutdown complete")

    except KeyboardInterrupt:
        logger.info("\n⚠️ Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise

if __name__ == "__main__":
    logger.info("🕓 Bot starting ...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Goodbye!")
    except Exception as e:
        logger.error(f"❌ Failed to start: {e}")
