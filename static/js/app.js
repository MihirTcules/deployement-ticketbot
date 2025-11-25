// Global state
let ws = null;
let activeBookings = [];
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
let datePicker = null;
let currentConfig = null;
let calendar = null;
let miniCalendar = null;
let selectedDate = null;
let bookingLogsById = {};
let selectedBookingId = null;
let currentMiniMonth = new Date();
let currentMiniYear = new Date().getFullYear();


// Common time slots (15-minute intervals from 8:00 AM to 3:00 PM)
const TIME_SLOTS = [
  "8:00 AM",
  "8:15 AM",
  "8:30 AM",
  "8:45 AM",
  "9:00 AM",
  "9:15 AM",
  "9:30 AM",
  "9:45 AM",
  "10:00 AM",
  "10:15 AM",
  "10:30 AM",
  "10:45 AM",
  "11:00 AM",
  "11:15 AM",
  "11:30 AM",
  "11:45 AM",
  "12:00 PM",
  "12:15 PM",
  "12:30 PM",
  "12:45 PM",
  "1:00 PM",
  "1:15 PM",
  "1:30 PM",
  "1:45 PM",
  "2:00 PM",
  "2:15 PM",
  "2:30 PM",
  "2:45 PM",
  "3:00 PM",
];

// Initialize on page load
document.addEventListener("DOMContentLoaded", async () => {
  connectWebSocket();
  setupFormHandlers();
  setupDateTimePicker();
  setupTimeSlotsGrid();
  setupCalendar();
  setupMiniCalendar();
  loadConfiguration();
  setupConfigHandlers();

  // Load bookings from server
  await loadBookingsFromServer();
});

// Expose debug functions to window for console access (for troubleshooting)
window.debugCalendar = function() {
  console.log("🔍 ========== CALENDAR DEBUG INFO ==========");
  console.log("Calendar initialized:", !!calendar);
  console.log("Calendar object:", calendar);
  console.log("Active bookings count:", activeBookings.length);
  console.log("Active bookings:", activeBookings);
  console.log("Calendar events count:", calendar ? calendar.getEvents().length : 0);
  console.log("Calendar events:", calendar ? calendar.getEvents() : []);
  console.log("🔍 ========================================");
};

window.forceRenderEvents = function() {
  console.log("🔄 Forcing event render...");
  renderCalendarEvents();
};

// WebSocket Connection
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  addLog("Connecting to bot...", "info");
  updateConnectionStatus("connecting");

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    addLog("Connected to bot successfully", "success");
    updateConnectionStatus("connected");
    reconnectAttempts = 0;

    // Send hello message
    sendMessage({ type: "web_hello", timestamp: new Date().toISOString() });
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleServerMessage(data);
    } catch (error) {
      console.error("Failed to parse message:", error);
    }
  };

  ws.onerror = (error) => {
    console.error("WebSocket error:", error);
    addLog("Connection error", "error");
  };

  ws.onclose = () => {
    addLog("Disconnected from bot", "warning");
    updateConnectionStatus("disconnected");

    // Attempt to reconnect
    if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
      reconnectAttempts++;
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
      addLog(
        `Reconnecting in ${
          delay / 1000
        }s... (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`,
        "info"
      );
      setTimeout(connectWebSocket, delay);
    } else {
      addLog("Failed to reconnect. Please refresh the page.", "error");
    }
  };
}

// Send message to server
function sendMessage(data) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data));
  } else {
    showToast("Not connected to bot", "error");
  }
}

// Handle messages from server
function handleServerMessage(data) {
  console.log("Received:", data);

  switch (data.type) {
    case "welcome":
      addLog(data.message, "success");
      break;

    case "booking_scheduled":
      console.log("📅 BOOKING_SCHEDULED received:", data);
      console.log("📅 Booking data:", data.booking);
      addLog(`Booking scheduled: ${data.booking_id}`, "success");
      showToast("Booking scheduled successfully!", "success");
      // Don't save to server - backend already saved it
      addBookingToList(data.booking, false);
      // Don't save log to server - backend already saved it
      addBookingLog(data.booking.id, "Booking scheduled", "success", false);
      break;

    case "booking_update":
      // Don't update on server - backend already persisted via _persist_booking_message()
      const booking = activeBookings.find((b) => b.id === data.booking_id);
      if (booking) {
        booking.status = data.status;
        booking.message = data.message;
        renderBookings();
        renderSidebarBookings();
        renderCalendarEvents();
      }
      // Determine log level based on booking status
      let logLevel = "info";
      if (data.status === "completed") {
        logLevel = "success";
      } else if (data.status === "failed") {
        logLevel = "error";
      } else if (data.status === "running") {
        logLevel = "info";
      }
      addLog(data.message, logLevel);
      // Don't save log to server - backend already saved it
      addBookingLog(data.booking_id, data.message, logLevel, false);
      break;

    case "booking_event_log":
      // Event-specific log message
      if (data.booking_id) {
        // Don't save log to server - backend already saved it
        addBookingLog(data.booking_id, data.message, data.level || "info", false);
      }
      break;

    case "log":
      addLog(data.message, data.level || "info");
      break;

    case "error":
      addLog(`Error: ${data.message}`, "error");
      showToast(data.message, "error");
      break;

    default:
      console.log("Unknown message type:", data.type);
  }
}

// Update WebSocket connection status (shown in Settings modal)
function updateConnectionStatus(status) {
  const botIndicator = document.getElementById("botStatusIndicator");
  const botText = document.getElementById("botStatusText");

  if (!botIndicator || !botText) return;

  botIndicator.className = "bot-status-indicator";
  botText.className = "bot-status-text";

  switch (status) {
    case "connected":
      botIndicator.classList.add("connected");
      botText.classList.add("connected");
      botText.innerHTML = "You’re online — good to go";
      break;
    case "connecting":
      botText.innerHTML = "Connecting to bot...";
      break;
    case "disconnected":
      botIndicator.classList.add("disconnected");
      botText.classList.add("disconnected");
      botText.innerHTML = "Offline. The bot will resume once you’re back online";
      break;
  }

  // Also update password status on main screen
  updatePasswordStatus();
}

// Update password save status (shown on Main screen)
function updatePasswordStatus() {
  console.log("🔐 updatePasswordStatus() called");

  const indicator = document.getElementById("statusIndicator");
  const text = document.getElementById("statusText");

  if (!indicator || !text) {
    console.warn("⚠️  Status indicator or text element not found");
    return;
  }

  // Check if password is saved in configuration
  // Backend returns '********' when password exists (masked for security)
  // Empty string or no password field means no password saved
  const passwordExists = currentConfig &&
                         currentConfig.password &&
                         currentConfig.password !== "";

  console.log("   - currentConfig:", currentConfig);
  console.log("   - currentConfig.password:", currentConfig ? currentConfig.password : "N/A");
  console.log("   - passwordExists:", passwordExists);

  indicator.className = "status-indicator";

  if (passwordExists) {
    indicator.classList.add("connected");
    text.textContent = "connected";
    console.log("   ✅ Status: Password Saved");
  } else {
    indicator.classList.add("disconnected");
    text.textContent = "disconnected";
    console.log("   ❌ Status: Password Not Saved");
  }
}

// Legacy function name for backward compatibility - now updates password status
function updateBotStatus() {
  updatePasswordStatus();
}

// Form Handlers
function setupFormHandlers() {
  const form = document.getElementById("bookingForm");
  form.addEventListener("submit", handleFormSubmit);
}

