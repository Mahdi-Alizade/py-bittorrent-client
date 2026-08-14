import requests

# Downloading a tiny seed (like a basic Arch Linux ISO snippet or similar)
# Using a generic valid tracker URL embedded inside a known torrent structure usually requires binary editing.
# For simplicity, let's just tell you where to drop the file.

url = "https://releases.archlinux.org/2024.10.07/arch-x86_64.iso.torrent" # Example real torrent
response = requests.get(url)

if response.status_code == 200:
    with open('data/archlinux.torrent', 'wb') as f:
        f.write(response.content)
    print(f"[+] Real-world Torrent downloaded successfully!")
else:
    print("[!] Failed to download torrent. Please download a .torrent file manually into 'data/' folder.")