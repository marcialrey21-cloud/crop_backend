import base64
import json
import re
from django.http import JsonResponse  
import requests 
from dotenv import load_dotenv
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from openai import AzureOpenAI
from .models import ScanHistory, EmailOTP, UserProfile
import random
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta 

load_dotenv()

class AnalyzeLeafView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        from openai import AzureOpenAI

        # --- 1. SARI-SARI STORE: CHECK BALANCE FIRST ---
        user_profile = getattr(request.user, 'profile', None)
        if not user_profile:
            return JsonResponse({"error": "User profile not found."}, status=400)
            
        if user_profile.ai_credits <= 0:
            return JsonResponse({
                "error": "INSUFFICIENT_CREDITS",
                "message": "You have 0 AI Scans left. Please reload via GCash to continue analyzing crops."
            }, status=403)
                    
        try:
            client = AzureOpenAI(api_version="2024-02-15-preview")
        except Exception as e:
            return JsonResponse({"error": f"Failed to initialize Azure: {str(e)}"}, status=500)

        try:
            # --- 1. FETCH WEATHER ---
            latitude = request.POST.get('latitude')
            longitude = request.POST.get('longitude')
            weather_context = "Weather data unavailable."
            temp = "Unknown"
            humidity = "Unknown"
            precip = "Unknown"

            if latitude and longitude:
                try:
                    import os
                    api_key = os.getenv("OPENWEATHER_API_KEY")
                    
                    # 'units=metric' automatically converts to Celsius and mm
                    weather_url = f"https://api.openweathermap.org/data/2.5/weather?lat={latitude}&lon={longitude}&appid={api_key}&units=metric"
                    weather_resp = requests.get(weather_url).json()
                    
                    temp = weather_resp['main']['temp']
                    humidity = weather_resp['main']['humidity']
                    
                    # OWM only includes 'rain' if it is actively raining, so we use .get() to prevent crashes
                    precip = weather_resp.get('rain', {}).get('1h', 0.0) 
                    
                    weather_context = f"Current local weather at the farm: {temp}°C, {humidity}% humidity, {precip}mm precipitation."
                except Exception as e:
                    print(f"Weather Fetch Failed: {e}")
                    pass

            # --- 2. GRAB BATCH IMAGES ---
            # We now look for a list of images (for Yield mode), but fallback to single 'image' (for Health mode)
            images = request.FILES.getlist('images')
            if not images:
                single_image = request.FILES.get('image')
                if single_image:
                    images = [single_image]

            if not images:
                return JsonResponse({"error": "No images were received from the app."}, status=400)

            # Convert every uploaded image into base64
            base64_images = [base64.b64encode(img.read()).decode('utf-8') for img in images]

            # --- 3. DETERMINE MODE & SET PROMPT ---
            scan_mode = request.POST.get('scan_mode', 'health')
            
            if scan_mode == 'yield': 
                farm_size = request.POST.get('farm_size', 'Unknown')
                system_prompt = f"""
                You are an expert agronomist in the Philippines.
                Context: Farm area is {farm_size}.
                You will be provided with {len(base64_images)} representative images of different zones of the same field.
                First, visually analyze the phenological growth stage of the crop to estimate its current age.
                Then, calculate the average health and project the total harvest data for the entire field.
                Respond ONLY with a valid JSON object. Do not include markdown.
                {{
                    "plant_name": "Identify the crop",
                    "diagnosis": "Overall field health status and estimated current growth stage",
                    "confidence": "High, Medium, or Low",
                    "organic_treatment": "Estimated days to harvest: [integer] days",
                    "industry_treatment": "Estimated total yield: [string] (e.g., 2.5 Tons)"
                }}
                """
            else: # Health Scan Mode
                system_prompt = f"""
                You are an expert agronomist and plant pathologist.
                Weather Context: {weather_context}
                Analyze the image and factor the current weather into your diagnosis.
                Respond ONLY with a valid JSON object. Do not include markdown.
                {{
                    "plant_name": "Identify the crop (e.g., Rice, Corn, Tomato)",
                    "diagnosis": "Name of the disease or 'Healthy'",
                    "confidence": "High, Medium, or Low",
                    "organic_treatment": "Provide step-by-step organic/natural treatment.",
                    "industry_treatment": "Provide standard commercial/chemical treatment guidelines."
                }}
                """

            # --- 4. BUILD THE MULTI-IMAGE AZURE PAYLOAD ---
            user_content = [{"type": "text", "text": "Analyze these crop images based on the system instructions."}]
            for b64 in base64_images:
                user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

            # --- 5. CALL AZURE AI ---
            response = client.chat.completions.create(
                model="gpt-4o", # <--- CRITICAL: TYPE YOUR DEPLOYMENT NAME HERE
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                max_tokens=800
            )
            
            ai_response_text = response.choices[0].message.content
            
            # --- 6. CLEAN, PARSE, AND ATTACH WEATHER ---
            cleaned_text = re.sub(r'```json\n|```', '', ai_response_text).strip()
            parsed_data = json.loads(cleaned_text)
            
            parsed_data['temperature'] = str(temp) 
            parsed_data['humidity'] = str(humidity)
            parsed_data['precipitation'] = str(precip)

            # --- 7. SAVE TO DATABASE ---
            organic = parsed_data.get('organic_treatment', '')
            industry = parsed_data.get('industry_treatment', '')
            combined_treatments = f"🌿 Organic:\n{organic}\n\n🧪 Industry:\n{industry}".strip()

            if images:
                images[0].seek(0)

            # --- SMART DATA SANITIZER ---
            # We must guarantee confidence_score is a number for the database
            raw_confidence = str(parsed_data.get('confidence', '85')).lower()
            confidence_val = 85 # Default fallback
            
            numbers = re.findall(r'\d+', raw_confidence)
            
            if numbers:
                # If the AI returns "85" or "85%", grab the number
                confidence_val = int(numbers[0])
            else:
                # If the AI returns text like "High", map it to a logical integer
                if 'high' in raw_confidence:
                    confidence_val = 90
                elif 'medium' in raw_confidence:
                    confidence_val = 70
                elif 'low' in raw_confidence:
                    confidence_val = 50

            # Save the record securely
            from .models import ScanHistory
            ScanHistory.objects.create(
                user=request.user,
                disease_name=parsed_data.get('diagnosis', 'Unknown'),
                confidence_score=confidence_val, # <--- NOW GUARANTEED TO BE A NUMBER
                treatments=combined_treatments,
                image=images[0] if images else None
            )
            
            # --- 2. SARI-SARI STORE: DEDUCT PAYMENT ---
            user_profile.ai_credits -= 1
            user_profile.save()
            
            # We add the remaining credits to the parsed_data so the phone knows the balance!
            parsed_data['remaining_credits'] = user_profile.ai_credits

            return JsonResponse(parsed_data, status=200)

        except json.JSONDecodeError:
            return JsonResponse({"error": "AI failed to return valid JSON format."}, status=500)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
            
class ScanHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Fetch only the scans belonging to the currently logged-in farmer
        history = ScanHistory.objects.filter(user=request.user).order_by('-created_at')
        
        data = []
        for item in history:
            data.append({
                "id": item.id,
                "disease_name": item.disease_name, # The original AI Guess
                "confidence": item.confidence_score,
                "date": item.created_at.strftime("%b %d, %Y"),
                "image_url": request.build_absolute_uri(item.image.url) if item.image else None,
                
                # --- THE NEW ENTERPRISE FIELDS ---
                "is_reviewed": item.is_reviewed,
                "expert_diagnosis": item.expert_diagnosis,
            })
            
        return JsonResponse({"history": data}, status=200)

class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # Security: get_or_create ensures older accounts that predated 
        # this update don't crash the server. It silently fixes them.
        profile, created = UserProfile.objects.get_or_create(user=user)
        
        total_scans = ScanHistory.objects.filter(user=user).count()

        return JsonResponse({
            'username': user.username,
            'email': user.email,
            'date_joined': user.date_joined.strftime("%b %Y"),
            'total_scans': total_scans,
            'is_agronomist': profile.is_agronomist, # <-- The Enterprise Badge!
        }, status=200)

from django.contrib.auth.models import User

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        email = request.data.get('email')
        password = request.data.get('password')

        if not username or not email or not password:
            return JsonResponse({"error": "All fields are required."}, status=400)

        if User.objects.filter(username=username).exists() or User.objects.filter(email=email).exists():
            return JsonResponse({"error": "Username or email is already taken."}, status=400)

        try:
            # 1. Create the user, but LOCK the account (is_active = False)
            user = User.objects.create_user(username=username, email=email, password=password)
            user.is_active = False 
            user.save()

            # 2. Generate a secure 6-digit OTP
            otp_code = str(random.randint(100000, 999999))
            
            # Save or update the OTP in the vault
            EmailOTP.objects.update_or_create(email=email, defaults={'otp': otp_code, 'created_at': timezone.now()})

            # 3. Send the physical email
            send_mail(
                subject="Verify your Uni-Farm Hub Account",
                message=f"Hello {username},\n\nYour 6-digit verification code is: {otp_code}\n\nThis code expires in 10 minutes.",
                from_email=None, # Uses the default from settings.py
                recipient_list=[email],
                fail_silently=False,
            )

            return JsonResponse({"message": "Verification code sent to your email.", "email": email}, status=201)
        except Exception as e:
            return JsonResponse({"error": f"Failed to create account: {str(e)}"}, status=500)


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        otp = request.data.get('otp')

        try:
            # 1. Check if the OTP exists and matches
            otp_record = EmailOTP.objects.get(email=email, otp=otp)
            
            # 2. Check if it expired (older than 10 minutes)
            if timezone.now() > otp_record.created_at + timedelta(minutes=10):
                return JsonResponse({"error": "This code has expired. Please register again."}, status=400)

            # 3. Unlock the user's account!
            user = User.objects.get(email=email)
            user.is_active = True
            user.save()

            # 4. Shred the OTP so it can't be reused
            otp_record.delete()

            return JsonResponse({"message": "Account successfully verified! You can now log in."}, status=200)

        except EmailOTP.DoesNotExist:
            return JsonResponse({"error": "Invalid verification code."}, status=400)