function handleFormSubmit(e) {
  e.preventDefault();

  // Get form values
  const url = document.getElementById("url").value.trim();
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;
  const bookingDate = document.getElementById("bookingDate").value.trim();
  const triggerDateTimeInput = document.getElementById("triggerDateTime").value.trim();

  // Validate trigger datetime format
  if (triggerDateTimeInput.length !== 16) {
    alert("Please enter a complete date and time (DD/MM/YYYY HH:MM)");
    return;
  }

  // Convert to backend format
  const triggerDateTime = convertToBackendFormat(triggerDateTimeInput);
  if (!triggerDateTime) {
    alert("Invalid date/time format. Please use DD/MM/YYYY HH:MM");
    return;
  }

  // Store the converted value in hidden field for reference
  const hiddenField = document.getElementById("triggerDateTimeFormatted");
  if (hiddenField) {
    hiddenField.value = triggerDateTime;
  }

  // Get selected time slots from checkboxes
  const timeSlots = [];
  const checkboxes = document.querySelectorAll(".slot-checkbox:checked");
  console.log("Found checked checkboxes:", checkboxes.length);

  checkboxes.forEach((checkbox) => {
    const slotItem = checkbox.closest(".time-slot-item");
    const quantityInput = slotItem ? slotItem.querySelector(".slot-quantity-input") : null;
    const time = checkbox.dataset.time;
    const quantity = quantityInput ? parseInt(quantityInput.value) : 0;

    console.log("Processing slot:", { time, quantity, hasSlotItem: !!slotItem, hasQuantityInput: !!quantityInput });

    if (time && quantity > 0) {
      timeSlots.push({ time, quantity });
    }
  });

  console.log("Final timeSlots array:", timeSlots);

  // Validate
  if (!url) {
    showToast("URL is required", "error");
    return;
  }
  if (!email) {
    showToast("Email is required", "error");
    return;
  }
  if (!password) {
    showToast("Password is required", "error");
    return;
  }
  if (!bookingDate) {
    showToast("Booking date is required - please select a date on the calendar", "error");
    return;
  }
  if (!triggerDateTime) {
    showToast("Trigger date & time is required", "error");
    return;
  }
  if (timeSlots.length === 0) {
    showToast("Please select at least one time slot with quantity", "error");
    return;
  }

  // Send booking request with combined datetime
  const bookingData = {
    type: "schedule_booking",
    url,
    email,
    password,
    booking_date: bookingDate,
    trigger_datetime: triggerDateTime, // Combined date and time
    time_slots: timeSlots,
  };

  sendMessage(bookingData);
  addLog("Sending booking request...", "info");

  // Close side panel and reset form
  closeBookingSidePanel();
  resetFormAfterSubmit();
}

/**
 * Reset form after submission while preserving auto-filled fields
 */
function resetFormAfterSubmit() {
  // Save auto-filled field values before reset
  const urlInput = document.getElementById("url");
  const emailInput = document.getElementById("email");
  const passwordInput = document.getElementById("password");

  const savedValues = {
    url: urlInput.classList.contains("auto-filled") ? urlInput.value : "",
    email: emailInput.classList.contains("auto-filled") ? emailInput.value : "",
    password: passwordInput.classList.contains("auto-filled")
      ? passwordInput.value
      : "",
  };

  // Clear date picker
  if (datePicker) datePicker.clear();

  // Reset time slots
  resetTimeSlots();

  // Clear booking date and trigger datetime fields
  const bookingDateInput = document.getElementById("bookingDate");
  const triggerDateTimeInput = document.getElementById("triggerDateTime");
  const triggerDateTimeFormatted = document.getElementById("triggerDateTimeFormatted");
  const triggerDateTimeError = document.getElementById("triggerDateTimeError");

  if (bookingDateInput) bookingDateInput.value = "";
  if (triggerDateTimeInput) {
    triggerDateTimeInput.value = "";
    triggerDateTimeInput.classList.remove("invalid", "valid");
  }
  if (triggerDateTimeFormatted) triggerDateTimeFormatted.value = "";
  if (triggerDateTimeError) triggerDateTimeError.style.display = "none";

  // Reset selected date
  selectedDate = null;

  // Restore auto-filled fields
  if (savedValues.url) {
    urlInput.value = savedValues.url;
    urlInput.classList.add("auto-filled");
  } else {
    urlInput.value = "";
    urlInput.classList.remove("auto-filled");
  }

  if (savedValues.email) {
    emailInput.value = savedValues.email;
    emailInput.classList.add("auto-filled");
  } else {
    emailInput.value = "";
    emailInput.classList.remove("auto-filled");
  }

  if (savedValues.password) {
    passwordInput.value = savedValues.password;
    passwordInput.classList.add("auto-filled");
  } else {
    passwordInput.value = "";
    passwordInput.classList.remove("auto-filled");
  }
}

// Date Picker Setup
function setupDatePicker() {
  datePicker = flatpickr("#bookingDate", {
    dateFormat: "F j, Y",
    minDate: "today",
    disableMobile: false,
    allowInput: false,
    clickOpens: true,
    onChange: function (selectedDates, dateStr, instance) {
      console.log("Date selected:", dateStr);
    },
    onReady: function (selectedDates, dateStr, instance) {
      // Remove year navigation arrows
      const yearInput = instance.currentYearElement;
      if (yearInput) {
        // Find and remove the arrow buttons
        const arrowUp = yearInput.parentElement.querySelector(".arrowUp");
        const arrowDown = yearInput.parentElement.querySelector(".arrowDown");

        if (arrowUp) {
          arrowUp.remove();
        }
        if (arrowDown) {
          arrowDown.remove();
        }

        // Make year input editable
        yearInput.removeAttribute("readonly");
        yearInput.style.cursor = "text";
      }
    },
  });
}

// DateTime Picker Setup (combined date and time picker)
// Setup auto-formatting for trigger datetime input
function setupDateTimePicker() {
  const input = document.getElementById("triggerDateTime");
  const errorElement = document.getElementById("triggerDateTimeError");

  if (!input) return;

  // Handle input event for auto-formatting
  input.addEventListener("input", function (e) {
    const cursorPosition = this.selectionStart;
    const oldValue = this.value;
    const oldLength = oldValue.length;

    // Remove all non-digit characters
    let digitsOnly = this.value.replace(/\D/g, "");

    // Limit to 12 digits (DDMMYYYYHHMM)
    digitsOnly = digitsOnly.substring(0, 12);

    // Format the digits
    let formatted = formatDateTimeInput(digitsOnly);

    // Update the input value
    this.value = formatted;

    // Calculate new cursor position
    const newLength = formatted.length;
    let newCursorPosition = cursorPosition;

    // If we added characters (formatting), adjust cursor
    if (newLength > oldLength) {
      // Check if we just added a separator
      const addedChars = newLength - oldLength;
      if (addedChars > 1) {
        newCursorPosition = cursorPosition + addedChars - 1;
      } else {
        newCursorPosition = cursorPosition + addedChars;
      }
    }

    // Set cursor position
    this.setSelectionRange(newCursorPosition, newCursorPosition);

    // Validate the input
    validateDateTimeInput(formatted);
  });

  // Handle keydown for better backspace handling
  input.addEventListener("keydown", function (e) {
    if (e.key === "Backspace") {
      const cursorPosition = this.selectionStart;
      const value = this.value;

      // If cursor is right after a separator, delete the digit before it
      if (
        cursorPosition > 0 &&
        (value[cursorPosition - 1] === "/" ||
          value[cursorPosition - 1] === " " ||
          value[cursorPosition - 1] === ":")
      ) {
        e.preventDefault();
        const digitsOnly = value.replace(/\D/g, "");
        const newDigits = digitsOnly.substring(0, digitsOnly.length - 1);
        this.value = formatDateTimeInput(newDigits);
        validateDateTimeInput(this.value);
      }
    }
  });

  // Handle paste event
  input.addEventListener("paste", function (e) {
    e.preventDefault();
    const pastedText = (e.clipboardData || window.clipboardData).getData("text");
    const digitsOnly = pastedText.replace(/\D/g, "");
    this.value = formatDateTimeInput(digitsOnly.substring(0, 12));
    validateDateTimeInput(this.value);
  });

  // Clear error on focus
  input.addEventListener("focus", function () {
    if (errorElement) {
      errorElement.style.display = "none";
    }
  });
}

