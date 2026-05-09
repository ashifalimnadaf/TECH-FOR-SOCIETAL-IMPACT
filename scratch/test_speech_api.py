import speech_recognition as sr
import os

def test_free_google_speech_api():
    """
    Tests Google's FREE Web Speech API via the speech_recognition library.
    This is the same API used by Chrome and doesn't require a service account key.
    """
    print("--- Testing Google's Free Web Speech API (Python) ---")
    
    # Initialize recognizer
    r = sr.Recognizer()
    
    # Use Microphone as source
    try:
        with sr.Microphone() as source:
            print("\nAdjusting for ambient noise... Please wait.")
            r.adjust_for_ambient_noise(source, duration=1)
            print("Listening... Speak something!")
            audio = r.listen(source, timeout=5)
            
            print("Processing speech...")
            # recognize speech using Google Speech Recognition (FREE)
            try:
                text = r.recognize_google(audio)
                print(f"\nSUCCESS! You said: \"{text}\"")
            except sr.UnknownValueError:
                print("Google Speech Recognition could not understand audio.")
            except sr.RequestError as e:
                print(f"Could not request results from Google Speech Recognition service; {e}")
                
    except Exception as e:
        print(f"\nERROR: {e}")
        print("\nCommon issues:")
        print("1. Library 'speech_recognition' or 'PyAudio' not installed.")
        print("   Fix: pip install SpeechRecognition PyAudio")
        print("2. No microphone detected.")

if __name__ == "__main__":
    test_free_google_speech_api()
