import os
import requests

ASSETS = {
    "background_noise.wav": "https://www.soundjay.com/nature/rain-01.wav", # Placeholder: rain as background noise if office is not found
    "keyboard_click.wav": "https://www.soundjay.com/communication/keyboard-typing-chatter-1.wav",
    "breath.wav": "https://www.soundjay.com/human/man-breathing-1.wav"
}

# Note: The above links might still 404. I'll use some known public ones if possible.
# For now, I'll provide a script that the user can run or modify.

def download():
    assets_dir = os.path.join(os.path.dirname(__file__), "backend", "chat", "assets")
    os.makedirs(assets_dir, exist_ok=True)
    
    for filename, url in ASSETS.items():
        path = os.path.join(assets_dir, filename)
        if os.path.exists(path):
            print(f"Skipping {filename}, already exists.")
            continue
            
        print(f"Downloading {filename}...")
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                with open(path, "wb") as f:
                    f.write(r.content)
                print(f"Successfully downloaded {filename}")
            else:
                print(f"Failed to download {filename}: HTTP {r.status_code}")
        except Exception as e:
            print(f"Error downloading {filename}: {e}")

if __name__ == "__main__":
    download()
