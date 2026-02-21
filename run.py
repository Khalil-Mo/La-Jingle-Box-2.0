#!/usr/bin/env python3
"""
La Jingle Box 2.0 - Unified Launcher

Starts both the web interface and MIDI sampler together.
"""

import os
import sys
import time
import signal
import subprocess
import webbrowser

# --- Configuration ---
WEB_SERVER_PORT = 80
WEB_SERVER_STARTUP_DELAY = 2  # Seconds to wait for server to start

# Global reference for cleanup
web_server_process = None


def get_project_dir():
    """Get the directory where this script is located."""
    return os.path.dirname(os.path.abspath(__file__))


def start_web_server():
    """Start the Node.js web server in the background."""
    global web_server_process
    
    project_dir = get_project_dir()
    server_dir = os.path.join(project_dir, "piano-upload")
    server_script = os.path.join(server_dir, "server.js")
    
    if not os.path.exists(server_script):
        print(f"[ERROR] Web server not found: {server_script}")
        return False
    
    print("[WEB] Starting web server...")
    
    try:
        # Start Node.js server as a subprocess
        web_server_process = subprocess.Popen(
            ["node", "server.js"],
            cwd=server_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        )
        
        # Wait for server to start
        time.sleep(WEB_SERVER_STARTUP_DELAY)
        
        # Check if process is still running
        if web_server_process.poll() is not None:
            print("[ERROR] Web server failed to start!")
            return False
        
        print(f"[WEB] Server running at http://localhost:{WEB_SERVER_PORT}")
        return True
        
    except FileNotFoundError:
        print("[ERROR] Node.js not found. Please install Node.js.")
        return False
    except Exception as e:
        print(f"[ERROR] Failed to start web server: {e}")
        return False


def open_browser():
    """Open the web interface in the default browser."""
    url = f"http://localhost:{WEB_SERVER_PORT}"
    print(f"[BROWSER] Opening {url}")
    webbrowser.open(url)


def cleanup():
    """Stop the web server process."""
    global web_server_process
    
    if web_server_process is not None:
        print("\n[CLEANUP] Stopping web server...")
        try:
            if sys.platform == "win32":
                web_server_process.terminate()
            else:
                web_server_process.send_signal(signal.SIGTERM)
            web_server_process.wait(timeout=5)
            print("[CLEANUP] Web server stopped.")
        except Exception as e:
            print(f"[CLEANUP] Force killing web server: {e}")
            web_server_process.kill()
        web_server_process = None


def run_midi_sampler():
    """Run the MIDI sampler (imports and runs main)."""
    # Import here to avoid loading pygame until needed
    from midi_sampler import main
    main()


def main():
    """Main entry point."""
    print("=" * 50)
    print("     LA JINGLE BOX 2.0 - Unified Launcher")
    print("=" * 50)
    
    try:
        # 1. Start web server
        if not start_web_server():
            print("\n[WARN] Continuing without web server...")
        else:
            # 2. Open browser
            open_browser()
        
        # 3. Run MIDI sampler (blocks until Ctrl+C)
        print("\n[MIDI] Starting MIDI sampler...\n")
        run_midi_sampler()
        
    except KeyboardInterrupt:
        print("\n[EXIT] Shutting down...")
    finally:
        cleanup()


if __name__ == "__main__":
    main()
