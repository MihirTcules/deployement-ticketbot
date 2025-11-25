"""
Booking storage management module for Recreation.gov Booking Bot
Handles persistent storage of scheduled bookings in JSON file
"""

import json
import os
import fcntl
import logging
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Get data directory from environment variable or use current directory
DATA_DIR = os.getenv("DATA_DIR", ".")

# Ensure data directory exists
if not os.path.exists(DATA_DIR):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        logger.info(f"📁 Created data directory: {DATA_DIR}")
    except Exception as e:
        logger.warning(f"⚠️ Could not create data directory {DATA_DIR}: {e}")
        logger.warning("⚠️ Using current directory for data storage")
        DATA_DIR = "."

BOOKINGS_FILE = os.path.join(DATA_DIR, "scheduled_bookings.json")
BACKUP_FILE = os.path.join(DATA_DIR, "scheduled_bookings.backup.json")

# Warn if using /tmp (data will be lost on restart)
if DATA_DIR == "/tmp":
    logger.warning("⚠️ Using /tmp for bookings - data will be lost on restart!")
    logger.warning("⚠️ For persistent storage, upgrade to a paid Render plan with disk storage")


class BookingStorage:
    """Manages persistent storage of scheduled bookings"""
    
    def __init__(self, bookings_file: str = BOOKINGS_FILE):
        self.bookings_file = bookings_file
        self.backup_file = BACKUP_FILE
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Create bookings file if it doesn't exist"""
        if not os.path.exists(self.bookings_file):
            self._write_bookings({"bookings": []})
            logger.info(f"📁 Created new bookings file: {self.bookings_file}")
    
    @contextmanager
    def _file_lock(self, file_handle, lock_type=fcntl.LOCK_EX):
        """Context manager for file locking"""
        try:
            fcntl.flock(file_handle, lock_type)
            yield file_handle
        finally:
            fcntl.flock(file_handle, fcntl.LOCK_UN)
    
    def _read_bookings(self) -> Dict:
        """Read bookings from JSON file with file locking"""
        try:
            with open(self.bookings_file, 'r') as f:
                with self._file_lock(f, fcntl.LOCK_SH):
                    data = json.load(f)
                    return data
        except json.JSONDecodeError as e:
            logger.error(f"❌ Corrupted JSON in bookings file: {e}")
            return self._recover_from_backup()
        except FileNotFoundError:
            logger.warning("⚠️  Bookings file not found, creating new one")
            self._ensure_file_exists()
            return {"bookings": []}
        except Exception as e:
            logger.error(f"❌ Error reading bookings file: {e}")
            return {"bookings": []}
    
    def _write_bookings(self, data: Dict):
        """Write bookings to JSON file with file locking and backup"""
        try:
            # Create backup before writing
            if os.path.exists(self.bookings_file):
                with open(self.bookings_file, 'r') as src:
                    with open(self.backup_file, 'w') as dst:
                        dst.write(src.read())
            
            # Write new data
            with open(self.bookings_file, 'w') as f:
                with self._file_lock(f):
                    json.dump(data, f, indent=2)
            
            logger.debug(f"✅ Bookings saved to {self.bookings_file}")
        except Exception as e:
            logger.error(f"❌ Error writing bookings file: {e}")
            raise
    
    def _recover_from_backup(self) -> Dict:
        """Recover bookings from backup file"""
        try:
            if os.path.exists(self.backup_file):
                logger.info("🔄 Attempting to recover from backup file")
                with open(self.backup_file, 'r') as f:
                    data = json.load(f)
                # Restore from backup
                self._write_bookings(data)
                logger.info("✅ Successfully recovered from backup")
                return data
        except Exception as e:
            logger.error(f"❌ Failed to recover from backup: {e}")
        
        # If recovery fails, return empty structure
        return {"bookings": []}
    
    def get_all_bookings(self) -> List[Dict]:
        """Get all bookings"""
        data = self._read_bookings()
        return data.get("bookings", [])
    
    def get_booking(self, booking_id: str) -> Optional[Dict]:
        """Get a specific booking by ID"""
        bookings = self.get_all_bookings()
        for booking in bookings:
            if booking.get("id") == booking_id:
                return booking
        return None
    
    def save_booking(self, booking: Dict) -> bool:
        """Save a new booking"""
        try:
            data = self._read_bookings()
            bookings = data.get("bookings", [])

            # Check for duplicate ID
            booking_id = booking.get('id')
            if any(b.get('id') == booking_id for b in bookings):
                logger.warning(f"⚠️  Booking {booking_id} already exists, skipping duplicate save")
                return False

            # Add timestamps
            now = datetime.now().isoformat()
            booking["created_at"] = now
            booking["updated_at"] = now

            # Initialize logs if not present
            if "logs" not in booking:
                booking["logs"] = []

            bookings.append(booking)
            data["bookings"] = bookings

            self._write_bookings(data)
            logger.info(f"✅ Saved booking {booking.get('id')}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save booking: {e}")
            return False

    def update_booking(self, booking_id: str, updates: Dict) -> bool:
        """Update an existing booking"""
        try:
            data = self._read_bookings()
            bookings = data.get("bookings", [])

            # Find and update the booking
            found = False
            for i, booking in enumerate(bookings):
                if booking.get("id") == booking_id:
                    # Update fields
                    for key, value in updates.items():
                        booking[key] = value

                    # Update timestamp
                    booking["updated_at"] = datetime.now().isoformat()

                    bookings[i] = booking
                    found = True
                    break

            if not found:
                logger.warning(f"⚠️  Booking {booking_id} not found for update")
                return False

            data["bookings"] = bookings
            self._write_bookings(data)
            logger.info(f"✅ Updated booking {booking_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to update booking: {e}")
            return False

    def delete_booking(self, booking_id: str) -> bool:
        """Delete a booking"""
        try:
            data = self._read_bookings()
            bookings = data.get("bookings", [])

            # Filter out the booking to delete
            original_count = len(bookings)
            bookings = [b for b in bookings if b.get("id") != booking_id]

            if len(bookings) == original_count:
                logger.warning(f"⚠️  Booking {booking_id} not found for deletion")
                return False

            data["bookings"] = bookings
            self._write_bookings(data)
            logger.info(f"✅ Deleted booking {booking_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete booking: {e}")
            return False

    def add_log_to_booking(self, booking_id: str, log_entry: Dict) -> bool:
        """Add a log entry to a booking"""
        try:
            data = self._read_bookings()
            bookings = data.get("bookings", [])

            # Find the booking and add log
            found = False
            for i, booking in enumerate(bookings):
                if booking.get("id") == booking_id:
                    if "logs" not in booking:
                        booking["logs"] = []

                    # Add timestamp if not present
                    if "timestamp" not in log_entry:
                        log_entry["timestamp"] = datetime.now().isoformat()

                    booking["logs"].append(log_entry)
                    booking["updated_at"] = datetime.now().isoformat()

                    bookings[i] = booking
                    found = True
                    break

            if not found:
                logger.warning(f"⚠️  Booking {booking_id} not found for log addition")
                return False

            data["bookings"] = bookings
            self._write_bookings(data)
            logger.debug(f"✅ Added log to booking {booking_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to add log to booking: {e}")
            return False

    def clear_all_bookings(self) -> bool:
        """Clear all bookings (for testing/reset)"""
        try:
            self._write_bookings({"bookings": []})
            logger.info("🗑️  Cleared all bookings")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to clear bookings: {e}")
            return False


# Global instance
booking_storage = BookingStorage()

