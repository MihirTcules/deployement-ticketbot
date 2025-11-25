"""
Simple test script to verify WebSocket connection and basic functionality
Run this AFTER starting the main bot.py
"""
import asyncio
import websockets
import json

WS_URL = "ws://localhost:8765"

async def test_connection():
    """Test WebSocket connection and message exchange"""
    print("🧪 Testing WebSocket Connection...")
    print(f"Connecting to {WS_URL}...")
    
    try:
        async with websockets.connect(WS_URL) as websocket:
            print("✅ Connected successfully!")
            
            # Test 1: Send hello message
            print("\n📤 Test 1: Sending 'hello' message...")
            await websocket.send(json.dumps({
                "type": "hello",
                "timestamp": asyncio.get_event_loop().time()
            }))
            
            # Wait for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                data = json.loads(response)
                print(f"✅ Received response: {data}")
            except asyncio.TimeoutError:
                print("⚠️ No response received (this is OK if bot doesn't respond to hello)")
            
            # Test 2: Send ping
            print("\n📤 Test 2: Sending 'ping' message...")
            await websocket.send(json.dumps({
                "type": "ping",
                "timestamp": asyncio.get_event_loop().time()
            }))
            
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                data = json.loads(response)
                if data.get("type") == "pong":
                    print(f"✅ Received pong: {data}")
                else:
                    print(f"⚠️ Unexpected response: {data}")
            except asyncio.TimeoutError:
                print("❌ No pong received")
            
            # Test 3: Simulate extension acknowledgment
            print("\n📤 Test 3: Sending 'ack' message (simulating extension)...")
            await websocket.send(json.dumps({
                "type": "ack",
                "status": "stored",
                "url": "https://test.com"
            }))
            print("✅ Ack sent (check bot console for confirmation)")
            
            # Test 4: Simulate extension result
            print("\n📤 Test 4: Sending 'result' message (simulating extension)...")
            await websocket.send(json.dumps({
                "type": "result",
                "status": "success",
                "tabId": 999,
                "url": "https://test.com"
            }))
            print("✅ Result sent (check bot console for confirmation)")
            
            print("\n✅ All tests completed!")
            print("\nℹ️ Check the bot console to verify it received and processed the messages.")
            
    except ConnectionRefusedError:
        print("❌ Connection refused!")
        print("Make sure the bot is running: python bot.py")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("="*60)
    print("WebSocket Connection Test")
    print("="*60)
    print("\n⚠️ Make sure bot.py is running before running this test!\n")
    
    asyncio.run(test_connection())