// Format datetime input as user types
// Input: digits only (e.g., "251220251430")
// Output: formatted string (e.g., "25/12/2025 14:30")
function formatDateTimeInput(digits) {
  let formatted = "";

  // Add day (DD)
  if (digits.length >= 1) {
    formatted += digits.substring(0, Math.min(2, digits.length));
  }

  // Add first slash after day
  if (digits.length >= 3) {
    formatted += "/" + digits.substring(2, Math.min(4, digits.length));
  }

  // Add second slash after month
  if (digits.length >= 5) {
    formatted += "/" + digits.substring(4, Math.min(8, digits.length));
  }

  // Add space after year
  if (digits.length >= 9) {
    formatted += " " + digits.substring(8, Math.min(10, digits.length));
  }

  // Add colon after hour
  if (digits.length >= 11) {
    formatted += ":" + digits.substring(10, Math.min(12, digits.length));
  }

  return formatted;
}

// Validate datetime input
function validateDateTimeInput(value) {
  const input = document.getElementById("triggerDateTime");
  const errorElement = document.getElementById("triggerDateTimeError");

  if (!input || !errorElement) return;

  // Clear previous validation state
  input.classList.remove("invalid", "valid");
  errorElement.style.display = "none";
  errorElement.textContent = "";

  // If empty or incomplete, don't show error
  if (value.length < 16) {
    return;
  }

  // Parse the input (DD/MM/YYYY HH:MM)
  const match = value.match(/^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})$/);

  if (!match) {
    showDateTimeError("Invalid format. Use DD/MM/YYYY HH:MM");
    return;
  }

  const day = parseInt(match[1]);
  const month = parseInt(match[2]);
  const year = parseInt(match[3]);
  const hour = parseInt(match[4]);
  const minute = parseInt(match[5]);

  // Validate day
  if (day < 1 || day > 31) {
    showDateTimeError("Day must be between 01 and 31");
    return;
  }

  // Validate month
  if (month < 1 || month > 12) {
    showDateTimeError("Month must be between 01 and 12");
    return;
  }

  // Validate year (current year or future)
  const currentYear = new Date().getFullYear();
  if (year < currentYear) {
    showDateTimeError(`Year must be ${currentYear} or later`);
    return;
  }

  // Validate hour
  if (hour < 0 || hour > 23) {
    showDateTimeError("Hour must be between 00 and 23");
    return;
  }

  // Validate minute
  if (minute < 0 || minute > 59) {
    showDateTimeError("Minute must be between 00 and 59");
    return;
  }

  // Validate the date is valid (e.g., not 31/02/2025)
  const date = new Date(year, month - 1, day);
  if (
    date.getDate() !== day ||
    date.getMonth() !== month - 1 ||
    date.getFullYear() !== year
  ) {
    showDateTimeError("Invalid date (e.g., day doesn't exist in that month)");
    return;
  }

  // Validate date is not in the past
  const now = new Date();
  const inputDate = new Date(year, month - 1, day, hour, minute);
  if (inputDate < now) {
    showDateTimeError("Date and time must be in the future");
    return;
  }

  // All validations passed
  input.classList.add("valid");
}

// Show datetime validation error
function showDateTimeError(message) {
  const input = document.getElementById("triggerDateTime");
  const errorElement = document.getElementById("triggerDateTimeError");

  if (input) {
    input.classList.add("invalid");
    input.classList.remove("valid");
  }

  if (errorElement) {
    errorElement.textContent = message;
    errorElement.style.display = "block";
  }
}

// Convert DD/MM/YYYY HH:MM to backend format (Month Day, Year Hour:Minute)
function convertToBackendFormat(formattedInput) {
  // Parse the input (DD/MM/YYYY HH:MM)
  const match = formattedInput.match(/^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})$/);

  if (!match) {
    return null;
  }

  const day = parseInt(match[1]);
  const month = parseInt(match[2]);
  const year = parseInt(match[3]);
  const hour = match[4];
  const minute = match[5];

  // Month names
  const monthNames = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
  ];

  // Convert to backend format: "December 25, 2025 14:30"
  const monthName = monthNames[month - 1];
  return `${monthName} ${day}, ${year} ${hour}:${minute}`;
}

// Time Slots Grid Setup
function setupTimeSlotsGrid() {
  const grid = document.getElementById("timeSlotsGrid");
  grid.innerHTML = "";

  TIME_SLOTS.forEach((timeSlot) => {
    const slotItem = document.createElement("div");
    slotItem.className = "time-slot-item";
    slotItem.innerHTML = `
            <div class="slot-checkbox-wrapper">
                <input type="checkbox" class="slot-checkbox" id="slot-${timeSlot.replace(
                  /[:\s]/g,
                  ""
                )}" data-time="${timeSlot}">
                <label class="slot-time-label" for="slot-${timeSlot.replace(
                  /[:\s]/g,
                  ""
                )}">${timeSlot}</label>
            </div>
            <div class="slot-quantity-wrapper">
                <label class="slot-quantity-label">Qty:</label>
                <input type="number" class="slot-quantity-input" min="1" value="1" disabled>
            </div>
        `;
    grid.appendChild(slotItem);

    // Add event listener to checkbox
    const checkbox = slotItem.querySelector(".slot-checkbox");
    const quantityInput = slotItem.querySelector(".slot-quantity-input");

    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        slotItem.classList.add("selected");
        quantityInput.disabled = false;
      } else {
        slotItem.classList.remove("selected");
        quantityInput.disabled = true;
      }
    });

    // Fix arrow key behavior for quantity input
    // UP arrow should DECREASE, DOWN arrow should INCREASE
    quantityInput.addEventListener("keydown", (e) => {
      if (e.key === "ArrowUp") {
        e.preventDefault();
        const currentValue = parseInt(quantityInput.value) || 1;
        if (currentValue > 1) {
          quantityInput.value = currentValue - 1;
        }
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        const currentValue = parseInt(quantityInput.value) || 1;
        quantityInput.value = currentValue + 1;
      }
    });

    // Add event listener to label for better UX
    const label = slotItem.querySelector(".slot-time-label");
    label.addEventListener("click", () => {
      checkbox.checked = !checkbox.checked;
      checkbox.dispatchEvent(new Event("change"));
    });
  });
}

function resetTimeSlots() {
  // Uncheck all checkboxes and reset quantities
  const checkboxes = document.querySelectorAll(".slot-checkbox");
  checkboxes.forEach((checkbox) => {
    checkbox.checked = false;
    const slotItem = checkbox.closest(".time-slot-item");
    slotItem.classList.remove("selected");
    const quantityInput = slotItem.querySelector(".slot-quantity-input");
    quantityInput.value = 1;
    quantityInput.disabled = true;
  });
}

// Bookings Management
function addBookingToList(booking, saveToServer = true) {
  console.log("➕ addBookingToList called with booking:", booking);
  console.log("➕ Current activeBookings count:", activeBookings.length);
  activeBookings.push(booking);
  console.log("➕ New activeBookings count:", activeBookings.length);
  console.log("➕ All activeBookings:", activeBookings);

  // Save to server (unless loading from server)
  if (saveToServer) {
    saveBookingToServer(booking);
  }

  renderBookings();
  renderSidebarBookings();
  console.log("➕ Calling renderCalendarEvents()...");
  renderCalendarEvents();
}

function updateBookingStatus(bookingId, status, message) {
  const booking = activeBookings.find((b) => b.id === bookingId);
  if (booking) {
    booking.status = status;
    booking.message = message;

    // Update on server
    updateBookingOnServer(bookingId, { status, message });

    renderBookings();
    renderSidebarBookings();
    renderCalendarEvents();
  }
}

// Calculate total tabs needed for multi-tab booking (50 ticket limit per tab)
function calculateTotalTabs(timeSlots) {
  let totalTabs = 0;
  timeSlots.forEach((slot) => {
    const quantity = slot.quantity || 1;
    const tabsForSlot = Math.ceil(quantity / 50);
    totalTabs += tabsForSlot;
  });
  return totalTabs;
}

