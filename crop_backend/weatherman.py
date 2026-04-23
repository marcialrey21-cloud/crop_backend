import os
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from django.utils import timezone

def check_morning_weather():
    print(f"\n[{timezone.now()}] 🌤️ Starting Daily Weather Radar...")
    
    # 1. Import your database model here to avoid Django startup crashes
    from crop_backend.models import UserProfile 
    
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        print("❌ Missing OpenWeather API Key.")
        return

    # 2. Grab every profile that has a Push Token registered
    active_farmers = UserProfile.objects.exclude(expo_push_token__isnull=True).exclude(expo_push_token__exact='')
    print(f"📡 Found {active_farmers.count()} farmers with active push tokens.")

    # 3. Loop through the database
    for profile in active_farmers:
        # If you haven't saved GPS to the database yet, we fallback to Cateel for the MVP
        lat = getattr(profile, 'latitude', "7.7853")
        lon = getattr(profile, 'longitude', "126.4468")
        
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
            resp = requests.get(url).json()
            
            temp = resp['main']['temp']
            condition = resp['weather'][0]['main'].lower()
            
            alert_title = ""
            alert_body = ""
            
            # The Logic Engine
            if "rain" in condition:
                alert_title = "🌧️ Heavy Rain Expected"
                alert_body = f"Current temp is {temp}°C. Delay pesticide spraying today to prevent runoff."
            elif temp > 20:
                alert_title = "☀️ Extreme Heat Warning"
                alert_body = f"Temperatures reaching {temp}°C today. Ensure crops are fully irrigated."
            
            # 4. Fire the actual Push Notification!
            if alert_title:
                expo_url = "https://exp.host/--/api/v2/push/send"
                payload = {
                    "to": profile.expo_push_token,
                    "title": alert_title,
                    "body": alert_body,
                    "data": {"type": "weather_alert"} # Custom data just in case you want to route it later
                }
                
                # Send the data to Apple/Google via Expo
                requests.post(expo_url, json=payload)
                print(f"✅ Alert beamed to {profile.user.username}'s phone!")
            else:
                 print(f"✅ Weather is clear for {profile.user.username}. No alert sent.")
                
        except Exception as e:
            print(f"❌ Failed to process weather for {profile.user.username}: {e}")

    print("🏁 Daily Weather Radar complete.\n")

def start_scheduler():
    scheduler = BackgroundScheduler()
    
    # --- THE PRODUCTION CRON JOB ---
    # Instead of an 'interval', we use a 'cron' trigger to fire exactly at 6:00 AM every day.
    # For testing right now, change hour=6 and minute=0 to be 2 minutes from your current time!
    scheduler.add_job(check_morning_weather, 'cron', hour=6, minute=00)
    
    scheduler.start()
    print("⏰ Production Weatherman is online. Next radar scan scheduled for 6:00 AM.")