import requests

# The URL of your Django API endpoint
url = 'http://127.0.0.1:8000/api/analyze-leaf/'

# The name of the image file you just downloaded
image_filename = 'sick_leaf.jpg' 

print(f"Sending {image_filename} to the AI for analysis...")

try:
    # Open the image in binary mode and send it via POST request
    with open(image_filename, 'rb') as img:
        files = {'leaf_image': img}
        response = requests.post(url, files=files)
    
    # Print the AI's response!
    print("\n--- AI DIAGNOSIS ---")
    print(response.json())

except FileNotFoundError:
    print(f"Error: Could not find '{image_filename}'. Make sure it is in the same folder as this script.")
except Exception as e:
    print(f"An error occurred: {e}")