// Format slot display with multi-tab info
function formatSlotDisplay(timeSlots) {
  const totalTabs = calculateTotalTabs(timeSlots);

  let display = timeSlots.map((s) => `${s.time} (${s.quantity})`).join(", ");

  // Add multi-tab info if needed
  if (totalTabs > timeSlots.length) {
    display += ` <span style="color: #6b7280; font-size: 11px;">[${totalTabs} tabs total]</span>`;
  }

  return display;
}

function renderBookings() {
  const container = document.getElementById("bookingsList");

  // If container doesn't exist (we removed it from the layout), just skip rendering
  if (!container) {
    console.log("ℹ️  Bookings list container not found (removed from layout) - skipping render");
    return;
  }

  if (activeBookings.length === 0) {
    container.innerHTML = '<p class="empty-state">No active bookings</p>';
    return;
  }

  // Helper function to get friendly status label
  const getStatusLabel = (status) => {
    const statusLabels = {
      'scheduled': 'Scheduled',
      'login_check': 'Login Check',
      'running': 'Running',
      'completed': 'Succeeded',
      'failed': 'Failed'
    };
    return statusLabels[status] || status;
  };

  container.innerHTML = activeBookings
    .map(
      (booking) => `
        <div class="booking-item">
            <div class="booking-header">
                <span class="booking-id">#${booking.id}</span>
                <span class="booking-status ${booking.status}">${getStatusLabel(booking.status)}</span>
            </div>
            <div class="booking-details">
                <div><strong>URL:</strong> ${truncateUrl(booking.url)}</div>
                <div><strong>Date:</strong> ${formatBookingDateForDisplay(booking.booking_date)}</div>
                <div><strong>Trigger:</strong> ${booking.trigger_time}</div>
                <div><strong>Slots:</strong> ${formatSlotDisplay(
                  booking.time_slots
                )}</div>
            </div>
            ${
              booking.status === "scheduled"
                ? `
                <div class="booking-actions">
                    <button class="btn-cancel" onclick="cancelBooking('${booking.id}')">Cancel</button>
                </div>
            `
                : ""
            }
        </div>
    `
    )
    .join("");
}

function cancelBooking(bookingId) {
  if (confirm("Are you sure you want to cancel this booking?")) {
    sendMessage({ type: "cancel_booking", booking_id: bookingId });
    activeBookings = activeBookings.filter((b) => b.id !== bookingId);

    // Delete from server
    deleteBookingFromServer(bookingId);

    renderBookings();
    renderCalendarEvents();
    addBookingLog(bookingId, "Booking cancelled by user", "warning");
    addLog(`🗑️ Booking ${bookingId} cancelled`, "warning");
    showToast("Booking cancelled", "info");

    // Close event details panel if it's open
    closeEventDetailsPanel();
  }
}

function truncateUrl(url) {
  return url.length > 50 ? url.substring(0, 47) + "..." : url;
}

// Logs Management (logs now only appear in event detail panels)
function addLog(message, level = "info") {
  // Log to console for debugging
  const timestamp = new Date().toLocaleTimeString();
  const logMessage = `[${timestamp}] ${message}`;

  switch (level) {
    case "error":
      console.error(logMessage);
      break;
    case "warning":
      console.warn(logMessage);
      break;
    case "success":
      console.log(`✅ ${logMessage}`);
      break;
    default:
      console.log(logMessage);
  }
}

function addBookingLog(bookingId, message, level = "info", saveToServer = true) {
  if (!bookingId) return;

  if (!bookingLogsById[bookingId]) {
    bookingLogsById[bookingId] = [];
  }

  const logEntry = {
    timestamp: new Date().toLocaleTimeString(),
    message,
    level,
  };

  bookingLogsById[bookingId].push(logEntry);

  // Save log to server (unless it came from WebSocket - backend already saved it)
  if (saveToServer) {
    addLogToBookingOnServer(bookingId, logEntry);
  }

  // Update event details panel if it's currently showing this booking
  const detailsPanel = document.getElementById("eventDetailsPanel");
  if (detailsPanel && detailsPanel.classList.contains("open")) {
    const currentBookingInPanel = activeBookings.find((b) => b.id === bookingId);
    if (currentBookingInPanel) {
      openEventDetailsPanel(bookingId);
    }
  }
}

// Calendar integration
function setupCalendar() {
  const calendarEl = document.getElementById("calendar");
  if (!calendarEl || !window.FullCalendar) {
    console.warn("FullCalendar not available or calendar element missing.");
    return;
  }

  calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: "dayGridMonth",
    height: "100%",
    headerToolbar: false,
    selectable: true,
    selectConstraint: {
      start: new Date().toISOString().split("T")[0],
    },
    editable: false,
    dayMaxEvents: 3,
    // Remove validRange to show past dates (they'll be styled as disabled via CSS)
    eventClick: function (info) {
      console.log("🖱️  Event clicked:", info.event);
      console.log("   - Event ID:", info.event.id);
      console.log("   - Extended Props:", info.event.extendedProps);

      info.jsEvent.preventDefault();
      const bookingId = info.event.extendedProps.bookingId || info.event.id;
      console.log("   - Booking ID:", bookingId);

      if (bookingId) {
        console.log("   ✅ Opening event details panel for booking:", bookingId);
        openEventDetailsPanel(bookingId);
      } else {
        console.error("   ❌ No booking ID found!");
      }
    },
    dateClick: function (info) {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const clickedDate = new Date(info.date);
      clickedDate.setHours(0, 0, 0, 0);

      // Prevent past date selection
      if (clickedDate < today) {
        showToast("Cannot schedule bookings for past dates", "error");
        return;
      }

      openBookingSidePanel(info.date);
    },
    datesSet: function (info) {
      // Update main calendar title
      updateMainCalendarTitle();

      // Update navigation buttons
      updateNavigationButtons();

      // Sync mini calendar when main calendar changes month
      const mainDate = calendar.getDate();
      if (mainDate.getMonth() !== currentMiniMonth.getMonth() ||
          mainDate.getFullYear() !== currentMiniMonth.getFullYear()) {
        currentMiniMonth = new Date(mainDate);
        renderMiniCalendar();
      }
    },
    eventMouseEnter: function (info) {
      showEventTooltip(info.jsEvent, info.event);
    },
    eventMouseLeave: function (info) {
      hideEventTooltip();
    },
    dayCellDidMount: function (info) {
      // Create a permanent bottom section for the "+ Add Scheduler" button
      // Use local date format to avoid timezone issues
      const year = info.date.getFullYear();
      const month = String(info.date.getMonth() + 1).padStart(2, '0');
      const day = String(info.date.getDate()).padStart(2, '0');
      const dateStr = `${year}-${month}-${day}`;

      console.log(`📅 dayCellDidMount for date: ${dateStr}`);

      // Find the day frame (main container for the cell content)
      const dayFrame = info.el.querySelector('.fc-daygrid-day-frame');

      if (dayFrame) {
        // Check if bottom section already exists (prevent duplicates on re-render)
        let bottomSection = dayFrame.querySelector('.calendar-cell-bottom-section');

        if (!bottomSection) {
          // Create the bottom section container only if it doesn't exist
          bottomSection = document.createElement("div");
          bottomSection.className = "calendar-cell-bottom-section";
          bottomSection.setAttribute("data-date", dateStr);

          // Create the "+ Add Scheduler" button (initially hidden)
          const addButton = document.createElement("div");
          addButton.className = "main-calendar-booking-indicator";
          addButton.innerHTML = '<span class="indicator-icon">+</span> <span class="indicator-text">Add Scheduler</span>';
          addButton.onclick = function() {
            // Convert dateStr to Date object and open booking panel
            const date = new Date(dateStr + 'T00:00:00');
            openBookingSidePanel(date);
          };

          // Add button to bottom section
          bottomSection.appendChild(addButton);

          // Add bottom section to day frame
          dayFrame.appendChild(bottomSection);

          console.log(`   ✅ Created new bottom section for ${dateStr}`);
        } else {
          console.log(`   ℹ️  Bottom section already exists for ${dateStr}, skipping creation`);
        }

        // Always update button visibility based on current bookings
        const addButton = bottomSection.querySelector('.main-calendar-booking-indicator');
        if (addButton) {
          const hasBooking = activeBookings.some((booking) => {
            const bookingDateStr = parseBookingDateToISO(booking.booking_date);
            console.log(`   Comparing: cell date=${dateStr}, booking date=${bookingDateStr}, match=${bookingDateStr === dateStr}`);
            return bookingDateStr === dateStr;
          });

          console.log(`   hasBooking for ${dateStr}: ${hasBooking}`);

          // Show or hide the button based on whether there are bookings
          if (hasBooking) {
            addButton.classList.remove("hidden");
            addButton.classList.add("visible");
            console.log(`   ✅ Showing button for ${dateStr}`);
          } else {
            addButton.classList.remove("visible");
            addButton.classList.add("hidden");
            console.log(`   ❌ Hiding button for ${dateStr}`);
          }
        }
      }
    },
  });

  calendar.render();
  updateMainCalendarTitle();
  updateNavigationButtons();

  // Hook up external controls
  const prevBtn = document.getElementById("calendarPrevBtn");
  const nextBtn = document.getElementById("calendarNextBtn");

  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      calendar.prev();
      updateMainCalendarTitle();
      updateNavigationButtons();
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      calendar.next();
      updateMainCalendarTitle();
      updateNavigationButtons();
    });
  }

  // Render any existing bookings
  renderCalendarEvents();
}

