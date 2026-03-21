#!/usr/bin/env python3
"""Quick test to verify rate limiting works."""

import asyncio
import json

import websockets

async def test_rate_limit():
    """Test rate limiting by flooding with messages."""
    uri = "ws://localhost:8000/ws/chat/rate-test"

    async with websockets.connect(uri) as ws:
        # Receive new_session
        msg = await ws.recv()
        data = json.loads(msg)
        print(f"Connected: {data}")

        # Send burst of messages WITHOUT waiting for responses
        print("\nSending 70 messages as fast as possible (no waiting)...")
        rate_limited = False

        # Send all messages first
        for i in range(70):
            await ws.send(
                json.dumps(
                    {
                        "type": "ping"  # Use ping instead of message to avoid slow processing
                    }
                )
            )

        print("All 70 messages sent, now checking responses...")

        # Now read responses
        for i in range(200):  # Read more than we sent to catch all responses
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                data = json.loads(msg)

                # Check for rate limit error (raw JSON, not wrapped in ServerMessage)
                if data.get("type") == "error" and data.get("code") == "RATE_LIMITED":
                    print("✓ Rate limited detected")
                    print(f"  Response: {data}")
                    rate_limited = True

                # Print first few responses
                if i < 5:
                    print(f"  [{i}] Received: {data.get('type')} (seq: {data.get('seq', 'N/A')})")

            except TimeoutError:
                break

        if not rate_limited:
            print("✗ Rate limiting did NOT trigger after 70 messages")

        # Drain remaining messages
        print("\nDraining remaining messages...")
        count = 0
        while count < 100:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                count += 1
                if count < 10:
                    data = json.loads(msg)
                    print(f"  Received: {data.get('type')} (seq: {data.get('seq', 'N/A')})")
            except TimeoutError:
                break

        print(f"\nTotal messages drained: {count}")

if __name__ == "__main__":
    asyncio.run(test_rate_limit())
