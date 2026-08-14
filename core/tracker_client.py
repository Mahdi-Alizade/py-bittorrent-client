import sys
import urllib.parse
from pathlib import Path
from colorama import Fore, Style, init
import xml.etree.ElementTree as ET
import requests # pip install requests

# اصلاح مسیرها برای اجرای مستقیم بدون ارور ایمپورت
sys.path.append(str(Path(__file__).resolve().parent.parent))
init(autoreset=True)

class TrackerClient:
    """
    Communicates with HTTP trackers to retrieve peer lists.
    Standard implementation based on BEP-03 (UDP/HTTP Traversal).
    """
    
    def __init__(self, info_hash: str, peer_id: str):
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.peers = []

    def announce(self, tracker_url: str) -> dict:
        """
        Sends an 'announce' request to the tracker and parses the XML response.
        
        Args:
            tracker_url: Full URL like 'http://open.tracker.cl:80/announce'
            
        Returns:
            Dictionary containing parsed metadata and peers list
        """
        try:
            print(f"{Fore.CYAN}[*] Contacting Tracker at {tracker_url}...{Style.RESET_ALL}")
            
            # Prepare required parameters according to BitTorrent spec
            params = {
                'info_hash': urllib.parse.unquote(self.info_hash),
                'peer_id': urllib.parse.unquote(self.peer_id),
                'port': 6881,  # Our local port
                'uploaded': 0,
                'downloaded': 0,
                'left': 1000,  # Assuming full download needed
                'compact': 1,  # Get compact IP format (saves bandwidth)
                'numwant': 50  # Want 50 peers
            }
            
            # Send the POST/GET request
            response = requests.get(tracker_url, params=params, timeout=10)
            
            if response.status_code != 200:
                print(f"{Fore.RED}[-] Tracker returned non-success status: {response.status_code}{Style.RESET_ALL}")
                return {}

            # Parse XML response
            root = ET.fromstring(response.content)
            
            interval = root.findtext('interval', '30')
            peers_data = root.findtext('peers')
            
            print(f"{Fore.GREEN}[+] Tracker connected! Interval: {interval}s{Style.RESET_ALL}")
            
            # Compact peers decoding (Binary packed IP + Port) goes here in production
            # For now, let's look for text-based peers if compact was not used
            if peers_data:
                print(f"{Fore.YELLOW}[!] Found peer data (length: {len(peers_data)}){Style.RESET_ALL}")
                
            return {
                'interval': int(interval),
                'complete': root.findtext('complete', '0'),
                'incomplete': root.findtext('incomplete', '0'),
                'peers_raw': peers_data
            }

        except requests.exceptions.RequestException as e:
            print(f"{Fore.RED}[-] Tracker connection error: {e}{Style.RESET_ALL}")
            return {'error': str(e)}
        except Exception as e:
            print(f"{Fore.RED}[-] XML Parsing Error: {e}{Style.RESET_ALL}")
            return {'error': str(e)}