function updateMainCalendarTitle() {
  if (!calendar) return;

  const titleEl = document.getElementById("mainCalendarTitle");
  if (!titleEl) return;

  const currentDate = calendar.getDate();
  const title = currentDate.toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });

  titleEl.textContent = title;
}

function updateNavigationButtons() {
  if (!calendar) return;

  const prevBtn = document.getElementById("calendarPrevBtn");
  if (!prevBtn) return;

  const currentDate = calendar.getDate();
  const today = new Date();

  // Get the first day of the current month being displayed
  const currentMonth = currentDate.getMonth();
  const currentYear = currentDate.getFullYear();

  // Get the first day of the current real month
  const todayMonth = today.getMonth();
  const todayYear = today.getFullYear();

  // Disable previous button if we're viewing the current month or earlier
  if (currentYear < todayYear || (currentYear === todayYear && currentMonth <= todayMonth)) {
    prevBtn.disabled = true;
  } else {
    prevBtn.disabled = false;
  }
}

function renderCalendarEvents() {
  console.log("🎨 ========== renderCalendarEvents() CALLED ==========");

  if (!calendar) {
    console.error("❌ Calendar not initialized yet!");
    return;
  }

  console.log("✅ Calendar is initialized");
  console.log("📊 Active bookings count:", activeBookings.length);
  console.log("📊 Active bookings data:", JSON.stringify(activeBookings, null, 2));

  const events = activeBookings
    .map((booking, index) => {
      console.log(`\n🔍 Processing booking ${index + 1}/${activeBookings.length}:`);
      console.log("   - ID:", booking.id);
      console.log("   - Booking Date (raw):", booking.booking_date);
      console.log("   - Status:", booking.status);
      console.log("   - Trigger Time:", booking.trigger_time);
      console.log("   - Time Slots:", booking.time_slots);

      const dateStr = parseBookingDateToISO(booking.booking_date);
      console.log("   - Parsed ISO Date:", dateStr);

      if (!dateStr) {
        console.error("   ❌ Could not parse date for booking:", booking.booking_date);
        return null;
      }

      const eventTitle = formatBookingEventTitle(booking);
      const statusColor = getStatusColor(booking.status);

      console.log("   - Event Title:", eventTitle);
      console.log("   - Status Color:", statusColor);

      const event = {
        id: booking.id,
        title: eventTitle,
        start: dateStr,
        allDay: true,
        backgroundColor: statusColor,
        borderColor: statusColor,
        extendedProps: {
          bookingId: booking.id,
          status: booking.status,
        },
        classNames: ["booking-event", `status-${booking.status}`],
      };

      console.log("   ✅ Event object created:", event);
      return event;
    })
    .filter(Boolean);

  console.log("\n📋 Total events to render:", events.length);
  console.log("📋 Events array:", JSON.stringify(events, null, 2));

  // Remove all existing events
  console.log("🗑️  Removing all existing events...");
  calendar.removeAllEvents();

  // Add new events
  console.log("➕ Adding new events to calendar...");
  events.forEach((event, index) => {
    console.log(`   Adding event ${index + 1}:`, event.title, "on", event.start);
    calendar.addEvent(event);
  });

  console.log("✅ All events added to calendar");
  console.log("📅 Calendar events after adding:", calendar.getEvents().length);

  // Re-render mini calendar to show event indicators
  console.log("🔄 Re-rendering mini calendar...");
  renderMiniCalendar();

  // Update "+ Add Scheduler" button visibility
  console.log("🔄 Updating Add Scheduler button visibility...");
  updateAddSchedulerButtons();

  console.log("🎨 ========== renderCalendarEvents() COMPLETE ==========\n");
}

// Update the visibility of "+ Add Scheduler" buttons based on bookings
function updateAddSchedulerButtons() {
  console.log("🔘 updateAddSchedulerButtons() called");

  // Get all calendar cells with bottom sections
  const bottomSections = document.querySelectorAll('.calendar-cell-bottom-section');
  console.log(`   Found ${bottomSections.length} bottom sections`);

  bottomSections.forEach((section) => {
    const dateStr = section.getAttribute('data-date');
    const button = section.querySelector('.main-calendar-booking-indicator');

    if (!button || !dateStr) return;

    // Check if this date has any bookings
    const hasBooking = activeBookings.some((booking) => {
      const bookingDateStr = parseBookingDateToISO(booking.booking_date);
      return bookingDateStr === dateStr;
    });

    // Show or hide button based on bookings
    if (hasBooking) {
      button.classList.remove('hidden');
      button.classList.add('visible');
      console.log(`   ✅ Showing button for date: ${dateStr}`);
    } else {
      button.classList.remove('visible');
      button.classList.add('hidden');
      console.log(`   ❌ Hiding button for date: ${dateStr}`);
    }
  });

  console.log("🔘 updateAddSchedulerButtons() complete");
}

function getStatusColor(status) {
  const colors = {
    scheduled: "#6366f1",      // Indigo
    login_check: "#f59e0b",    // Amber
    running: "#3b82f6",        // Blue
    completed: "#10b981",      // Green
    failed: "#ef4444",         // Red
  };
  return colors[status] || "#6366f1";
}

function formatBookingEventTitle(booking) {
  const time = booking.trigger_time || "";
  const shortId = booking.id ? booking.id.slice(0, 4) : "";
  const slotsLabel =
    booking.time_slots && booking.time_slots.length
      ? booking.time_slots.map((s) => s.time).join(", ")
      : "";

  const parts = [];
  if (time) parts.push(time);
  if (slotsLabel) parts.push(slotsLabel);
  if (!parts.length && shortId) {
    parts.push(`Booking ${shortId}`);
  }

  return parts.join(" • ") || "Booking";
}

// Mini Calendar Setup
function setupMiniCalendar() {
  currentMiniMonth = new Date();
  renderMiniCalendar();

  // Hook up navigation buttons
  const prevBtn = document.getElementById("miniCalendarPrevBtn");
  const nextBtn = document.getElementById("miniCalendarNextBtn");

  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      currentMiniMonth.setMonth(currentMiniMonth.getMonth() - 1);
      renderMiniCalendar();
      // Sync main calendar
      if (calendar) {
        calendar.gotoDate(currentMiniMonth);
      }
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      currentMiniMonth.setMonth(currentMiniMonth.getMonth() + 1);
      renderMiniCalendar();
      // Sync main calendar
      if (calendar) {
        calendar.gotoDate(currentMiniMonth);
      }
    });
  }
}

