from youtube_transcript_api import YouTubeTranscriptApi

def get_transcript(video_id):
    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)
        return " ".join([t.text for t in transcript])
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    import sys
    video_id = "rA6nX-C07ws"
    print(get_transcript(video_id))
