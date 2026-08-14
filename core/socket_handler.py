import socket
import sys
from pathlib import Path
from colorama import Fore, Style, init

# اصلاح مسیرها برای اجرای مستقیم بدون ارور ایمپورت
sys.path.append(str(Path(__file__).resolve().parent.parent))

# FIX: Changed import to absolute path
from core.network import NetworkProtocol

init(autoreset=True)

class PeerConnector:
    """
    Handles low-level TCP connections to BitTorrent peers.
    Implements the strict handshake required by the protocol.
    """
    
    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port
        self.sock = None

    def connect_and_handshake(self, info_hash_hex: str, my_peer_id: str) -> bool:
        """
        Opens a socket connection and performs the BitTorrent Handshake.
        
        Args:
            info_hash_hex: Hex string of the Info Hash (e.g. 'a94a8fe5...')
            my_peer_id: Your client's unique ID (e.g. 'AvestaClient-0.1')
            
        Returns:
            True if handshake successful, False otherwise.
        """
        
        try:
            print(f"{Fore.CYAN}[*] Attempting to connect to {self.ip}:{self.port}...{Style.RESET_ALL}")
            
            # 1. Initialize TCP Socket
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5) # Wait max 5 seconds
            
            # 2. Connect
            self.sock.connect((self.ip, self.port))
            print(f"{Fore.GREEN}[+] Successfully connected!{Style.RESET_ALL}")
            
            # 3. Prepare Handshake
            # We assume you have already generated these from your torrent metadata
            info_hash_bytes = bytes.fromhex(info_hash_hex) 
            
            # Build the exact handshake format defined in BEP-00
            # Format: [pstrlen][pstr][reserved][info_hash][peer_id]
            bt_proto = b'bittorrent protocol'
            reserved = b'\x00\x00\x00\x00\x00\x00\x00\x00'
            
            handshake_payload = bytearray()
            handshake_payload.append(len(bt_proto))
            handshake_payload.extend(bt_proto)
            handshake_payload.extend(reserved)
            handshake_payload.extend(info_hash_bytes)
            handshake_payload.extend(my_peer_id.encode('latin-1'))
            
            # 4. Send Handshake
            print(f"{Fore.YELLOW}[*] Sending Handshake ({len(handshake_payload)} bytes)...{Style.RESET_ALL}")
            self.sock.sendall(bytes(handshake_payload))
            
            # 5. Receive Response
            # The response must match our handshake pattern
            expected_prefix = f'{len(bt_proto)}'.encode() + bt_proto
            
            response_data = self.sock.recv(128)
            
            if response_data.startswith(expected_prefix):
                received_info_hash = response_data[28:48] # Extract 20-byte hash
                
                print(f"{Fore.LIGHTWHITE_EX}[+] Received valid handshake!")
                print(f"    Info Hash Match: {'YES' if received_info_hash == info_hash_bytes else 'NO'}")
                
                # Now the channel is OPEN for piece selection
                print(f"{Fore.GREEN}[*] Channel Opened: Ready for BEP-6 Protocol Extensions.{Style.RESET_ALL}")
                return True
            else:
                print(f"{Fore.RED}[-] Invalid Handshake response. Connection dropped.{Style.RESET_ALL}")
                self.close()
                return False
                
        except socket.timeout:
            print(f"{Fore.RED}[!] Timeout connecting to {self.ip}:{self.port}{Style.RESET_ALL}")
            self.close()
            return False
        except ConnectionRefusedError:
            print(f"{Fore.RED}[!] Connection Refused by {self.ip}:{self.port}{Style.RESET_ALL}")
            self.close()
            return False
        except Exception as e:
            print(f"{Fore.RED}[!] Fatal Error: {e}{Style.RESET_ALL}")
            self.close()
            return False

    def close(self):
        if self.sock:
            self.sock.close()
            print(f"{Fore.WHITE}[*] Connection closed.{Style.RESET_ALL}")

def run_demo():
    """
    A utility function to test the connector against a real-world seed.
    Example: Connecting to a public tracker's announce endpoint (mocked).
    """
    # Note: Real connection requires knowing the specific peer IP:Port from a DHT or Tracker.
    # Here we demonstrate the logic.
    
    if len(sys.argv) < 3:
        print("Usage: python core/socket_handler.py <IP> <Port>")
        print("Example: python core/socket_handler.py 127.0.0.1 6881")
        return

    target_ip = sys.argv[1]
    target_port = int(sys.argv[2])
    
    # We reuse the vars from main context implicitly or passed through args
    # For this standalone test, we use generic values
    demo_hash = "ca5cf02a5b265b13500214be40196d532286f49f" # From sample.txt
    client_id = "AvestaClient-0.1"

    connector = PeerConnector(target_ip, target_port)
    connector.connect_and_handshake(demo_hash, client_id)

if __name__ == "__main__":
    run_demo()