function renderMiniCalendar() {
  const container = document.getElementById("miniCalendar");
  const titleEl = document.getElementById("miniCalendarTitle");

  if (!container || !titleEl) return;

  const year = currentMiniMonth.getFullYear();
  const month = currentMiniMonth.getMonth();
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // Update title
  titleEl.textContent = currentMiniMonth.toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });

  // Get first day of month and number of days
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const daysInMonth = lastDay.getDate();
  const startingDayOfWeek = firstDay.getDay();

  // Build calendar HTML
  let html = '<table><thead><tr>';
  const dayNames = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
  dayNames.forEach((day) => {
    html += `<th>${day}</th>`;
  });
  html += "</tr></thead><tbody><tr>";

  // Empty cells before first day
  for (let i = 0; i < startingDayOfWeek; i++) {
    html += "<td></td>";
  }

  // Days of month
  for (let day = 1; day <= daysInMonth; day++) {
    const date = new Date(year, month, day);
    date.setHours(0, 0, 0, 0);

    const isPast = date < today;
    const isToday = date.getTime() === today.getTime();
    const isSelected = selectedDate && date.getTime() === new Date(selectedDate).setHours(0, 0, 0, 0);
    const hasEvent = activeBookings.some((booking) => {
      const bookingDate = parseBookingDateToISO(booking.booking_date);
      if (!bookingDate) return false;
      const bDate = new Date(bookingDate);
      bDate.setHours(0, 0, 0, 0);
      return bDate.getTime() === date.getTime();
    });

    let classes = ["mini-calendar-day"];
    if (isPast) classes.push("disabled");
    if (isToday) classes.push("today");
    if (isSelected) classes.push("selected");
    if (hasEvent) classes.push("has-event");

    const dateStr = date.toISOString().split("T")[0];

    // No plus icon on mini calendar anymore
    html += `<td><span class="${classes.join(" ")}" data-date="${dateStr}" onclick="handleMiniCalendarDateClick('${dateStr}')">${day}</span></td>`;

    // Start new row on Sunday
    if ((startingDayOfWeek + day) % 7 === 0 && day < daysInMonth) {
      html += "</tr><tr>";
    }
  }

  // Empty cells after last day
  const remainingCells = (7 - ((startingDayOfWeek + daysInMonth) % 7)) % 7;
  for (let i = 0; i < remainingCells; i++) {
    html += "<td></td>";
  }

  html += "</tr></tbody></table>";
  container.innerHTML = html;
}

function handleMiniCalendarDateClick(dateStr) {
  const date = new Date(dateStr + "T12:00:00");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  date.setHours(0, 0, 0, 0);

  // Prevent past date selection
  if (date < today) {
    showToast("Cannot select past dates", "error");
    return;
  }

  // Open booking side panel
  openBookingSidePanel(date);

  // Update mini calendar to show selection
  renderMiniCalendar();
}

// Render sidebar bookings list
function renderSidebarBookings() {
  const container = document.getElementById("sidebarBookingsList");

  if (!container) {
    console.log("ℹ️  Sidebar bookings list container not found");
    return;
  }

  if (activeBookings.length === 0) {
    container.innerHTML = '<p class="empty-state">No scheduled bookings</p>';
    return;
  }

  // Group bookings by month
  const bookingsByMonth = {};

  activeBookings.forEach((booking) => {
    const dateStr = parseBookingDateToISO(booking.booking_date);
    if (!dateStr) return;

    const date = new Date(dateStr);
    const monthKey = date.toLocaleDateString("en-US", {
      month: "long",
      year: "numeric",
    });

    if (!bookingsByMonth[monthKey]) {
      bookingsByMonth[monthKey] = [];
    }

    bookingsByMonth[monthKey].push({
      ...booking,
      dateObj: date,
    });
  });

  // Sort months chronologically
  const sortedMonths = Object.keys(bookingsByMonth).sort((a, b) => {
    const dateA = new Date(bookingsByMonth[a][0].dateObj);
    const dateB = new Date(bookingsByMonth[b][0].dateObj);
    return dateA - dateB;
  });

  // Build HTML
  let html = "";

  sortedMonths.forEach((monthKey) => {
    const bookings = bookingsByMonth[monthKey];

    // Sort bookings within month by date
    bookings.sort((a, b) => a.dateObj - b.dateObj);

    html += `<div class="sidebar-booking-month">${monthKey}</div>`;

    bookings.forEach((booking) => {
      const dateDisplay = booking.dateObj.toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
      });

      const slotsText = booking.time_slots
        .map((s) => `${s.time} (${s.quantity})`)
        .join(", ");

      // Get friendly status label
      const statusLabels = {
        'scheduled': 'Scheduled',
        'login_check': 'Login Check',
        'running': 'Running',
        'completed': 'Succeeded',
        'failed': 'Failed'
      };
      const statusLabel = statusLabels[booking.status] || booking.status;

      html += `
        <div class="sidebar-booking-item status-${booking.status}" onclick="openEventDetailsPanel('${booking.id}')">
          <div class="sidebar-booking-date">${dateDisplay}</div>
          <div class="sidebar-booking-details">
            <div>⏰ ${booking.trigger_time}</div>
            <div>🎫 ${slotsText}</div>
          </div>
          <span class="sidebar-booking-status ${booking.status}">${statusLabel}</span>
        </div>
      `;
    });
  });

  container.innerHTML = html;
}

// Side Panel Management
function openBookingSidePanel(date) {
  // Close any open panels first
  closeAllPanels();

  selectedDate = date;

  const panel = document.getElementById("bookingSidePanel");
  const overlay = document.getElementById("sidePanelOverlay");
  const bookingDateInput = document.getElementById("bookingDate");
  const selectedDateDisplay = document.getElementById("selectedDateDisplay");

  const formattedForBackend = formatBookingDate(date);
  const formattedForDisplay = date.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  if (bookingDateInput) {
    bookingDateInput.value = formattedForBackend;
  }

  if (selectedDateDisplay) {
    selectedDateDisplay.textContent = formattedForDisplay;
  }

  // Reset form
  resetTimeSlots();

  // Clear trigger datetime input (leave blank with placeholder)
  const triggerDateTimeInput = document.getElementById("triggerDateTime");
  if (triggerDateTimeInput) {
    triggerDateTimeInput.value = "";
    triggerDateTimeInput.classList.remove("invalid", "valid");

    // Clear any error messages
    const errorElement = document.getElementById("triggerDateTimeError");
    if (errorElement) {
      errorElement.style.display = "none";
    }
  }

  // Open panel and overlay
  panel.classList.add("open");
  overlay.classList.add("active");
}

function closeBookingSidePanel() {
  const panel = document.getElementById("bookingSidePanel");
  const overlay = document.getElementById("sidePanelOverlay");
  panel.classList.remove("open");
  overlay.classList.remove("active");
  selectedDate = null;
}

