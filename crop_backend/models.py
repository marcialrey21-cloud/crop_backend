from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

class ScanHistory(models.Model):
    # <-- NEW: This links every single scan to a specific user account!
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True) 
    
    image = models.ImageField(upload_to='scans/')
    disease_name = models.CharField(max_length=255)
    confidence_score = models.FloatField()
    treatments = models.JSONField(default=list)
    estimated_days_to_harvest = models.IntegerField(null=True, blank=True)
    estimated_yield = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expert_diagnosis = models.CharField(max_length=255, null=True, blank=True)
    is_reviewed = models.BooleanField(default=False)    

    def __str__(self):
        return f"{self.user.username} - {self.disease_name}"

class EmailOTP(models.Model):
    email = models.EmailField(unique=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.email} - {self.otp}"

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    is_agronomist = models.BooleanField(default=False)
    
    # --- NEW: THE NOTIFICATION ADDRESS ---
    expo_push_token = models.CharField(max_length=255, null=True, blank=True)
    # --- NEW: THE SARI-SARI STORE CREDIT SYSTEM ---
    ai_credits = models.IntegerField(default=3)
    
    def __str__(self):
        role = "Agronomist" if self.is_agronomist else "Farmer"
        return f"{self.user.username} - {role}"
# --- AUTOMATION: Automatically create a Profile when a User signs up ---
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)