class PendingScansView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # SECURITY: Kick them out if they aren't an Agronomist
        if not request.user.is_staff:
            return JsonResponse({"error": "Unauthorized. Agronomist access only."}, status=403)

        # Fetch scans that have low AI confidence (< 85) and haven't been reviewed yet
        pending_scans = ScanHistory.objects.filter(is_reviewed=False, confidence_score__lt=85).order_by('-created_at')
        
        data = []
        for scan in pending_scans:
            data.append({
                "id": scan.id,
                "farmer": scan.user.username,
                "ai_diagnosis": scan.disease_name,
                "confidence": scan.confidence_score,
                "date": scan.created_at.strftime("%b %d, %Y"),
                # Safely grab the image URL if it exists
                "image_url": request.build_absolute_uri(scan.image.url) if scan.image else None 
            })
            
        return JsonResponse(data, safe=False, status=200)


class SubmitReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, scan_id):
        if not request.user.is_staff:
            return JsonResponse({"error": "Unauthorized."}, status=403)

        expert_diagnosis = request.data.get('diagnosis')
        if not expert_diagnosis:
            return JsonResponse({"error": "Diagnosis is required."}, status=400)

        try:
            scan = ScanHistory.objects.get(id=scan_id)
            scan.expert_diagnosis = expert_diagnosis
            scan.is_reviewed = True
            scan.reviewed_by = request.user
            scan.save()
            return JsonResponse({"message": "Official diagnosis saved!"}, status=200)
        except ScanHistory.DoesNotExist:
            return JsonResponse({"error": "Scan not found."}, status=404)

class AgronomistDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, 'profile') or not request.user.profile.is_agronomist:
            return JsonResponse({"error": "Unauthorized. Agronomist badge required."}, status=403)

        # FIX 1: Change order_by('-date') to order_by('-created_at')
        flagged_scans = ScanHistory.objects.filter(is_reviewed=False).order_by('-created_at')

        data = []
        for scan in flagged_scans:
            data.append({
                "id": scan.id,
                # THE FIX: If there is no user attached to this scan, call them "Unknown Farmer" instead of crashing
                "farmer_username": scan.user.username if scan.user else "Unknown Farmer",
                "ai_guess": scan.disease_name, 
                "confidence": scan.confidence_score, 
                "date": scan.created_at.strftime("%b %d, %Y") if scan.created_at else "Unknown Date",
                "image_url": request.build_absolute_uri(scan.image.url) if scan.image else None,
            })

        return JsonResponse({"flagged_scans": data}, status=200)

    def post(self, request):
        if not hasattr(request.user, 'profile') or not request.user.profile.is_agronomist:
            return JsonResponse({"error": "Unauthorized."}, status=403)

        scan_id = request.data.get('scan_id')
        new_diagnosis = request.data.get('expert_diagnosis')

        try:
            scan = ScanHistory.objects.get(id=scan_id)
            scan.expert_diagnosis = new_diagnosis
            scan.is_reviewed = True
            scan.save()

            # --- NEW: TRIGGER PUSH NOTIFICATION ---
            farmer_profile = getattr(scan.user, 'profile', None)
            
            if farmer_profile and farmer_profile.expo_push_token:
                push_payload = {
                    "to": farmer_profile.expo_push_token,
                    "title": "🧑‍🌾 Expert Review Complete!",
                    "body": f"An Agronomist reviewed your scan. Diagnosis: {new_diagnosis}",
                    "data": {"scan_id": scan.id} # We can use this later to open the exact screen
                }
                
                # Fire the signal to Expo's servers
                try:
                    response = requests.post("https://exp.host/--/api/v2/push/send", json=push_payload)
                    # --- NEW DIAGNOSTIC TRACER ---
                    print(f"EXPO RECEIPT: {response.json()}") 
                except Exception as e:
                    print(f"Push Network Error: {e}")

            return JsonResponse({"message": "Expert override saved successfully!"}, status=200)
        except ScanHistory.DoesNotExist:
            return JsonResponse({"error": "Scan not found."}, status=404)
        

class SavePushTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get('token')
        if not token:
            return JsonResponse({"error": "No token provided"}, status=400)

        # Get the profile and save the phone's unique address
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        profile.expo_push_token = token
        profile.save()

        return JsonResponse({"message": "Push token saved securely."}, status=200)

class LiveWeatherView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        lat = request.GET.get('lat', '7.7853')
        lon = request.GET.get('lon', '126.4468')
        
        import os
        import requests
        api_key = os.getenv("OPENWEATHER_API_KEY")

        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
            resp = requests.get(url).json()
            
            return JsonResponse({
                "temperature": str(resp['main']['temp']),
                "humidity": str(resp['main']['humidity']),
                "precipitation": str(resp.get('rain', {}).get('1h', 0.0))
            })
        except Exception as e:
            return JsonResponse({"error": "Failed to fetch radar."}, status=500)