function openEventDetailsPanel(bookingId) {
  console.log("📋 openEventDetailsPanel called with bookingId:", bookingId);

  // Close any open panels first
  closeAllPanels();

  const panel = document.getElementById("eventDetailsPanel");
  const overlay = document.getElementById("sidePanelOverlay");
  const content = document.getElementById("eventDetailsContent");

  console.log("   - Panel element:", panel);
  console.log("   - Overlay element:", overlay);
  console.log("   - Content element:", content);
  console.log("   - Searching in activeBookings:", activeBookings.length, "bookings");

  const booking = activeBookings.find((b) => b.id === bookingId);
  console.log("   - Found booking:", booking);

  if (!booking) {
    console.error("   ❌ Booking not found in activeBookings!");
    content.innerHTML = '<p class="empty-state">Booking not found.</p>';
    panel.classList.add("open");
    overlay.classList.add("active");
    return;
  }

  console.log("   ✅ Booking found, displaying details...");

  const logs = bookingLogsById[bookingId] || [];

  // Helper function to get status badge HTML
  const getStatusBadgeHtml = (status) => {
    const statusLabels = {
      'scheduled': 'Scheduled',
      'login_check': 'Login Check',
      'running': 'Running',
      'completed': 'Succeeded',
      'failed': 'Failed'
    };
    const label = statusLabels[status] || status;
    return `<span class="booking-status ${status}">${label}</span>`;
  };

  const logsHtml =
    logs.length > 0
      ? logs
          .map(
            (log) =>
              `<div class="log-entry ${log.level || "info"}">
                <span class="log-timestamp">${log.timestamp}</span>
                <span class="log-message">${log.message}</span>
              </div>`
          )
          .join("")
      : '<p class="empty-state">No activity logs yet.</p>';

  content.innerHTML = `
    <div class="booking-item">
      <div class="booking-header">
        <span class="booking-id">#${booking.id}</span>
        ${getStatusBadgeHtml(booking.status)}
      </div>
      <div class="booking-details">
        <div><strong>Date:</strong> ${formatBookingDateForDisplay(booking.booking_date)}</div>
        <div><strong>Trigger:</strong> ${booking.trigger_time}</div>
        <div><strong>Slots:</strong> ${formatSlotDisplay(booking.time_slots)}</div>
      </div>
      ${
        booking.status === "scheduled"
          ? `<div class="booking-actions"><button class="btn-cancel" onclick="cancelBooking('${booking.id}')">Cancel Booking</button></div>`
          : ""
      }
      <div class="booking-logs-section" style="margin-top: 20px;">
        <h3 style="font-size: 15px; font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
          Activity Logs
          <span style="font-size: 12px; font-weight: 400; color: #6b7280;">(${logs.length} ${logs.length === 1 ? 'entry' : 'entries'})</span>
        </h3>
        <div class="booking-logs-list">
          ${logsHtml}
        </div>
      </div>
    </div>
  `;

  panel.classList.add("open");
  overlay.classList.add("active");
}

function closeEventDetailsPanel() {
  const panel = document.getElementById("eventDetailsPanel");
  const overlay = document.getElementById("sidePanelOverlay");
  panel.classList.remove("open");
  overlay.classList.remove("active");
}

function closeAllPanels() {
  closeBookingSidePanel();
  closeEventDetailsPanel();
}

// Event Tooltip
function showEventTooltip(jsEvent, event) {
  const tooltip = document.getElementById("eventTooltip");
  const content = document.getElementById("tooltipContent");

  const bookingId = event.extendedProps.bookingId || event.id;
  const booking = activeBookings.find((b) => b.id === bookingId);

  if (!booking) return;

  const shortId = booking.id.slice(0, 6);
  const slotsText = booking.time_slots
    .map((s) => `${s.time} (${s.quantity})`)
    .join(", ");

  content.innerHTML = `
    <strong>Booking #${shortId}</strong>
    <div style="margin-top: 4px;">
      <div><strong>Status:</strong> ${booking.status}</div>
      <div><strong>Trigger:</strong> ${booking.trigger_time}</div>
      <div><strong>Slots:</strong> ${slotsText}</div>
    </div>
  `;

  tooltip.style.display = "block";
  tooltip.style.left = jsEvent.pageX + 10 + "px";
  tooltip.style.top = jsEvent.pageY + 10 + "px";
}

function hideEventTooltip() {
  const tooltip = document.getElementById("eventTooltip");
  tooltip.style.display = "none";
}

function formatBookingDate(date) {
  // Format as YYYY-MM-DD for backend compatibility
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0'); // Months are 0-indexed
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function parseBookingDateToISO(dateStr) {
  console.log("🔄 parseBookingDateToISO called with:", dateStr);

  if (!dateStr) {
    console.warn("⚠️  dateStr is null or undefined");
    return null;
  }

  // Handle different date formats
  let date;

  // If dateStr is already in YYYY-MM-DD format, use it directly with local timezone
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    // Already in ISO format, parse as local date
    date = new Date(dateStr + 'T00:00:00');
  } else {
    // Parse other formats (e.g., "November 22, 2025")
    date = new Date(dateStr);
  }

  console.log("   - Parsed Date object:", date);
  console.log("   - Date.getTime():", date.getTime());

  if (Number.isNaN(date.getTime())) {
    console.error("❌ Invalid date - getTime() returned NaN");
    return null;
  }

  // Use local date components to avoid timezone shifts
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  const isoDate = `${year}-${month}-${day}`;

  console.log("   ✅ ISO Date:", isoDate);
  return isoDate;
}

/**
 * Format booking date for display (converts YYYY-MM-DD to readable format)
 */
function formatBookingDateForDisplay(dateStr) {
  if (!dateStr) return dateStr;

  // If already in YYYY-MM-DD format, convert to readable format
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    const date = new Date(dateStr + 'T00:00:00');
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
      });
    }
  }

  // Return as-is if not in YYYY-MM-DD format (backward compatibility)
  return dateStr;
}

// Toast Notifications
function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;

  const icon =
    {
      success: "✅",
      error: "❌",
      warning: "⚠️",
      info: "ℹ️",
    }[type] || "ℹ️";

  toast.innerHTML = `
        <span style="font-size: 20px;">${icon}</span>
        <span>${message}</span>
    `;

  container.appendChild(toast);

  // Auto remove after 5 seconds
  setTimeout(() => {
    toast.style.animation = "slideIn 0.3s ease-out reverse";
    setTimeout(() => toast.remove(), 300);
  }, 5000);
}

// ==============================
// Configuration Management
// ==============================

/**
 * Load configuration from server
 */
async function loadConfiguration() {
  try {
    const response = await fetch("/api/config");
    const data = await response.json();

    if (data.success) {
      currentConfig = data.config;
      console.log("Configuration loaded:", currentConfig);

      // Auto-fill form fields if configuration exists
      autoFillFormFields();

      // Update password status after loading config
      updatePasswordStatus();
    } else {
      console.warn("Failed to load configuration:", data.error);
      // Ensure currentConfig is null if load failed
      currentConfig = null;
      // Update password status to show "Password Not Saved"
      updatePasswordStatus();
    }
  } catch (error) {
    console.error("Error loading configuration:", error);
    // Ensure currentConfig is null if error occurred
    currentConfig = null;
    // Update password status to show "Password Not Saved"
    updatePasswordStatus();
  }
}

// ==============================
// 📅 Booking Persistence API
// ==============================

/**
 * Load all bookings from server
 */
async function loadBookingsFromServer() {
  console.log("📥 Loading bookings from server...");
  try {
    const response = await fetch("/api/bookings");
    const data = await response.json();

    if (data.success) {
      const bookings = data.bookings || [];
      console.log(`✅ Loaded ${bookings.length} bookings from server`);

      // Clear current bookings
      activeBookings = [];
      bookingLogsById = {};

      // Restore bookings to memory
      bookings.forEach((booking) => {
        activeBookings.push(booking);

        // Restore logs
        if (booking.logs && Array.isArray(booking.logs)) {
          bookingLogsById[booking.id] = booking.logs;
        }
      });

      // Render UI (don't call addBookingToList - it would add duplicates!)
      renderBookings();
      renderSidebarBookings();

      // Update calendar
      if (calendar) {
        renderCalendarEvents();
        updateAddSchedulerButtons();
      }

      console.log(`📊 Final activeBookings count: ${activeBookings.length}`);
      return bookings;
    } else {
      console.error("Failed to load bookings:", data.error);
      return [];
    }
  } catch (error) {
    console.error("Error loading bookings from server:", error);
    return [];
  }
}

/**
 * Save a booking to server
 */
async function saveBookingToServer(booking) {
  console.log(`💾 Saving booking ${booking.id} to server...`);
  try {
    const response = await fetch("/api/bookings", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(booking),
    });

    const data = await response.json();

    if (data.success) {
      console.log(`✅ Booking ${booking.id} saved to server`);
      return true;
    } else {
      console.error(`Failed to save booking ${booking.id}:`, data.error);
      return false;
    }
  } catch (error) {
    console.error(`Error saving booking ${booking.id} to server:`, error);
    return false;
  }
}

