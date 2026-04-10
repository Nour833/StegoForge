with open("stego.mp3", "rb") as f:
    data = f.read()
    print("Does it start with RIFF?", data.startswith(b"RIFF"))
    
