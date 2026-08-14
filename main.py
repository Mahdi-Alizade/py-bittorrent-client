import sys
from pathlib import Path
from colorama import Fore, Style, init

# راه‌اندازی رنگ‌ها برای خروجی تمیز
init()

def main():
    """Main Entry Point"""
    print(f"{Fore.CYAN}Initializing Py-BitTorrent Client...{Style.RESET_ALL}")
    
    # TODO: اینجا بعداً منطق خواندن Magnet Link یا فایل torrent رو پیاده میکنیم
    
    print(f"{Fore.GREEN}Environment setup complete.{Style.RESET_ALL}")
    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n{Fore.RED}Process interrupted by user.{Style.RESET_ALL}")
        sys.exit(1)