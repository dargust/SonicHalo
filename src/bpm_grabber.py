import requests

def get_song_bpm(artist, title):
    """
    Fetches the BPM of a song using the SongBPM API.
    Returns BPM as an integer if found, else None.
    """
    url = "https://api.getsongbpm.com/search/"
    api_key = "YOUR_API_KEY"  # Replace with your SongBPM API key

    params = {
        "api_key": api_key,
        "type": "both",
        "lookup": f"{artist} {title}"
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        # SongBPM returns a list of songs, pick the first match
        if data.get("search"):
            bpm = data["search"][0].get("tempo")
            return int(float(bpm)) if bpm else None
    except Exception as e:
        print(f"Error fetching BPM: {e}")
    return None

if __name__ == "__main__":
    artist = input("Enter artist name: ")
    title = input("Enter song title: ")
    bpm = get_song_bpm(artist, title)
    if bpm:
        print(f"BPM for '{artist} - {title}': {bpm}")
    else:
        print("BPM not found.")