/**
 * Update a booking on server
 */
async function updateBookingOnServer(bookingId, updates) {
  console.log(`🔄 Updating booking ${bookingId} on server...`);
  try {
    const response = await fetch(`/api/bookings/${bookingId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(updates),
    });

    const data = await response.json();

    if (data.success) {
      console.log(`✅ Booking ${bookingId} updated on server`);
      return true;
    } else {
      console.error(`Failed to update booking ${bookingId}:`, data.error);
      return false;
    }
  } catch (error) {
    console.error(`Error updating booking ${bookingId} on server:`, error);
    return false;
  }
}

/**
 * Delete a booking from server
 */
async function deleteBookingFromServer(bookingId) {
  console.log(`🗑️  Deleting booking ${bookingId} from server...`);
  try {
    const response = await fetch(`/api/bookings/${bookingId}`, {
      method: "DELETE",
    });

    const data = await response.json();

    if (data.success) {
      console.log(`✅ Booking ${bookingId} deleted from server`);
      return true;
    } else {
      console.error(`Failed to delete booking ${bookingId}:`, data.error);
      return false;
    }
  } catch (error) {
    console.error(`Error deleting booking ${bookingId} from server:`, error);
    return false;
  }
}

/**
 * Add a log entry to a booking on server
 */
async function addLogToBookingOnServer(bookingId, logEntry) {
  try {
    const response = await fetch(`/api/bookings/${bookingId}/logs`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(logEntry),
    });

    const data = await response.json();

    if (data.success) {
      return true;
    } else {
      console.error(`Failed to add log to booking ${bookingId}:`, data.error);
      return false;
    }
  } catch (error) {
    console.error(`Error adding log to booking ${bookingId}:`, error);
    return false;
  }
}

/**
 * Toggle password visibility
 */
function togglePasswordVisibility(inputId) {
  const input = document.getElementById(inputId);
  const wrapper = input.closest(".password-input-wrapper");
  const eyeOpen = wrapper.querySelector(".eye-open");
  const eyeClosed = wrapper.querySelector(".eye-closed");

  if (input.type === "password") {
    input.type = "text";
    eyeOpen.style.display = "none";
    eyeClosed.style.display = "block";
  } else {
    input.type = "password";
    eyeOpen.style.display = "block";
    eyeClosed.style.display = "none";
  }
}

/**
 * Auto-fill form fields from configuration
 */
function autoFillFormFields() {
  if (!currentConfig) return;

  const urlInput = document.getElementById("url");
  const emailInput = document.getElementById("email");
  const passwordInput = document.getElementById("password");

  // Auto-fill URL if empty and config has default URL
  if (currentConfig.default_url && !urlInput.value) {
    urlInput.value = currentConfig.default_url;
    urlInput.classList.add("auto-filled");
  }

  // Auto-fill email if empty and config has email
  if (currentConfig.email && !emailInput.value) {
    emailInput.value = currentConfig.email;
    emailInput.classList.add("auto-filled");
  }

  // Auto-fill password from sessionStorage (stored when config is saved)
  const savedPassword = sessionStorage.getItem("config_password");
  if (savedPassword && !passwordInput.value) {
    passwordInput.value = savedPassword;
    passwordInput.classList.add("auto-filled");
  }
}

/**
 * Setup configuration form handlers
 */
function setupConfigHandlers() {
  const configForm = document.getElementById("configForm");

  configForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    await saveConfiguration();
  });

  // Remove auto-filled class when user starts typing
  const inputs = ["url", "email", "password"];
  inputs.forEach((id) => {
    const input = document.getElementById(id);
    if (input) {
      input.addEventListener("input", () => {
        input.classList.remove("auto-filled");
      });
    }
  });
}

/**
 * Open configuration modal
 */
function openConfigModal() {
  const modal = document.getElementById("configModal");
  modal.classList.add("active");

  // Update bot status when opening modal
  updateBotStatus();

  // Load current configuration into form
  if (currentConfig) {
    document.getElementById("configEmail").value = currentConfig.email || "";
    document.getElementById("configDefaultUrl").value =
      currentConfig.default_url || "";
    document.getElementById("configMonitoringTime").value =
      currentConfig.slot_monitoring_time || 30;
    document.getElementById("configMonitoringInterval").value =
      currentConfig.monitoring_interval || 50;

    // Don't pre-fill password for security (user must re-enter)
    document.getElementById("configPassword").value = "";
    document.getElementById("configPassword").placeholder =
      currentConfig.password === "********"
        ? "Leave blank to keep current password"
        : "Your password";
  }
}

/**
 * Close configuration modal
 */
function closeConfigModal() {
  const modal = document.getElementById("configModal");
  modal.classList.remove("active");
}

/**
 * Save configuration
 */
async function saveConfiguration() {
  const email = document.getElementById("configEmail").value.trim();
  const password = document.getElementById("configPassword").value;
  const defaultUrl = document.getElementById("configDefaultUrl").value.trim();
  const monitoringTime = parseInt(
    document.getElementById("configMonitoringTime").value
  );
  const monitoringInterval = parseInt(
    document.getElementById("configMonitoringInterval").value
  );

  // Validate inputs
  if (email && !isValidEmail(email)) {
    showToast("Please enter a valid email address", "error");
    return;
  }

  if (defaultUrl && !isValidUrl(defaultUrl)) {
    showToast("Please enter a valid recreation.gov URL", "error");
    return;
  }

  const configData = {
    email: email,
    default_url: defaultUrl,
    slot_monitoring_time: monitoringTime,
    monitoring_interval: monitoringInterval,
  };

  // Only include password if user entered one
  if (password) {
    configData.password = password;
  }

  try {
    const response = await fetch("/api/config", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(configData),
    });

    const data = await response.json();

    if (data.success) {
      // Store password in sessionStorage for auto-fill (only in current session)
      if (password) {
        sessionStorage.setItem("config_password", password);
      }

      showToast("Configuration saved successfully", "success");
      closeConfigModal();

      // Reload configuration
      await loadConfiguration();
    } else {
      showToast("Failed to save configuration: " + data.error, "error");
    }
  } catch (error) {
    console.error("Error saving configuration:", error);
    showToast("Error saving configuration", "error");
  }
}

/**
 * Clear all configuration
 */
async function clearConfiguration() {
  if (
    !confirm(
      "Are you sure you want to clear all configuration? This cannot be undone."
    )
  ) {
    return;
  }

  try {
    const response = await fetch("/api/config", {
      method: "DELETE",
    });

    const data = await response.json();

    if (data.success) {
      showToast("Configuration cleared successfully", "success");
      closeConfigModal();

      // Reset current config
      currentConfig = null;

      // Clear sessionStorage password
      sessionStorage.removeItem("config_password");

      // Clear form fields
      document.getElementById("url").value = "";
      document.getElementById("email").value = "";
      document.getElementById("password").value = "";

      // Remove auto-filled classes
      document.getElementById("url").classList.remove("auto-filled");
      document.getElementById("email").classList.remove("auto-filled");
      document.getElementById("password").classList.remove("auto-filled");

      // Clear config form
      document.getElementById("configForm").reset();

      // Update password status on main screen
      updatePasswordStatus();
    } else {
      showToast("Failed to clear configuration: " + data.error, "error");
    }
  } catch (error) {
    console.error("Error clearing configuration:", error);
    showToast("Error clearing configuration", "error");
  }
}

/**
 * Validate email format
 */
function isValidEmail(email) {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
}

/**
 * Validate URL format
 */
function isValidUrl(url) {
  try {
    const urlObj = new URL(url);
    return urlObj.hostname.includes("recreation.gov");
  } catch {
    return false;
  }
}

// Close modal when clicking outside
document.addEventListener("click", (e) => {
  const modal = document.getElementById("configModal");
  if (e.target === modal) {
    closeConfigModal();
  }
});

// Close modal on Escape key
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeConfigModal();
  }
});
